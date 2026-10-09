import argparse

import uvicorn

from .config import ConfigStore
from .network import lan_urls
from .server import create_app
from .sources import get_source


def build_parser(description: str = "LMU Assistant : serveur local") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--source", choices=["mock", "lmu", "replay"], default="lmu")
    parser.add_argument("--host", default=None,
                        help="0.0.0.0 = accessible depuis le réseau local (défaut : réglage lan_access, sinon 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--hz", type=float, default=None, help="fréquence d'envoi aux clients (défaut : réglage refresh_hz, 30/s)")
    parser.add_argument("--config", default=None, help="fichier de configuration JSON (défaut : data/config.json)")
    parser.add_argument("--history", choices=["auto", "on", "off"], default="auto",
                        help="historique des tours (data/history.sqlite) : auto = lecture du jeu seulement")
    parser.add_argument("--history-file", default=None, help="base de l'historique (défaut : data/history.sqlite)")
    rec = parser.add_argument_group("enregistrement / relecture")
    rec.add_argument("--record", nargs="?", const="", metavar="CHEMIN",
                     help="enregistre la session (défaut : data/recordings/<date>_<source>.jsonl.gz)")
    rec.add_argument("--file", help="fichier à rejouer (avec --source replay)")
    rec.add_argument("--speed", type=float, default=1.0, help="vitesse de relecture")
    rec.add_argument("--loop", action="store_true", help="rejoue en boucle")
    return parser


def resolve_host(args: argparse.Namespace) -> str:
    """Adresse d'écoute : --host s'il est donné, sinon selon le réglage « accès réseau local ».

    Écouter seulement sur 127.0.0.1 évite la demande d'autorisation du pare-feu Windows au lancement.
    """
    if args.host is None:
        args.host = "0.0.0.0" if ConfigStore(args.config).config.lan_access else "127.0.0.1"
    return args.host


def build_app(parser: argparse.ArgumentParser, args: argparse.Namespace):
    resolve_host(args)
    if args.source == "replay":
        if not args.file:
            parser.error("--source replay demande --file CHEMIN")
        source = get_source("replay", path=args.file, speed=args.speed, loop=args.loop)
    else:
        source = get_source(args.source)
    if args.record is not None:
        from .sources.recording import RecordingSource

        source = RecordingSource(source, args.record or None)
        print(f"Enregistrement : {source.path}")

    kw = {"history_path": args.history_file} if args.history_file else {}
    app = create_app(source, hz=args.hz, config_path=args.config, history_mode=args.history, **kw)
    app.state.port, app.state.host = args.port, args.host
    print(f"LMU Assistant : http://localhost:{args.port}  (source : {args.source})")
    for url in lan_urls(args.port, args.host):
        print(f"  Réseau local : {url}  (QR code : http://localhost:{args.port}/connect.html)")
    return app


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    app = build_app(parser, args)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
