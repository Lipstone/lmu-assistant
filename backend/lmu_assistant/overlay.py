"""Overlay : fenêtre transparente, sans bordure, toujours au premier plan.

Elle affiche la page web locale en mode overlay. Lancer le serveur d'abord
(l'exécutable LMU-Assistant lance les deux ensemble, voir launcher.py).
Le jeu doit être en mode « fenêtré sans bordure » pour que l'overlay soit visible.

Configuration (T06) lue sur le serveur (GET /api/config, modifiable via /settings.html) :
- position/taille de la fenêtre, clics traversants (Windows) ;
- raccourci global afficher/masquer (paquet `keyboard`, optionnel).
Les changements sont relus toutes les 2 s et appliqués sans redémarrer.
"""

import argparse
import json
import sys
import time
import urllib.request
from urllib.parse import urlsplit

TITLE = "LMU Assistant overlay"
POLL_S = 2.0

DEFAULT_WINDOW = {"x": 20, "y": 20, "width": 400, "height": 420, "click_through": True}
DEFAULT_HOTKEY = "ctrl+shift+o"


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


def set_click_through(enabled: bool) -> None:
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
        hwnd = user32.FindWindowW(None, TITLE)
        if not hwnd:
            warn("fenêtre overlay introuvable pour les clics traversants")
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


class Overlay:
    def __init__(self, window, config_url: str, overrides: dict, initial: dict | None) -> None:
        self.window = window
        self.config_url = config_url
        self.overrides = overrides  # options de ligne de commande, prioritaires
        self.visible = True
        self.applied: dict = {}
        self.hotkey = Hotkey(self.toggle)
        self.initial = initial

    def toggle(self) -> None:
        if self.visible:
            self.window.hide()
        else:
            self.window.show()
        self.visible = not self.visible

    def apply(self, cfg: dict) -> None:
        win = {**DEFAULT_WINDOW, **cfg.get("window", {}), **self.overrides}
        old = self.applied
        if old and (win["x"], win["y"]) != (old["x"], old["y"]):
            self.window.move(win["x"], win["y"])
        if old and (win["width"], win["height"]) != (old["width"], old["height"]):
            self.window.resize(win["width"], win["height"])
        if win["click_through"] != old.get("click_through"):
            set_click_through(win["click_through"])
        self.applied = win
        self.hotkey.set(cfg.get("hotkey") or DEFAULT_HOTKEY)

    def run(self) -> None:
        """Lancé par pywebview dans un thread une fois la fenêtre créée."""
        time.sleep(0.5)  # laisse la fenêtre native apparaître (clics traversants)
        cfg = self.initial or {}
        self.applied = {**DEFAULT_WINDOW, **cfg.get("window", {}), **self.overrides, "click_through": None}
        self.apply(cfg)
        while True:
            time.sleep(POLL_S)
            cfg = fetch_config(self.config_url)
            if cfg is not None:
                self.apply(cfg)


def run(url: str, overrides: dict | None = None) -> None:
    """Ouvre la fenêtre overlay sur `url` ; bloque jusqu'à sa fermeture (thread principal)."""
    import webview  # pywebview : dépendance optionnelle `overlay`

    overrides = overrides or {}
    parts = urlsplit(url)
    config_url = f"{parts.scheme}://{parts.netloc}/api/config"
    initial = fetch_config(config_url)
    win = {**DEFAULT_WINDOW, **((initial or {}).get("window", {})), **overrides}

    window = webview.create_window(
        TITLE,
        url,
        x=win["x"],
        y=win["y"],
        width=win["width"],
        height=win["height"],
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=True,
    )
    overlay = Overlay(window, config_url, overrides, initial)
    webview.start(overlay.run)


def main() -> None:
    parser = argparse.ArgumentParser(description="LMU Assistant : overlay")
    parser.add_argument("--url", default="http://localhost:8765/?mode=overlay")
    parser.add_argument("--x", type=int, help="remplace la position de la config serveur")
    parser.add_argument("--y", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--no-click-through", action="store_true", help="garde la fenêtre cliquable/déplaçable")
    args = parser.parse_args()

    overrides = {k: getattr(args, k) for k in ("x", "y", "width", "height") if getattr(args, k) is not None}
    if args.no_click_through:
        overrides["click_through"] = False
    run(args.url, overrides)


if __name__ == "__main__":
    main()
