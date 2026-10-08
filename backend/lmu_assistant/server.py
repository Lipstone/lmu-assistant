"""Serveur local : page web, API et diffusion WebSocket des Snapshot."""

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .network import router as network_router
from .sources import DataSource

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


class Broadcaster:
    def __init__(self, source: DataSource, hz: float) -> None:
        self.source = source
        self.period = 1.0 / hz
        self.clients: set[WebSocket] = set()
        self.latest: dict = {}

    async def run(self) -> None:
        while True:
            self.latest = self.source.read().to_dict()
            message = {"type": "snapshot", "data": self.latest}
            for ws in list(self.clients):
                try:
                    await ws.send_json(message)
                except Exception:
                    self.clients.discard(ws)
            await asyncio.sleep(self.period)


def create_app(source: DataSource, hz: float = 10.0) -> FastAPI:
    broadcaster = Broadcaster(source, hz)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(broadcaster.run())
        yield
        task.cancel()
        source.close()

    app = FastAPI(title="LMU Assistant", lifespan=lifespan)
    app.state.source = source
    app.include_router(network_router)  # /api/info, /api/qr.svg

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return broadcaster.latest

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        broadcaster.clients.add(ws)
        try:
            while True:
                await ws.receive_text()  # garde la connexion ouverte
        except WebSocketDisconnect:
            broadcaster.clients.discard(ws)

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
