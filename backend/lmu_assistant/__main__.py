import argparse

import uvicorn

from .server import create_app
from .sources import get_source


def main() -> None:
    parser = argparse.ArgumentParser(description="LMU Assistant : serveur local")
    parser.add_argument("--source", choices=["mock", "lmu"], default="lmu")
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = accessible depuis le réseau local")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--hz", type=float, default=10.0, help="fréquence d'envoi aux clients")
    args = parser.parse_args()

    app = create_app(get_source(args.source), hz=args.hz)
    print(f"LMU Assistant : http://localhost:{args.port}  (source : {args.source})")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
