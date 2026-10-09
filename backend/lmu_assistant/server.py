"""Serveur local : page web, API et diffusion WebSocket des Snapshot."""

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path

import anyio
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
from .shift import SHIFT_RPM_PCT, ShiftCalculator
from .standings import compute_standings
from .strategy_api import make_strategy_router
from .paths import resource_dir
from .sources import DataSource

WEB_DIR = resource_dir() / "web"
log = logging.getLogger(__name__)
DEFAULT_HZ = 30.0

# Données brutes que les pages n'affichent pas (servent aux calculs du serveur, restent dans /api/snapshot) :
# jamais envoyées par le WebSocket, ce sont les plus lourdes (une entrée par voiture).
NOT_SENT = {"vehicles", "weather_forecast"}
# Toujours envoyé : état de la connexion au jeu, en-tête de la page et heure d'envoi (ms, horloge du PC).
COMMON_KEYS = ("connected", "source", "session", "track", "car", "ts")
# Fenêtre d'overlay d'un seul widget (/ws?widget=<id>) : seulement les champs que son rendu lit (web/app.js).
WIDGET_KEYS = {
    "lap": ("lap", "position", "laps", "current_lap_s", "lap_invalid", "last_lap_s", "best_lap_s"),
    "delta": ("delta",),
    "fuel": ("fuel", "energy", "fuel_l", "fuel_capacity_l", "virtual_energy_pct"),
    "car": ("speed_kmh", "gear", "rpm"),
    "tyres": ("wheels",),
    "brakes": ("brakes", "wheels"),
    "relative": ("relative",),
    "standings": ("standings",),
    "pit": ("pit", "lap"),
    "session": ("session_info",),
    "damage": ("damage",),
    "inputs": ("throttle", "brake", "clutch", "steering", "steering_range_deg", "abs_active", "tc_active"),
    "stint": ("stint",),
    "weather": ("weather",),
    "shift": ("shift",),
}


class Client:
    """Un WebSocket ouvert. Les images (snapshot) ne s'empilent jamais : si la page n'a pas fini de recevoir
    la précédente, la nouvelle la remplace (on n'envoie que la plus récente, la latence reste celle d'une image).
    Les autres messages (config) sont tous envoyés, dans l'ordre."""

    def __init__(self, ws: WebSocket, keys: tuple[str, ...] | None = None, snapshots: bool = True) -> None:
        self.ws = ws
        self.keys = keys  # None : tous les champs (sauf NOT_SENT)
        self.snapshots = snapshots
        self.snapshot: str | None = None
        self.messages: list[str] = []
        self.ready = asyncio.Event()

    def push_snapshot(self, text: str) -> None:
        if self.snapshots:
            self.snapshot = text
            self.ready.set()

    def push(self, text: str) -> None:
        self.messages.append(text)
        self.ready.set()

    async def run(self) -> None:
        while True:
            await self.ready.wait()
            self.ready.clear()
            while self.messages:
                await self.ws.send_text(self.messages.pop(0))
            text, self.snapshot = self.snapshot, None
            if text is not None:
                await self.ws.send_text(text)


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
        self.clients: set[Client] = set()
        self.latest: dict = {}
        self.fuel = FuelCalculator()
        self.delta = DeltaCalculator(records_path)
        self.laps = LapTimesCalculator()
        self.brakes = BrakesCalculator()
        self.pit = PitCalculator()
        self.session = SessionCalculator()
        self.weather = WeatherCalculator()
        self.shift = ShiftCalculator()
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
        snap = self.shift.update(snap, cfg.shift_rpm_pct if cfg else SHIFT_RPM_PCT, cfg.shift_use_table if cfg else True)
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
            self.latest["ts"] = round(time.time() * 1000)
            self.publish(self.latest)
            # Cadence régulière : le temps de calcul et d'envoi est déduit de l'attente.
            next_t = max(next_t + self.period, loop.time())
            await asyncio.sleep(next_t - loop.time())

    def publish(self, data: dict) -> None:
        """Donne l'image à chaque client ; le JSON est fait une fois par jeu de champs, pas par client."""
        texts: dict = {}
        for client in list(self.clients):
            if not client.snapshots:
                continue
            if client.keys not in texts:
                part = ({k: v for k, v in data.items() if k not in NOT_SENT} if client.keys is None
                        else {k: data[k] for k in client.keys if k in data})
                texts[client.keys] = json.dumps({"type": "snapshot", "data": part}, separators=(",", ":"))
            client.push_snapshot(texts[client.keys])

    async def send_all(self, message: dict) -> None:
        text = json.dumps(message, separators=(",", ":"))
        for client in list(self.clients):
            client.push(text)


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
        """`?widget=<id>` : seulement les champs de ce widget (fenêtre d'overlay) ;
        `?snapshots=0` : seulement les messages de configuration (page des réglages)."""
        await ws.accept()
        widget = ws.query_params.get("widget")
        keys = COMMON_KEYS + WIDGET_KEYS[widget] if widget in WIDGET_KEYS else None
        client = Client(ws, keys, ws.query_params.get("snapshots") != "0")
        broadcaster.clients.add(client)
        try:
            # Envoi et réception en parallèle ; le premier qui s'arrête (page fermée, envoi impossible) arrête l'autre.
            async with anyio.create_task_group() as tg:
                async def send() -> None:
                    with contextlib.suppress(Exception):
                        await client.run()
                    tg.cancel_scope.cancel()

                tg.start_soon(send)
                with contextlib.suppress(WebSocketDisconnect):
                    while True:
                        await ws.receive_text()  # garde la connexion ouverte
                tg.cancel_scope.cancel()
        finally:
            broadcaster.clients.discard(client)

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
