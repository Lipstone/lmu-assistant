"""Historique des tours (F20) : chaque tour terminé est enregistré dans une base SQLite.

`HistoryRecorder.update` reçoit chaque Snapshot après les calculs (temps au tour F04, session F10…). Pendant
un tour, il relève le carburant, l'énergie, l'usure, l'arrêt aux stands et une trace (temps et vitesse à chaque
200e du tour) ; quand le temps du tour est publié (F04), il écrit une ligne dans `laps` :

- temps, secteurs (`mLastSector1`, `mLastSector2`), tour valide / stand / invalidé ;
- carburant et énergie au début et à la fin, consommation (sans ravitaillement pendant le tour) ;
- usure, températures et pressions des pneus à la fin du tour, pneus changés pendant le tour ;
- arrêt au stand (voiture à l'arrêt dans les stands, ou ravitaillement) ;
- conditions : températures air / piste, pluie, piste mouillée, grip ; position, pilote, chocs.

Le recorder garde aussi les tours de la session en mémoire (même sans écrire dans la base) pour le widget
**Relais** (F21, F22) : `snapshot.stint` = résumé du relais en cours (`analysis.py`).

Une **session** (table `sessions`) regroupe les tours d'une même session de jeu, piste et voiture ; elle est
créée au premier tour enregistré. Par défaut seule la lecture du jeu (`lmu`) est enregistrée : les données
simulées ou rejouées ne remplissent pas l'historique (`--history on` pour tout enregistrer, `off` pour rien).

Base : `data/history.sqlite` (à côté de l'exe). Lecture par l'API `/api/history/…` (`history_api.py`).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import analysis
from .model import Snapshot, StintInfo
from .paths import data_dir

DEFAULT_HISTORY_PATH = data_dir() / "history.sqlite"
TRACE_POINTS = 200  # trace : temps et vitesse à chaque 200e du tour (~70 m au Mans)
REFUEL_L = 0.5  # hausse du carburant (ou de 0,5 % d'énergie) = ravitaillement
TYRE_CHANGE_WEAR = 0.02  # hausse de l'usure (gomme restante) = pneus changés
STOPPED_KMH = 2.0
STOPPED_S = 1.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    source TEXT,
    session TEXT,
    track TEXT,
    car TEXT,
    car_class TEXT,
    driver TEXT
);
CREATE TABLE IF NOT EXISTS laps (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    lap INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    session_time_s REAL,
    time_s REAL,
    s1 REAL, s2 REAL, s3 REAL,
    valid INTEGER, pit INTEGER, invalid INTEGER,
    stop INTEGER, refuel INTEGER, tyres_changed INTEGER,
    fuel_start REAL, fuel_end REAL, fuel_used REAL,
    energy_start REAL, energy_end REAL, energy_used REAL,
    wear TEXT, tyre_temp TEXT, pressure TEXT,
    air_temp REAL, track_temp REAL, rain REAL, wetness REAL, grip INTEGER,
    position INTEGER, driver TEXT, impacts INTEGER,
    trace TEXT
);
CREATE INDEX IF NOT EXISTS laps_session ON laps(session_id, lap);
CREATE TABLE IF NOT EXISTS conditions (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    session_time_s REAL,
    recorded_at TEXT NOT NULL,
    air_temp REAL, track_temp REAL, rain REAL, wetness REAL, grip INTEGER, cloud INTEGER
);
CREATE INDEX IF NOT EXISTS conditions_session ON conditions(session_id, session_time_s);
"""
CONDITIONS_EVERY_S = 30.0  # relevé des conditions (F28) toutes les 30 s de session
CONDITION_COLUMNS = ("session_id", "session_time_s", "recorded_at", "air_temp", "track_temp", "rain", "wetness",
                     "grip", "cloud")

LAP_COLUMNS = (
    "session_id", "lap", "recorded_at", "session_time_s", "time_s", "s1", "s2", "s3", "valid", "pit", "invalid",
    "stop", "refuel", "tyres_changed", "fuel_start", "fuel_end", "fuel_used", "energy_start", "energy_end",
    "energy_used", "wear", "tyre_temp", "pressure", "air_temp", "track_temp", "rain", "wetness", "grip",
    "position", "driver", "impacts", "trace",
)
JSON_COLUMNS = ("wear", "tyre_temp", "pressure", "trace")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class HistoryStore:
    """Base SQLite de l'historique. Utilisable depuis plusieurs fils (verrou)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_HISTORY_PATH
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        with self._lock:
            self.db.close()

    # --- écriture -------------------------------------------------------------

    def new_session(self, **values: Any) -> int:
        cols = ("started_at", "source", "session", "track", "car", "car_class", "driver")
        values.setdefault("started_at", _now())
        with self._lock:
            cur = self.db.execute(
                f"INSERT INTO sessions ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [values.get(c) for c in cols],
            )
            self.db.commit()
            return int(cur.lastrowid)

    def add_lap(self, session_id: int, **values: Any) -> int:
        values["session_id"] = session_id
        values.setdefault("recorded_at", _now())
        row = [json.dumps(values.get(c)) if c in JSON_COLUMNS and values.get(c) is not None else values.get(c)
               for c in LAP_COLUMNS]
        with self._lock:
            cur = self.db.execute(
                f"INSERT INTO laps ({', '.join(LAP_COLUMNS)}) VALUES ({', '.join('?' * len(LAP_COLUMNS))})", row
            )
            self.db.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (values["recorded_at"], session_id))
            self.db.commit()
            return int(cur.lastrowid)

    def add_conditions(self, session_id: int, **values: Any) -> None:
        values["session_id"] = session_id
        values.setdefault("recorded_at", _now())
        with self._lock:
            self.db.execute(
                f"INSERT INTO conditions ({', '.join(CONDITION_COLUMNS)}) VALUES ({', '.join('?' * len(CONDITION_COLUMNS))})",
                [values.get(c) for c in CONDITION_COLUMNS],
            )
            self.db.commit()

    def conditions(self, session_id: int) -> list[dict]:
        with self._lock:
            rows = self.db.execute(
                "SELECT * FROM conditions WHERE session_id = ? ORDER BY session_time_s, id", (session_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: int) -> bool:
        with self._lock:
            cur = self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self.db.commit()
            return cur.rowcount > 0

    # --- lecture --------------------------------------------------------------

    def sessions(self) -> list[dict]:
        """Sessions, la plus récente d'abord, avec le nombre de tours et le meilleur tour valide."""
        with self._lock:
            rows = self.db.execute(
                """SELECT s.*, COUNT(l.id) AS laps,
                          MIN(CASE WHEN l.valid THEN l.time_s END) AS best_s,
                          SUM(CASE WHEN l.valid THEN 1 ELSE 0 END) AS valid_laps
                   FROM sessions s LEFT JOIN laps l ON l.session_id = s.id
                   GROUP BY s.id ORDER BY s.id DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def session(self, session_id: int) -> dict | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def laps(self, session_id: int, with_trace: bool = False) -> list[dict]:
        with self._lock:
            rows = self.db.execute("SELECT * FROM laps WHERE session_id = ? ORDER BY lap, id", (session_id,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            for c in JSON_COLUMNS:
                if c == "trace" and not with_trace:
                    d.pop(c, None)
                elif d.get(c) is not None:
                    d[c] = json.loads(d[c])
            for c in ("valid", "pit", "invalid", "stop", "refuel", "tyres_changed"):
                d[c] = bool(d[c])
            result.append(d)
        return result

    def lap(self, lap_id: int) -> dict | None:
        with self._lock:
            row = self.db.execute("SELECT session_id FROM laps WHERE id = ?", (lap_id,)).fetchone()
        if not row:
            return None
        return next((lap for lap in self.laps(row["session_id"], with_trace=True) if lap["id"] == lap_id), None)


@dataclass
class _LapStats:
    """Relevés pendant un tour."""

    lap: int
    fuel_start: float | None = None
    fuel_end: float | None = None
    energy_start: float | None = None
    energy_end: float | None = None
    refuel: bool = False
    tyres_changed: bool = False
    stop: bool = False
    stopped_since: float | None = None
    impacts_start: int = 0
    end: dict = field(default_factory=dict)  # pneus et conditions au dernier relevé du tour
    times: list[float | None] = field(default_factory=lambda: [None] * TRACE_POINTS)
    speeds: list[float | None] = field(default_factory=lambda: [None] * TRACE_POINTS)


class HistoryRecorder:
    """Enregistre les tours terminés dans un HistoryStore. `mode` : auto (source lmu seulement), on, off."""

    def __init__(self, store: HistoryStore | None, mode: str = "auto") -> None:
        self.store = store
        self.mode = mode
        self._key: tuple | None = None
        self.session_id: int | None = None
        self._laps: dict[int, _LapStats] = {}
        self._written: set[int] = set()
        self._prev: Snapshot | None = None
        self.session_laps: list[dict] = []  # tours de la session (aussi sans base), pour le relais en cours
        self._last_conditions: float | None = None
        self._stint: StintInfo = StintInfo()

    def enabled(self, snap: Snapshot) -> bool:
        if self.store is None or self.mode == "off":
            return False
        return self.mode == "on" or snap.source == "lmu"

    def _sample(self, snap: Snapshot) -> None:
        st = self._laps.get(snap.lap)
        if st is None:
            st = self._laps[snap.lap] = _LapStats(snap.lap, impacts_start=snap.damage.impacts)
            st.fuel_start = snap.fuel_l
            st.energy_start = snap.virtual_energy_pct
            for old in [k for k in self._laps if k < snap.lap - 3]:
                del self._laps[old]
        prev = self._prev
        if prev is not None and prev.connected:
            if snap.fuel_l > prev.fuel_l + REFUEL_L:
                st.refuel = True
            if snap.virtual_energy_pct is not None and prev.virtual_energy_pct is not None \
                    and snap.virtual_energy_pct > prev.virtual_energy_pct + REFUEL_L:
                st.refuel = True
            if any(w.wear > p.wear + TYRE_CHANGE_WEAR for w, p in zip(snap.wheels, prev.wheels)):
                st.tyres_changed = True
        if st.refuel and st.fuel_start is not None and snap.fuel_l > st.fuel_start:
            st.fuel_start = snap.fuel_l  # le tour reprend après le plein : conso non comptée
        st.fuel_end = snap.fuel_l
        st.end = self._end_values(snap)
        st.energy_end = snap.virtual_energy_pct
        if snap.in_pits and snap.speed_kmh < STOPPED_KMH:
            st.stopped_since = st.stopped_since if st.stopped_since is not None else snap.current_lap_s
            if snap.current_lap_s - st.stopped_since >= STOPPED_S:
                st.stop = True
        else:
            st.stopped_since = None
        if snap.lap_fraction is not None:
            i = min(TRACE_POINTS - 1, int(snap.lap_fraction * TRACE_POINTS))
            if st.times[i] is None:
                st.times[i] = round(snap.current_lap_s, 3)
                st.speeds[i] = round(snap.speed_kmh, 1)

    def _ensure_session(self, snap: Snapshot) -> None:
        if self.session_id is None:
            me = next((v for v in snap.vehicles if v.is_player), None)
            self.session_id = self.store.new_session(
                source=snap.source, session=snap.session, track=snap.track, car=snap.car,
                car_class=me.car_class if me else "", driver=me.driver if me else "",
            )

    def _conditions(self, snap: Snapshot) -> None:
        """Évolution des conditions (F28) : un relevé toutes les 30 s de session."""
        t = snap.session_elapsed_s
        if t is None or (snap.track_temp_c is None and snap.raining is None):
            return
        if self._last_conditions is not None and 0 <= t - self._last_conditions < CONDITIONS_EVERY_S:
            return
        self._last_conditions = t
        self._ensure_session(snap)
        self.store.add_conditions(
            self.session_id, session_time_s=round(t, 1), air_temp=snap.air_temp_c, track_temp=snap.track_temp_c,
            rain=snap.raining, wetness=snap.wetness, grip=snap.track_grip, cloud=snap.cloud_coverage,
        )

    @staticmethod
    def _end_values(snap: Snapshot) -> dict:
        si = snap.session_info
        return dict(
            wear=[round(w.wear, 4) for w in snap.wheels],
            tyre_temp=[None if w.temp_c is None else round(sum(w.temp_c) / 3, 1) for w in snap.wheels],
            pressure=[None if w.pressure_kpa is None else round(w.pressure_kpa, 1) for w in snap.wheels],
            air_temp=si.air_temp_c, track_temp=si.track_temp_c,
            rain=snap.raining, wetness=snap.wetness, grip=snap.track_grip,
            position=snap.position,
        )

    def _write(self, snap: Snapshot, entry) -> None:
        st = self._laps.get(entry.lap)
        me = next((v for v in snap.vehicles if v.is_player), None)
        if self.enabled(snap):
            self._ensure_session(snap)
        s1 = snap.last_sector1_s
        s2 = s3 = None
        if s1 is not None and snap.last_sector2_s is not None and entry.time_s is not None:
            s2 = round(snap.last_sector2_s - s1, 3)
            s3 = round(entry.time_s - snap.last_sector2_s, 3)
        values: dict[str, Any] = dict(
            lap=entry.lap, session_time_s=snap.session_elapsed_s, time_s=entry.time_s, s1=s1, s2=s2, s3=s3,
            valid=entry.valid, pit=entry.pit, invalid=entry.invalid, driver=me.driver if me else "",
        )
        values.update(st.end if st is not None and st.end else self._end_values(snap))
        if st is not None:
            values.update(
                stop=st.stop or st.refuel, refuel=st.refuel, tyres_changed=st.tyres_changed,
                fuel_start=st.fuel_start, fuel_end=st.fuel_end, energy_start=st.energy_start,
                energy_end=st.energy_end, impacts=max(0, snap.damage.impacts - st.impacts_start),
            )
            if st.fuel_start is not None and st.fuel_end is not None and not st.refuel:
                values["fuel_used"] = round(st.fuel_start - st.fuel_end, 3)
            if st.energy_start is not None and st.energy_end is not None and not st.refuel:
                values["energy_used"] = round(st.energy_start - st.energy_end, 3)
            if sum(t is not None for t in st.times) >= TRACE_POINTS // 2:
                values["trace"] = {"t": st.times, "v": st.speeds}
        if self.enabled(snap):
            self.store.add_lap(self.session_id, **values)
        self.session_laps.append(values)
        self._stint = self._summary()

    def _summary(self) -> StintInfo:
        stints = analysis.stints(self.session_laps)
        if not stints:
            return StintInfo()
        s = stints[-1]
        info = StintInfo(
            number=s["number"], start_lap=s["start_lap"], laps=s["laps"], time_s=s["duration_s"],
            avg_s=s["avg_s"], best_s=s["best_s"], stdev_s=s["stdev_s"], deg_s_per_lap=s["deg_s_per_lap"],
            fuel_per_lap=s["fuel_per_lap"], energy_per_lap=s["energy_per_lap"],
            tyre_age_laps=None if s["tyre_age_start"] is None else s["tyre_age_start"] + s["laps"],
            laps_to_wear_limit=s["laps_to_wear_limit"],
        )
        wear = s["wear_end"]
        if wear and len(wear) == 4:
            i = min(range(4), key=lambda k: wear[k])
            info.worst_wheel = analysis.WHEELS[i]
            info.wear_left_pct = round(100 * wear[i], 1)
        if s["wear_per_lap"] and any(w is not None for w in s["wear_per_lap"]):
            info.wear_per_lap_pct = round(100 * max(w for w in s["wear_per_lap"] if w is not None), 2)
        return info

    def _live_stint(self, snap: Snapshot) -> StintInfo:
        """Relais en cours : résumé des tours terminés + tour en cours ; un arrêt pendant le tour en cours
        ouvre déjà le relais suivant."""
        st = self._laps.get(snap.lap)
        base = self._stint
        if st is not None and (st.stop or st.refuel) and base.start_lap != snap.lap:
            age = 0 if st.tyres_changed else (None if base.tyre_age_laps is None else base.tyre_age_laps)
            return StintInfo(number=base.number + 1, start_lap=snap.lap, laps=0,
                             time_s=round(snap.current_lap_s, 1), tyre_age_laps=age)
        info = StintInfo(**{k: getattr(base, k) for k in base.__dataclass_fields__})
        if info.number:
            info.time_s = round((base.time_s or 0.0) + snap.current_lap_s, 1)
        return info

    def update(self, snap: Snapshot) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.source, snap.session, snap.track, snap.car)
        if key != self._key:
            self._key = key
            self.session_id = None
            self._laps.clear()
            self._written.clear()
            self._prev = None
            self.session_laps = []
            self._stint = StintInfo()
            self._last_conditions = None
        # Tours terminés publiés par F04 : le temps est connu, on écrit avec les relevés du tour.
        for entry in sorted(snap.laps.recent, key=lambda e: e.lap):
            if entry.lap not in self._written and entry.time_s is not None:
                self._written.add(entry.lap)
                self._write(snap, entry)
        self._sample(snap)
        if self.enabled(snap):
            self._conditions(snap)
        self._prev = snap
        snap.stint = self._live_stint(snap)
        return snap
