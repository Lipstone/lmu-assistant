"""Overlay : une fenêtre transparente, sans bordure, toujours au premier plan, par widget.

Chaque fenêtre affiche un seul widget de la page web locale (`/?mode=overlay&widget=<id>`),
et se place indépendamment sur l'écran. Lancer le serveur d'abord
(l'exécutable LMU-Assistant lance les deux ensemble, voir launcher.py).
Le jeu doit être en mode « fenêtré sans bordure » pour que l'overlay soit visible.

Configuration (T06) lue sur le serveur (GET /api/config, modifiable via /settings.html) :
- position de chaque fenêtre, échelle (taille), widget affiché ou non, clics traversants (Windows) ;
- raccourci global afficher/masquer (paquet `keyboard`, optionnel).
Les changements sont relus toutes les 2 s et appliqués sans redémarrer.

Mode placement (case dans les réglages ou raccourci, `ctrl+shift+p` par défaut) : les clics ne
traversent plus, chaque fenêtre se déplace en la faisant glisser et s'agrandit par la poignée en bas
à droite ; positions et échelles sont enregistrées dans la configuration du serveur.
"""

import argparse
import json
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from .config import AppConfig, window_size

TITLE = "LMU Assistant overlay"
POLL_S = 2.0
PLACEMENT_POLL_S = 0.4  # en mode placement : suivi des fenêtres déplacées à la souris

DEFAULT_HOTKEY = "ctrl+shift+o"
DEFAULT_PLACEMENT_HOTKEY = "ctrl+shift+p"
MIN_SCALE, MAX_SCALE = 0.25, 4.0


def window_title(widget_id: str) -> str:
    return f"{TITLE} - {widget_id}"  # titre unique : sert à retrouver la fenêtre native


def warn(msg: str) -> None:
    print(f"[overlay] {msg}", file=sys.stderr)


def fetch_config(config_url: str) -> dict | None:
    try:
        with urllib.request.urlopen(config_url, timeout=2) as r:
            return json.load(r)
    except Exception as exc:  # serveur pas encore lancé, etc.
        warn(f"config indisponible ({config_url}) : {exc}")
        return None


def put_config(config_url: str, cfg: dict) -> bool:
    req = urllib.request.Request(
        config_url, data=json.dumps(cfg).encode(), method="PUT", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception as exc:
        warn(f"enregistrement de la config impossible : {exc}")
        return False


# --- Clics traversants (Windows uniquement, via l'API Win32) -----------------
# pywebview n'expose pas d'option « click-through » : on ajoute WS_EX_TRANSPARENT
# au style étendu de la fenêtre. Sur les autres OS, la fonction ne fait rien.
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


def set_click_through(title: str, enabled: bool) -> None:
    if sys.platform != "win32":
        if enabled:
            warn("clics traversants non pris en charge hors Windows")
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            warn(f"fenêtre {title!r} introuvable pour les clics traversants")
            return
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if enabled:
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception as exc:
        warn(f"clics traversants impossibles : {exc}")


# --- Raccourci global afficher/masquer ---------------------------------------
class Hotkey:
    """Raccourci global via le paquet `keyboard` ; avertit et ne fait rien s'il manque."""

    def __init__(self, on_press) -> None:
        self.on_press = on_press
        self.current: str | None = None
        self.handle = None
        try:
            import keyboard
        except Exception as exc:  # ImportError, ou droits insuffisants hors Windows
            warn(f"raccourci global indisponible (pip install keyboard) : {exc}")
            self.keyboard = None
        else:
            self.keyboard = keyboard

    def set(self, combo: str) -> None:
        if self.keyboard is None or combo == self.current:
            return
        try:
            if self.handle is not None:
                self.keyboard.remove_hotkey(self.handle)
                self.handle = None
            self.handle = self.keyboard.add_hotkey(combo, self.on_press)
            self.current = combo
            print(f"[overlay] raccourci afficher/masquer : {combo}")
        except Exception as exc:
            warn(f"raccourci {combo!r} refusé : {exc}")
            self.current = combo  # évite de réessayer en boucle


@dataclass(frozen=True)
class WindowState:
    x: int
    y: int
    width: int
    height: int
    visible: bool
    click_through: bool


def plan(cfg: dict, overrides: dict | None = None) -> dict[str, WindowState]:
    """État voulu de chaque fenêtre (une par widget) d'après la config du serveur."""
    try:
        config = AppConfig.model_validate(cfg)
    except ValueError as exc:  # serveur d'une autre version, etc.
        warn(f"config refusée, valeurs par défaut : {exc}")
        config = AppConfig()
    # En mode placement, les fenêtres doivent recevoir la souris.
    click = (overrides or {}).get("click_through", config.window.click_through) and not config.placement
    return {
        w.id: WindowState(w.x, w.y, *window_size(w.id, w.scale), w.visible, click) for w in config.widgets
    }


def clamp_scale(scale: float) -> float:
    return round(round(min(max(float(scale), MIN_SCALE), MAX_SCALE) / 0.05) * 0.05, 2)


class WidgetApi:
    """Fonctions appelées par la page d'un widget (window.pywebview.api) : agrandissement à la souris."""

    def __init__(self, overlay: "Overlay", widget_id: str) -> None:
        self._overlay = overlay  # attributs en _ : non exposés au JavaScript
        self._wid = widget_id

    def set_scale(self, scale: float, final: bool = False) -> None:
        self._overlay.set_scale(self._wid, scale, final)


class Overlay:
    def __init__(self, windows: dict, config_url: str, overrides: dict, initial: dict | None) -> None:
        self.windows = windows  # id du widget -> fenêtre pywebview
        self.config_url = config_url
        self.overrides = overrides  # options de ligne de commande, prioritaires
        self.shown = True  # raccourci afficher/masquer
        self.placement = False
        self.applied: dict[str, WindowState] = {}
        self.resizing: set[str] = set()  # agrandissement en cours : la config ne doit pas le défaire
        self.unsaved: set[str] = set()  # déplacées à la souris, pas encore enregistrées sur le serveur
        self.lock = threading.RLock()  # raccourcis, appels JavaScript et boucle de suivi
        self.hotkey = Hotkey(self.toggle)
        self.placement_hotkey = Hotkey(self.toggle_placement)
        self.initial = initial

    def _set_visible(self, wid: str, visible: bool) -> None:
        win = self.windows[wid]
        win.show() if visible else win.hide()

    def toggle(self) -> None:
        with self.lock:
            self.shown = not self.shown
            for wid, state in self.applied.items():
                self._set_visible(wid, self.shown and state.visible)

    def apply(self, cfg: dict) -> None:
        with self.lock:
            self.placement = bool(cfg.get("placement"))
            for wid, new in plan(cfg, self.overrides).items():
                old = self.applied.get(wid)
                win = self.windows[wid]
                if wid in self.resizing and old is not None:
                    new = replace(new, width=old.width, height=old.height)
                if wid in self.unsaved and old is not None:
                    new = replace(new, x=old.x, y=old.y)
                if old is None or (new.x, new.y) != (old.x, old.y):
                    win.move(new.x, new.y)
                if old is None or (new.width, new.height) != (old.width, old.height):
                    win.resize(new.width, new.height)
                if old is None or new.visible != old.visible:
                    self._set_visible(wid, self.shown and new.visible)
                if old is None or new.click_through != old.click_through:
                    set_click_through(window_title(wid), new.click_through)
                self.applied[wid] = new
            self.hotkey.set(cfg.get("hotkey") or DEFAULT_HOTKEY)
            self.placement_hotkey.set(cfg.get("placement_hotkey") or DEFAULT_PLACEMENT_HOTKEY)

    # --- Mode placement ---------------------------------------------------------
    def save_widgets(self, changes: dict[str, dict]) -> bool:
        """Enregistre sur le serveur des champs de widgets (x, y, scale) changés à la souris."""
        with self.lock:
            cfg = fetch_config(self.config_url)
            if cfg is None:
                return False
            for w in cfg.get("widgets", []):
                w.update(changes.get(w.get("id"), {}))
            if not put_config(self.config_url, cfg):
                return False
            self.unsaved -= set(changes)
            return True

    def toggle_placement(self) -> None:
        with self.lock:
            cfg = fetch_config(self.config_url)
            if cfg is None:
                return
            cfg["placement"] = not cfg.get("placement", False)
            if put_config(self.config_url, cfg):
                self.apply(cfg)

    def sync_moves(self) -> dict[str, dict]:
        """Positions des fenêtres déplacées à la souris depuis la dernière application de la config."""
        moved = {}
        with self.lock:
            if not self.shown:  # tout masqué par le raccourci : rien à suivre
                return moved
            for wid, state in list(self.applied.items()):
                if not state.visible:
                    continue
                try:
                    x, y = int(self.windows[wid].x), int(self.windows[wid].y)
                except Exception:
                    continue
                if (x, y) != (state.x, state.y):
                    self.applied[wid] = replace(state, x=x, y=y)
                    self.unsaved.add(wid)  # la config lue d'ici l'enregistrement ne la ramène pas
                    moved[wid] = {"x": x, "y": y}
        return moved

    def set_scale(self, wid: str, scale: float, final: bool) -> None:
        scale = clamp_scale(scale)
        width, height = window_size(wid, scale)
        with self.lock:
            state = self.applied.get(wid)
            if state is None:
                return
            if final:
                self.resizing.discard(wid)
            else:
                self.resizing.add(wid)
            if (width, height) != (state.width, state.height):
                self.windows[wid].resize(width, height)
                self.applied[wid] = replace(state, width=width, height=height)
        if final:
            self.save_widgets({wid: {"scale": scale}})

    def run(self) -> None:
        """Lancé par pywebview dans un thread une fois les fenêtres créées."""
        time.sleep(0.5)  # laisse les fenêtres natives apparaître (clics traversants)
        self.apply(self.initial or {})
        while True:
            time.sleep(PLACEMENT_POLL_S if self.placement else POLL_S)
            if self.placement:
                self.sync_moves()
            if self.unsaved:
                with self.lock:
                    pending = {w: {"x": self.applied[w].x, "y": self.applied[w].y} for w in self.unsaved}
                self.save_widgets(pending)
            cfg = fetch_config(self.config_url)
            if cfg is not None:
                self.apply(cfg)


def run(url: str, overrides: dict | None = None) -> None:
    """Ouvre une fenêtre par widget sur `url` (page en mode overlay) ; bloque jusqu'à la
    fermeture de toutes les fenêtres (thread principal)."""
    import webview  # pywebview : dépendance optionnelle `overlay`

    overrides = overrides or {}
    parts = urlsplit(url)
    config_url = f"{parts.scheme}://{parts.netloc}/api/config"
    initial = fetch_config(config_url)
    sep = "&" if parts.query else "?"

    overlay = Overlay({}, config_url, overrides, initial)
    for wid, state in plan(initial or {}, overrides).items():
        overlay.windows[wid] = webview.create_window(
            window_title(wid),
            f"{url}{sep}widget={wid}",
            js_api=WidgetApi(overlay, wid),
            x=state.x,
            y=state.y,
            width=state.width,
            height=state.height,
            hidden=not state.visible,
            min_size=(40, 40),  # défaut pywebview 200×100 : plus grand qu'un widget
            frameless=True,
            easy_drag=False,  # glisser seulement en mode placement (classe pywebview-drag-region)
            on_top=True,
            transparent=True,
        )
    webview.start(overlay.run)


def main() -> None:
    parser = argparse.ArgumentParser(description="LMU Assistant : overlay (une fenêtre par widget)")
    parser.add_argument("--url", default="http://localhost:8765/?mode=overlay")
    parser.add_argument("--no-click-through", action="store_true", help="garde les fenêtres cliquables")
    args = parser.parse_args()
    run(args.url, {"click_through": False} if args.no_click_through else {})


if __name__ == "__main__":
    main()
