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
    return f"{TITLE} - {widget_id}"  # titre unique par fenêtre


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


# --- Transparence et clics traversants (Windows uniquement, via l'API Win32) ----
# pywebview (6.x) rend la page WebView2 transparente mais laisse le fond de la fenêtre WinForms
# (gris clair « Control ») : ce sont les zones blanches derrière les widgets. On peint ce fond en noir
# et on active la transparence par pixel de DWM (DwmEnableBlurBehindWindow avec une région vide :
# aucun flou, seulement le canal alpha), comme le font Tauri/winit pour leurs fenêtres transparentes.
# Mode « colorkey » de secours : le fond de la fenêtre prend une couleur clé rendue invisible par Windows
# (les zones vides deviennent transparentes, un fond de widget semi-transparent devient opaque).
# Clics traversants : pywebview n'a pas d'option, on ajoute WS_EX_TRANSPARENT au style étendu.
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
LWA_COLORKEY, LWA_ALPHA = 0x1, 0x2
DWM_BB_ENABLE, DWM_BB_BLURREGION = 0x1, 0x2
COLOR_KEY = (1, 0, 1)  # couleur clé du mode colorkey (quasi noire : bords du texte sans halo clair)


def ex_style(style: int, click_through: bool, transparency: str) -> int:
    """Style étendu voulu : fenêtre « layered » pour les clics traversants et pour la couleur clé."""
    layered = click_through or transparency == "colorkey"
    style = style | WS_EX_LAYERED if layered else style & ~WS_EX_LAYERED
    return style | WS_EX_TRANSPARENT if click_through else style & ~WS_EX_TRANSPARENT


def _on_gui_thread(form, fn) -> None:
    """Exécute `fn` dans le thread de l'interface WinForms (propriétés .NET de la fenêtre)."""
    from System import Action  # pythonnet, installé avec pywebview sous Windows

    if form.InvokeRequired:
        form.Invoke(Action(fn))
    else:
        fn()


def set_native_style(win, click_through: bool, transparency: str = "alpha") -> bool:
    """Applique transparence et clics traversants à la fenêtre native. False si elle n'existe pas encore."""
    if sys.platform != "win32":
        if click_through:
            warn("clics traversants non pris en charge hors Windows")
        return True
    form = getattr(win, "native", None)
    if form is None:
        return False

    def apply() -> None:
        import ctypes
        from ctypes import wintypes

        from System.Drawing import Color

        user32, dwmapi, gdi32 = ctypes.windll.user32, ctypes.windll.dwmapi, ctypes.windll.gdi32

        class DWM_BLURBEHIND(ctypes.Structure):
            _fields_ = [
                ("dwFlags", wintypes.DWORD),
                ("fEnable", wintypes.BOOL),
                ("hRgnBlur", wintypes.HANDLE),
                ("fTransitionOnMaximized", wintypes.BOOL),
            ]

        hwnd = ctypes.c_void_p(form.Handle.ToInt64())
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        user32.SetLayeredWindowAttributes.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
        gdi32.CreateRectRgn.restype = wintypes.HANDLE
        dwmapi.DwmEnableBlurBehindWindow.argtypes = [ctypes.c_void_p, ctypes.POINTER(DWM_BLURBEHIND)]

        colorkey = transparency == "colorkey"
        form.BackColor = Color.FromArgb(255, *COLOR_KEY) if colorkey else Color.Black
        style = ex_style(user32.GetWindowLongW(hwnd, GWL_EXSTYLE), click_through, transparency)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        if colorkey:
            r, g, b = COLOR_KEY
            user32.SetLayeredWindowAttributes(hwnd, r | g << 8 | b << 16, 255, LWA_COLORKEY)
        elif style & WS_EX_LAYERED:
            user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)  # sans cet appel, fenêtre invisible
        region = gdi32.CreateRectRgn(0, 0, -1, -1)
        bb = DWM_BLURBEHIND(DWM_BB_ENABLE | DWM_BB_BLURREGION, not colorkey, region, False)
        dwmapi.DwmEnableBlurBehindWindow(hwnd, ctypes.byref(bb))
        gdi32.DeleteObject(region)
        form.Invalidate(True)

    try:
        _on_gui_thread(form, apply)
    except Exception as exc:
        warn(f"transparence / clics traversants impossibles : {exc}")
    return True


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
    transparency: str = "alpha"


def plan(cfg: dict, overrides: dict | None = None) -> dict[str, WindowState]:
    """État voulu de chaque fenêtre (une par widget) d'après la config du serveur."""
    try:
        config = AppConfig.model_validate(cfg)
    except ValueError as exc:  # serveur d'une autre version, etc.
        warn(f"config refusée, valeurs par défaut : {exc}")
        config = AppConfig()
    # En mode placement, les fenêtres doivent recevoir la souris.
    click = (overrides or {}).get("click_through", config.window.click_through) and not config.placement
    mode = config.window.transparency
    return {
        w.id: WindowState(w.x, w.y, *window_size(w.id, w.scale), w.visible, click, mode) for w in config.widgets
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
        self.native_pending: set[str] = set()  # transparence / clics traversants pas encore appliqués
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
                native = (new.click_through, new.transparency)
                if old is None or wid in self.native_pending or native != (old.click_through, old.transparency):
                    if set_native_style(win, *native):
                        self.native_pending.discard(wid)
                    else:  # fenêtre native pas encore créée : on réessaiera
                        self.native_pending.add(wid)
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
        time.sleep(0.5)  # laisse les fenêtres natives apparaître (transparence, clics traversants)
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
            background_color="#000000",
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
