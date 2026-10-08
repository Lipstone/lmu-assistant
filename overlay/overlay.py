"""Overlay : fenêtre transparente, sans bordure, toujours au premier plan.

Elle affiche la page web locale en mode overlay. Lancer le serveur d'abord.
Le jeu doit être en mode « fenêtré sans bordure » pour que l'overlay soit visible.
"""

import argparse

import webview


def main() -> None:
    parser = argparse.ArgumentParser(description="LMU Assistant : overlay")
    parser.add_argument("--url", default="http://localhost:8765/?mode=overlay")
    parser.add_argument("--x", type=int, default=20)
    parser.add_argument("--y", type=int, default=20)
    parser.add_argument("--width", type=int, default=400)
    parser.add_argument("--height", type=int, default=420)
    args = parser.parse_args()

    webview.create_window(
        "LMU Assistant overlay",
        args.url,
        x=args.x,
        y=args.y,
        width=args.width,
        height=args.height,
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
