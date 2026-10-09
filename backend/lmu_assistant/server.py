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
from .opponents import OpponentsCalculator
from .notes import NoteStore, make_notes_router
from .laptimes import AVG_LAPS, LapTimesCalculator
from .network import router as network_router
from .pitstop import PIT_LOSS_S, PitCalculator
from .relative import compute_relative
from .session import SessionCalculator
from .weather import WeatherCalculator
from .standings import compute_standings
from .strategy_api import make_strategy_router
from .paths import resource_dir
from .sources import DataSource

WEB_DIR = resource_dir() / "web"
log = logging.getLogger(__name__)
DEFAULT_HZ = 30.0


class Broadcaster:
    def __init__(
        self,
        source: DataSource,
        hz: float | None,
        records_path: str | Path | None = DEFAULT_RECORDS_PATH,
        config_store: ConfigStore | None = None,
        history: HistoryRecorder | None = None,
    ) -> None:
        self.source = source
        self.config_store = config_store
        self.hz = hz  # None : fréquence des réglages (refresh_hz), modifiable en direct
        self.clients: set[WebSocket] = set()
        self.latest: dict = {}
        self.fuel = FuelCalculator()
        self.delta = DeltaCalculator(records_path)
        self.laps = LapTimesCalculator()
        self.brakes = BrakesCalculator()
        self.pit = PitCalculator()
        self.session = SessionCalculator()
        self.weather = WeatherCalculator()
        self.damage = DamageCalculator()
        self.opponents = OpponentsCalculator()
        self.history = history

    def compute(self, snap):
        cfg = self.config_store.config if self.config_store else None
        snap = self.laps.update(self.delta.update(self.fuel.update(snap)), cfg.laptime_avg_laps if cfg else AVG_LAPS)
        snap = self.brakes.update(snap, cfg.brake_overheat_c if cfg else OVERHEAT_C)
        snap = compute_standings(compute_relative(self.opponents.update(snap)))
        snap = self.pit.update(snap, cfg.pit_loss_s if cfg else PIT_LOSS_S)
        snap = self.damage.update(self.weather.update(self.session.update(snap)))
        if self.history is not None:
            try:
                self.history.update(snap)
            except Exception:  # l'historique ne doit jamais couper la diffusion
                log.exception("historique : enregistrement impossible")
        return snap

    @property
    def period(self) -> float:
        cfg = self.config_store.config if self.config_store else None
        return 1.0 / (self.hz or (cfg.refresh_hz if cfg else DEFAULT_HZ))

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_t = loop.time()
        while True:
            self.latest = self.compute(self.source.read()).to_dict()
            await self.send_all({"type": "snapshot", "data": self.latest})
            # Cadence régulière : le temps de calcul et d'envoi est déduit de l'attente.
            next_t = max(next_t + self.period, loop.time())
            await asyncio.sleep(next_t - loop.time())

    async def send_all(self, message: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)


def create_app(
    source: DataSource,
    hz: float | None = None,
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
    note_store = NoteStore(history_store)
    app.include_router(make_history_router(history_store, note_store))
    app.include_router(make_notes_router(note_store))
    app.include_router(make_strategy_router(lambda: broadcaster.latest))
    app.state.history = history_store

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
