"""Serveur local : page web, API et diffusion WebSocket des Snapshot."""

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .brakes import OVERHEAT_C, BrakesCalculator
from .config import ConfigStore
from .config_api import make_config_router
from .delta import DEFAULT_RECORDS_PATH, DeltaCalculator
from .fuel import FuelCalculator
from .laptimes import AVG_LAPS, LapTimesCalculator
from .network import router as network_router
from .relative import compute_relative
from .standings import compute_standings
from .paths import resource_dir
from .sources import DataSource

WEB_DIR = resource_dir() / "web"


class Broadcaster:
    def __init__(
        self,
        source: DataSource,
        hz: float,
        records_path: str | Path | None = DEFAULT_RECORDS_PATH,
        config_store: ConfigStore | None = None,
    ) -> None:
        self.source = source
        self.config_store = config_store
        self.period = 1.0 / hz
        self.clients: set[WebSocket] = set()
        self.latest: dict = {}
        self.fuel = FuelCalculator()
        self.delta = DeltaCalculator(records_path)
        self.laps = LapTimesCalculator()
        self.brakes = BrakesCalculator()

    def compute(self, snap):
        cfg = self.config_store.config if self.config_store else None
        snap = self.laps.update(self.delta.update(self.fuel.update(snap)), cfg.laptime_avg_laps if cfg else AVG_LAPS)
        snap = self.brakes.update(snap, cfg.brake_overheat_c if cfg else OVERHEAT_C)
        return compute_standings(compute_relative(snap))

    async def run(self) -> None:
        while True:
            self.latest = self.compute(self.source.read()).to_dict()
            await self.send_all({"type": "snapshot", "data": self.latest})
            await asyncio.sleep(self.period)

    async def send_all(self, message: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)


def create_app(
    source: DataSource,
    hz: float = 10.0,
    config_path: str | Path | None = None,
    records_path: str | Path | None = DEFAULT_RECORDS_PATH,
) -> FastAPI:
    config_store = ConfigStore(config_path)
    broadcaster = Broadcaster(source, hz, records_path, config_store)

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
