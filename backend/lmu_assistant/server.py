"""Serveur local : page web, API et diffusion WebSocket des Snapshot."""

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .brakes import OVERHEAT_C, BrakesCalculator
from .config import ConfigStore
from .config_api import make_config_router
from .damage import DamageCalculator
from .delta import DEFAULT_RECORDS_PATH, DeltaCalculator
from .fuel import FuelCalculator
from .history import DEFAULT_HISTORY_PATH, HistoryRecorder, HistoryStore
from .history_api import make_history_router
from .laptimes import AVG_LAPS, LapTimesCalculator
from .network import router as network_router
from .pitstop import PIT_LOSS_S, PitCalculator
from .relative import compute_relative
from .session import SessionCalculator
from .standings import compute_standings
from .paths import resource_dir
from .sources import DataSource

WEB_DIR = resource_dir() / "web"
log = logging.getLogger(__name__)


class Broadcaster:
    def __init__(
        self,
        source: DataSource,
        hz: float,
        records_path: str | Path | None = DEFAULT_RECORDS_PATH,
        config_store: ConfigStore | None = None,
        history: HistoryRecorder | None = None,
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
        self.pit = PitCalculator()
        self.session = SessionCalculator()
        self.damage = DamageCalculator()
        self.history = history

    def compute(self, snap):
        cfg = self.config_store.config if self.config_store else None
        snap = self.laps.update(self.delta.update(self.fuel.update(snap)), cfg.laptime_avg_laps if cfg else AVG_LAPS)
        snap = self.brakes.update(snap, cfg.brake_overheat_c if cfg else OVERHEAT_C)
        snap = compute_standings(compute_relative(snap))
        snap = self.pit.update(snap, cfg.pit_loss_s if cfg else PIT_LOSS_S)
        snap = self.damage.update(self.session.update(snap))
        if self.history is not None:
            try:
                self.history.update(snap)
            except Exception:  # l'historique ne doit jamais couper la diffusion
                log.exception("historique : enregistrement impossible")
        return snap

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
    history_path: str | Path | None = DEFAULT_HISTORY_PATH,
    history_mode: str = "auto",
) -> FastAPI:
    config_store = ConfigStore(config_path)
    history_store = HistoryStore(history_path or ":memory:")
    broadcaster = Broadcaster(source, hz, records_path, config_store, HistoryRecorder(history_store, history_mode))

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(broadcaster.run())
        yield
        task.cancel()
        source.close()
        history_store.close()

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
    app.include_router(make_history_router(history_store))
    app.state.history = history_store

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
