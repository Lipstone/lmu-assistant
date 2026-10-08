"""Point d'entrée de l'exécutable LMU-Assistant : serveur + overlay en un seul lancement.

Le serveur tourne dans un thread ; l'overlay (pywebview) occupe le thread principal.
Fermer l'overlay arrête le serveur. Avec --no-overlay, le serveur tourne jusqu'à Ctrl+C.
"""

import sys
import threading
import time
import webbrowser

import uvicorn

from .__main__ import build_app, build_parser

START_TIMEOUT_S = 15.0


def start_server(app, host: str, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, name="serveur", daemon=True)
    thread.start()
    deadline = time.monotonic() + START_TIMEOUT_S
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise SystemExit(f"Le serveur n'a pas démarré (port {port} déjà utilisé ?)")
        time.sleep(0.05)
    return server, thread


def main(argv: list[str] | None = None) -> None:
    parser = build_parser("LMU Assistant : serveur + overlay")
    parser.add_argument("--no-overlay", action="store_true", help="serveur et page web seulement")
    parser.add_argument("--browser", action="store_true", help="ouvre aussi la page web dans le navigateur")
    args = parser.parse_args(argv)

    app = build_app(parser, args)
    server, thread = start_server(app, args.host, args.port)
    local = f"http://localhost:{args.port}"
    if args.browser:
        webbrowser.open(local)

    try:
        if not args.no_overlay:
            try:
                from .overlay import run as run_overlay

                run_overlay(f"{local}/?mode=overlay")  # bloque jusqu'à la fermeture de l'overlay
                return
            except Exception as exc:  # pywebview absent ou pas d'affichage
                print(f"[overlay] indisponible ({exc}) : page web seulement", file=sys.stderr)
        print("Ctrl+C pour quitter.")
        while thread.is_alive():
            thread.join(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(5)


if __name__ == "__main__":
    main()
