"""Point d'entrée de l'exécutable LMU-Assistant : serveur + interface ingénieur + overlay en un seul lancement.

Le serveur tourne dans un thread ; les fenêtres Qt (interface ingénieur et widgets de l'overlay)
occupent le thread principal. L'interface ingénieur et l'overlay course sont indépendants : fermer la
fenêtre de l'interface laisse l'overlay tourner, « Quitter » dans l'icône de notification arrête tout.
Avec --no-window et --no-overlay, le serveur tourne jusqu'à Ctrl+C.

L'exécutable n'a pas de console : les messages vont dans data/lmu-assistant.log, à côté de l'exe.
"""

import argparse
import os
import sys
import threading
import time
import webbrowser

import uvicorn

from . import paths
from .__main__ import build_app, build_parser

START_TIMEOUT_S = 15.0
LOG_NAME = "lmu-assistant.log"


def redirect_output() -> None:
    """Exécutable sans console : sys.stdout et sys.stderr valent None, on les envoie dans un fichier."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = paths.data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / LOG_NAME, "w", encoding="utf-8", buffering=1)  # noqa: SIM115 (ouvert toute la vie de l'appli)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def unblock_exe() -> None:
    """Retire la marque « fichier téléchargé d'Internet » (flux Zone.Identifier) de l'exécutable.

    Sans elle, Windows ne redemande plus à chaque lancement s'il faut exécuter ce fichier
    (avertissement de sécurité « L'éditeur n'a pas pu être vérifié »). L'utilisateur a déjà accepté
    de lancer l'application une fois ; on ne fait rien hors de l'exécutable Windows.
    """
    if sys.platform != "win32" or not paths.is_frozen():
        return
    try:
        os.remove(f"{sys.executable}:Zone.Identifier")
        print("Exécutable débloqué : Windows ne demandera plus d'autorisation au lancement.")
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"Impossible de débloquer l'exécutable : {exc}", file=sys.stderr)


def alert(message: str) -> None:
    """Affiche une erreur : boîte de dialogue sous Windows (pas de console), sinon la sortie d'erreur."""
    print(message, file=sys.stderr)
    if sys.platform == "win32" and paths.is_frozen():
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "LMU Assistant", 0x10)


def start_server(app, host: str, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, name="serveur", daemon=True)
    thread.start()
    deadline = time.monotonic() + START_TIMEOUT_S
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise SystemExit(f"Le serveur n'a pas démarré (port {port} déjà utilisé ? L'application est peut-être déjà ouverte.)")
        time.sleep(0.05)
    return server, thread


def main(argv: list[str] | None = None) -> None:
    redirect_output()
    unblock_exe()
    parser = build_parser("LMU Assistant : serveur + interface + overlay")
    parser.add_argument("--no-overlay", action="store_true", help="sans les fenêtres de widgets en jeu")
    parser.add_argument("--no-window", action="store_true", help="sans la fenêtre de l'interface ingénieur")
    parser.add_argument("--browser", action="store_true", help="ouvre aussi la page web dans le navigateur")
    parser.add_argument("--quit-after", type=float, metavar="S", help=argparse.SUPPRESS)  # vérification CI de l'exe
    args = parser.parse_args(argv)

    app = build_app(parser, args)
    try:
        server, thread = start_server(app, args.host, args.port)
    except SystemExit as exc:
        alert(str(exc))
        raise
    local = f"http://localhost:{args.port}"
    if args.browser:
        webbrowser.open(local)

    try:
        if not (args.no_overlay and args.no_window):
            try:
                from .overlay import run as run_qt

                run_qt(  # bloque jusqu'à « Quitter » (ou la fermeture de l'interface sans overlay)
                    f"{local}/?mode=overlay",
                    quit_after=args.quit_after,
                    main_url=f"{local}/",  # sans overlay ni fenêtre au lancement : rouvrable par l'icône
                    show_main=not args.no_window,
                    widgets=not args.no_overlay,
                )
                return
            except Exception as exc:  # PySide6 absent ou pas d'affichage
                if args.quit_after:  # vérification de l'exécutable : les fenêtres doivent marcher
                    raise
                print(f"[fenêtres] indisponibles ({exc}) : page web dans le navigateur", file=sys.stderr)
                if not args.no_window and not args.browser:
                    webbrowser.open(local)
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
