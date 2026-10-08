"""Overlay : une fenêtre transparente, sans bordure, toujours au premier plan, par widget.

Chaque fenêtre affiche un seul widget de la page web locale (`/?mode=overlay&widget=<id>`),
et se place indépendamment sur l'écran. Lancer le serveur d'abord
(l'exécutable LMU-Assistant lance les deux ensemble, voir launcher.py).
Le jeu doit être en mode « fenêtré sans bordure » pour que l'overlay soit visible.

Configuration (T06) lue sur le serveur (GET /api/config, modifiable via /settings.html) :
- position de chaque fenêtre, échelle (taille), widget affiché ou non, clics traversants (Windows) ;
- raccourci global afficher/masquer (paquet `keyboard`, optionnel).
Les changements sont relus toutes les 2 s et appliqués sans redémarrer.
"""

import argparse
import json
import sys
from dataclasses import dataclass
import time
import urllib.request
from urllib.parse import urlsplit

from .config import AppConfig, window_size

TITLE = "LMU Assistant overlay"
POLL_S = 2.0

DEFAULT_HOTKEY = "ctrl+shift+o"


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
    click = (overrides or {}).get("click_through", config.window.click_through)
    return {
        w.id: WindowState(w.x, w.y, *window_size(w.id, w.scale), w.visible, click) for w in config.widgets
    }


class Overlay:
    def __init__(self, windows: dict, config_url: str, overrides: dict, initial: dict | None) -> None:
        self.windows = windows  # id du widget -> fenêtre pywebview
        self.config_url = config_url
        self.overrides = overrides  # options de ligne de commande, prioritaires
        self.shown = True  # raccourci afficher/masquer
        self.applied: dict[str, WindowState] = {}
        self.hotkey = Hotkey(self.toggle)
        self.initial = initial

    def _set_visible(self, wid: str, visible: bool) -> None:
        win = self.windows[wid]
        win.show() if visible else win.hide()

    def toggle(self) -> None:
        self.shown = not self.shown
        for wid, state in self.applied.items():
            self._set_visible(wid, self.shown and state.visible)

    def apply(self, cfg: dict) -> None:
        for wid, new in plan(cfg, self.overrides).items():
            old = self.applied.get(wid)
            win = self.windows[wid]
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

    def run(self) -> None:
        """Lancé par pywebview dans un thread une fois les fenêtres créées."""
        time.sleep(0.5)  # laisse les fenêtres natives apparaître (clics traversants)
        self.apply(self.initial or {})
        while True:
            time.sleep(POLL_S)
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

    windows = {}
    for wid, state in plan(initial or {}, overrides).items():
        windows[wid] = webview.create_window(
            window_title(wid),
            f"{url}{sep}widget={wid}",
            x=state.x,
            y=state.y,
            width=state.width,
            height=state.height,
            hidden=not state.visible,
            min_size=(40, 40),  # défaut pywebview 200×100 : plus grand qu'un widget
            frameless=True,
            easy_drag=True,
            on_top=True,
            transparent=True,
        )
    overlay = Overlay(windows, config_url, overrides, initial)
    webview.start(overlay.run)


def main() -> None:
    parser = argparse.ArgumentParser(description="LMU Assistant : overlay (une fenêtre par widget)")
    parser.add_argument("--url", default="http://localhost:8765/?mode=overlay")
    parser.add_argument("--no-click-through", action="store_true", help="garde les fenêtres cliquables/déplaçables")
    args = parser.parse_args()
    run(args.url, {"click_through": False} if args.no_click_through else {})


if __name__ == "__main__":
    main()
