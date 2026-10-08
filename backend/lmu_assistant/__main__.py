import argparse

import uvicorn

from .network import lan_urls
from .server import create_app
from .sources import get_source


def build_parser(description: str = "LMU Assistant : serveur local") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--source", choices=["mock", "lmu", "replay"], default="lmu")
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = accessible depuis le réseau local")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--hz", type=float, default=10.0, help="fréquence d'envoi aux clients")
    parser.add_argument("--config", default=None, help="fichier de configuration JSON (défaut : data/config.json)")
    rec = parser.add_argument_group("enregistrement / relecture")
    rec.add_argument("--record", nargs="?", const="", metavar="CHEMIN",
                     help="enregistre la session (défaut : data/recordings/<date>_<source>.jsonl.gz)")
    rec.add_argument("--file", help="fichier à rejouer (avec --source replay)")
    rec.add_argument("--speed", type=float, default=1.0, help="vitesse de relecture")
    rec.add_argument("--loop", action="store_true", help="rejoue en boucle")
    return parser


def build_app(parser: argparse.ArgumentParser, args: argparse.Namespace):
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

    app = create_app(source, hz=args.hz, config_path=args.config)
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
