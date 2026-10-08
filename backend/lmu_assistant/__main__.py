import argparse

import uvicorn

from .server import create_app
from .sources import get_source


def main() -> None:
    parser = argparse.ArgumentParser(description="LMU Assistant : serveur local")
    parser.add_argument("--source", choices=["mock", "lmu", "replay"], default="lmu")
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = accessible depuis le réseau local")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--hz", type=float, default=10.0, help="fréquence d'envoi aux clients")
    rec = parser.add_argument_group("enregistrement / relecture")
    rec.add_argument("--record", nargs="?", const="", metavar="CHEMIN",
                     help="enregistre la session (défaut : data/recordings/<date>_<source>.jsonl.gz)")
    rec.add_argument("--file", help="fichier à rejouer (avec --source replay)")
    rec.add_argument("--speed", type=float, default=1.0, help="vitesse de relecture")
    rec.add_argument("--loop", action="store_true", help="rejoue en boucle")
    args = parser.parse_args()

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

    app = create_app(source, hz=args.hz)
    print(f"LMU Assistant : http://localhost:{args.port}  (source : {args.source})")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
