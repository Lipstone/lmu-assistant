"""Delta en direct (F03) : écart du tour en cours avec un tour de référence, au même endroit de la piste.

Pendant chaque tour, on note le temps écoulé en fonction de l'avancement dans le tour (`lap_fraction`).
Au passage de la ligne, un tour complet et propre devient une trace de référence possible :

- **meilleur** tour de la session (repart de zéro quand la session, la piste ou la voiture change) ;
- **dernier** tour valide ;
- **record** personnel pour la piste et la voiture, gardé dans `data/records.json` d'une session à l'autre
  (seulement avec la source `lmu` : les données simulées ou rejouées ne touchent pas aux records).

Delta = temps écoulé dans le tour en cours − temps de la référence au même avancement (interpolé).
Négatif = plus rapide que la référence.

Le temps d'un tour terminé est celui retenu par F04 (`snap.laps`, calculé juste avant) : le jeu peut le publier
un peu après le passage de la ligne, et lire `last_lap_s` à l'instant du passage donnait parfois le temps du tour
précédent.

Un tour ne sert pas de référence s'il n'a pas été suivi depuis la ligne, s'il est passé par les stands,
s'il a été invalidé par le jeu (limites de piste) ou si l'avancement n'a pas été relevé sur presque tout le tour.
"""

from __future__ import annotations

import bisect
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .model import DeltaInfo, Snapshot
from .paths import data_dir

log = logging.getLogger(__name__)

DEFAULT_RECORDS_PATH = data_dir() / "records.json"
# Version 2 : avant, un tour invalidé (limites de piste) ou un temps du tour précédent pouvait devenir un record,
# plus court que les vrais tours. Les records de la version 1 sont ignorés (et remplacés au premier bon tour).
RECORDS_VERSION = 2
START_MAX_FRACTION = 0.05  # 1er relevé d'un tour : il faut être tout près de la ligne
END_MIN_FRACTION = 0.95  # dernier relevé avant la ligne : le tour doit être couvert presque en entier
LATE_START_S = 5.0  # sans relevé près de la ligne après 5 s de tour, le tour n'est pas suivi depuis la ligne
MAX_GAP_FRACTION = 0.1  # trou maximal entre deux relevés (pause, perte de données)
MAX_DELTA_RATIO = 0.25  # au-delà de 25 % du temps de référence, le delta n'a pas de sens (stands, sortie)
PENDING_S = 12.0  # tour terminé abandonné si F04 n'a toujours pas son temps après 12 s du tour suivant


@dataclass
class Trace:
    """Temps écoulé (s) en fonction de l'avancement dans le tour (0..1), croissant."""

    lap_s: float
    fractions: list[float]
    times: list[float]

    def time_at(self, fraction: float) -> float:
        f, t = self.fractions, self.times
        i = bisect.bisect_left(f, fraction)
        if i <= 0:
            return t[0] * fraction / f[0] if f[0] > 0 else t[0]
        if i >= len(f):
            return t[-1]
        f0, f1, t0, t1 = f[i - 1], f[i], t[i - 1], t[i]
        return t0 + (t1 - t0) * (fraction - f0) / (f1 - f0)

    def to_json(self) -> dict:
        return {"lap_s": self.lap_s, "trace": [[round(f, 5), round(t, 3)] for f, t in zip(self.fractions, self.times)]}

    @classmethod
    def from_json(cls, data: dict) -> Trace:
        points = [(float(f), float(t)) for f, t in data["trace"]]
        if len(points) < 2 or any(b[0] <= a[0] for a, b in zip(points, points[1:])):
            raise ValueError("trace vide ou non croissante")
        return cls(float(data["lap_s"]), [p[0] for p in points], [p[1] for p in points])


class RecordStore:
    """Records personnels par piste et voiture, dans un fichier JSON."""

    def __init__(self, path: str | os.PathLike | None) -> None:
        self.path = Path(path) if path else None
        self.records: dict[str, dict] = {}
        self._traces: dict[str, Trace | None] = {}  # traces déjà lues
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("version", 1) >= RECORDS_VERSION:
                    self.records = data.get("records", {})
                else:
                    log.info("Records %s d'une version précédente ignorés (tours invalidés possibles)", self.path)
            except (OSError, ValueError, AttributeError) as exc:
                log.warning("Records %s illisibles, ignorés : %s", self.path, exc)

    @staticmethod
    def key(track: str, car: str) -> str:
        return f"{track} | {car}"

    def get(self, track: str, car: str) -> Trace | None:
        key = self.key(track, car)
        if key not in self._traces:
            try:
                self._traces[key] = Trace.from_json(self.records[key]) if key in self.records else None
            except (KeyError, TypeError, ValueError):
                self._traces[key] = None
        return self._traces[key]

    def put(self, track: str, car: str, trace: Trace) -> None:
        key = self.key(track, car)
        self.records[key] = {**trace.to_json(), "date": datetime.now().isoformat(timespec="seconds")}
        self._traces[key] = trace
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".records-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"version": RECORDS_VERSION, "records": self.records}, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("Record non enregistré dans %s : %s", self.path, exc)


class DeltaCalculator:
    def __init__(self, records_path: str | os.PathLike | None = DEFAULT_RECORDS_PATH) -> None:
        self.records = RecordStore(records_path)
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._lap: int | None = None
        self._fractions: list[float] = []
        self._times: list[float] = []
        self._clean = False  # tour en cours suivi depuis la ligne, sans stand ni trou
        self._pending: tuple[int, list[float], list[float]] | None = None  # tour terminé dont on attend le temps
        self._pending_started = False
        self.best: Trace | None = None
        self.last: Trace | None = None

    def update(self, snap: Snapshot) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track, snap.car)
        if key != self._key or (self._lap is not None and snap.lap < self._lap):
            self.reset()  # nouvelle session, piste, voiture ou retour en arrière
            self._key = key

        if snap.lap != self._lap:
            self._pending = None
            if self._lap is not None and snap.lap == self._lap + 1 and self._clean and self._fractions \
                    and self._fractions[-1] >= END_MIN_FRACTION:
                self._pending = (self._lap, self._fractions, self._times)
                self._pending_started = False  # chrono du tour suivant parti (la télémétrie peut être en retard)
            self._lap = snap.lap
            self._fractions, self._times = [], []
            self._clean = not snap.in_pits
        if snap.in_pits:
            self._clean = False
        if self._pending is not None:
            self._finish_lap(snap)
        self._record_point(snap)

        record = self.records.get(snap.track, snap.car)
        snap.delta = DeltaInfo(
            best_s=self.best.lap_s if self.best else None,
            last_s=self.last.lap_s if self.last else None,
            record_s=record.lap_s if record else None,
            vs_best=self._delta(snap, self.best),
            vs_last=self._delta(snap, self.last),
            vs_record=self._delta(snap, record),
        )
        return snap

    def _record_point(self, snap: Snapshot) -> None:
        f = snap.lap_fraction
        if f is None:
            self._clean = False
            return
        if not self._fractions:
            if f > START_MAX_FRACTION:
                if snap.current_lap_s > LATE_START_S:
                    self._clean = False  # appli lancée en cours de tour
                return  # sinon : avancement du tour précédent pas encore remis à zéro
        elif f <= self._fractions[-1] or snap.current_lap_s < self._times[-1]:
            return  # pas d'avancement (arrêt) ou relevé en retard sur le précédent
        elif f - self._fractions[-1] > MAX_GAP_FRACTION:
            self._clean = False
        self._fractions.append(f)
        self._times.append(snap.current_lap_s)

    def _finish_lap(self, snap: Snapshot) -> None:
        lap, fractions, times = self._pending
        entry = next((e for e in snap.laps.recent if e.lap == lap), None)
        if entry is None:
            self._pending_started |= snap.current_lap_s < PENDING_S
            if self._pending_started and snap.current_lap_s > PENDING_S:
                self._pending = None
            return
        self._pending = None
        lap_s = entry.time_s
        if not (entry.valid and lap_s) or lap_s < times[-1]:
            return  # tour invalidé, passé aux stands, ou temps incohérent avec les relevés
        trace = Trace(lap_s, [*fractions, 1.0], [*times, lap_s])
        self.last = trace
        if self.best is None or lap_s < self.best.lap_s:
            self.best = trace
        if snap.source == "lmu":
            record = self.records.get(snap.track, snap.car)
            if record is None or lap_s < record.lap_s:
                self.records.put(snap.track, snap.car, trace)

    @staticmethod
    def _delta(snap: Snapshot, ref: Trace | None) -> float | None:
        if ref is None or snap.lap_fraction is None:
            return None
        delta = snap.current_lap_s - ref.time_at(snap.lap_fraction)
        if abs(delta) > MAX_DELTA_RATIO * ref.lap_s:
            return None  # passage de ligne pas encore vu, stands, voiture arrêtée…
        return round(delta, 3)
