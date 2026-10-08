"""Serveur local : page web, API et diffusion WebSocket des Snapshot."""

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .config import ConfigStore
from .config_api import make_config_router
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
            await self.send_all({"type": "snapshot", "data": self.latest})
            await asyncio.sleep(self.period)

    async def send_all(self, message: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)


def create_app(source: DataSource, hz: float = 10.0, config_path: str | Path | None = None) -> FastAPI:
    broadcaster = Broadcaster(source, hz)
    config_store = ConfigStore(config_path)

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

    async def config_changed(config) -> None:
        await broadcaster.send_all({"type": "config", "data": config.model_dump()})

    app.include_router(make_config_router(config_store, config_changed))

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
