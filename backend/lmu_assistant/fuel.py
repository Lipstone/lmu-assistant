"""Calculs de consommation : carburant (F01, litres) et énergie virtuelle (F02, %).

Pour chacun : conso du dernier tour, moyenne, tours restants, quantité à ajouter pour finir.
Indépendant de la source : le serveur passe chaque Snapshot à `FuelCalculator.update`, qui
mesure carburant et énergie au passage de la ligne et remplit `snapshot.fuel` et `snapshot.energy`.

Un tour ne compte pas dans la moyenne s'il n'a pas été suivi depuis la ligne (appli lancée en
cours de tour), si la voiture est passée par les stands ou si du carburant ou de l'énergie a été
ajouté pendant le tour.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .model import FuelInfo, Snapshot

AVG_LAPS = 5  # tours valides pris pour la moyenne
REFILL = {"L": 0.2, "%": 0.2}  # hausse au-delà de laquelle on considère un ravitaillement
MIN_LAP = {"L": 0.05, "%": 0.05}  # en dessous, le tour n'a pas consommé (neutralisé, relecture figée…)
LAP_START_S = 2.0  # appli lancée dans les 2 premières secondes d'un tour : il est suivi depuis la ligne


def _levels(snap: Snapshot) -> dict[str, float | None]:
    return {"L": snap.fuel_l, "%": snap.virtual_energy_pct}


@dataclass
class _Lap:
    used: dict[str, float | None]  # par unité ; None si non mesurable pendant ce tour
    time_s: float | None


class FuelCalculator:
    def __init__(self, avg_laps: int = AVG_LAPS) -> None:
        self.avg_laps = avg_laps
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._lap: int | None = None
        self._lap_start: dict[str, float | None] | None = None
        self._lap_valid = False
        self._prev: dict[str, float | None] = {}
        self._history: deque[_Lap] = deque(maxlen=self.avg_laps)

    def update(self, snap: Snapshot) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track, snap.car)
        if key != self._key or (self._lap is not None and snap.lap < self._lap):
            self.reset()  # nouvelle session, piste, voiture ou retour en arrière
            self._key = key

        levels = _levels(snap)
        for unit, level in levels.items():
            prev = self._prev.get(unit)
            if level is not None and prev is not None and level > prev + REFILL[unit]:
                self._lap_valid = False
        if snap.in_pits:
            self._lap_valid = False

        if snap.lap != self._lap:
            if self._lap is None:
                at_start = snap.current_lap_s < LAP_START_S
                self._lap_start = levels if at_start else None
            else:
                if snap.lap == self._lap + 1 and self._lap_valid and self._lap_start is not None:
                    used = {}
                    for unit, level in levels.items():
                        start = self._lap_start.get(unit)
                        diff = start - level if start is not None and level is not None else None
                        used[unit] = diff if diff is not None and diff > MIN_LAP[unit] else None
                    if any(v is not None for v in used.values()):
                        self._history.append(_Lap(used, snap.last_lap_s))
                self._lap_start = levels
            self._lap_valid = not snap.in_pits
            self._lap = snap.lap
        self._prev = levels

        lap_time = self._lap_time(snap)
        laps_to_finish = self._laps_to_finish(snap, lap_time)
        snap.fuel = self._compute("L", snap.fuel_l, laps_to_finish)
        snap.energy = self._compute("%", snap.virtual_energy_pct, laps_to_finish)
        return snap

    def _lap_time(self, snap: Snapshot) -> float | None:
        times = [lap.time_s for lap in self._history if lap.time_s]
        if times:
            return sum(times) / len(times)
        return snap.last_lap_s or snap.best_lap_s

    def _laps_to_finish(self, snap: Snapshot, lap_time: float | None) -> float | None:
        frac = snap.lap_fraction
        if frac is None:
            frac = snap.current_lap_s / lap_time if lap_time else 0.0
        frac = min(max(frac, 0.0), 0.999)

        remaining: list[float] = []
        if snap.max_laps:
            remaining.append(max(0.0, snap.max_laps - (snap.lap - 1) - frac))
        if snap.session_time_left_s is not None and lap_time:
            # À la fin du temps, on termine le tour en cours : on arrondit au passage de ligne suivant.
            total = frac + snap.session_time_left_s / lap_time
            remaining.append(math.ceil(total - 1e-9) - frac)
        return round(min(remaining), 2) if remaining else None

    def _compute(self, unit: str, level: float | None, laps_to_finish: float | None) -> FuelInfo:
        used = [lap.used[unit] for lap in self._history if lap.used.get(unit) is not None]
        info = FuelInfo(unit=unit, valid_laps=len(used))
        if not used or level is None:
            return info
        avg = sum(used) / len(used)
        info.last_lap = round(used[-1], 2)
        info.avg_lap = round(avg, 3)
        info.laps_left = round(level / avg, 2)
        if laps_to_finish is not None:
            info.laps_to_finish = laps_to_finish
            info.to_add = round(max(0.0, laps_to_finish * avg - level), 1)
        return info
