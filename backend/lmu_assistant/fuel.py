"""Calculs carburant (F01) : conso par tour, moyenne, tours restants, carburant à ajouter pour finir.

Indépendant de la source : le serveur passe chaque Snapshot à `FuelCalculator.update`, qui
mesure le carburant au passage de la ligne et remplit `snapshot.fuel`.

Un tour ne compte pas dans la moyenne s'il n'a pas été suivi depuis la ligne (appli lancée en
cours de tour), si la voiture est passée par les stands ou si du carburant a été ajouté pendant le tour.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .model import FuelInfo, Snapshot

AVG_LAPS = 5  # tours valides pris pour la moyenne
REFUEL_L = 0.2  # hausse au-delà de laquelle on considère un ravitaillement
MIN_LAP_L = 0.05  # en dessous, le tour n'a pas consommé (tour neutralisé, relecture figée…)
LAP_START_S = 2.0  # appli lancée dans les 2 premières secondes d'un tour : il est suivi depuis la ligne


@dataclass
class _Lap:
    used_l: float
    time_s: float | None


class FuelCalculator:
    def __init__(self, avg_laps: int = AVG_LAPS) -> None:
        self.avg_laps = avg_laps
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._lap: int | None = None
        self._lap_start_fuel: float | None = None
        self._lap_valid = False
        self._prev_fuel: float | None = None
        self._history: deque[_Lap] = deque(maxlen=self.avg_laps)

    def update(self, snap: Snapshot) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track, snap.car)
        if key != self._key or (self._lap is not None and snap.lap < self._lap):
            self.reset()  # nouvelle session, piste, voiture ou retour en arrière
            self._key = key

        if self._prev_fuel is not None and snap.fuel_l > self._prev_fuel + REFUEL_L:
            self._lap_valid = False
        if snap.in_pits:
            self._lap_valid = False

        if snap.lap != self._lap:
            if self._lap is None:
                at_start = snap.current_lap_s < LAP_START_S
                self._lap_start_fuel = snap.fuel_l if at_start else None
            else:
                if snap.lap == self._lap + 1 and self._lap_valid and self._lap_start_fuel is not None:
                    used = self._lap_start_fuel - snap.fuel_l
                    if used > MIN_LAP_L:
                        self._history.append(_Lap(used, snap.last_lap_s))
                self._lap_start_fuel = snap.fuel_l
            self._lap_valid = not snap.in_pits
            self._lap = snap.lap
        self._prev_fuel = snap.fuel_l

        snap.fuel = self._compute(snap)
        return snap

    def _lap_time(self, snap: Snapshot) -> float | None:
        times = [lap.time_s for lap in self._history if lap.time_s]
        if times:
            return sum(times) / len(times)
        return snap.last_lap_s or snap.best_lap_s

    def _compute(self, snap: Snapshot) -> FuelInfo:
        info = FuelInfo(valid_laps=len(self._history))
        if not self._history:
            return info
        avg = sum(lap.used_l for lap in self._history) / len(self._history)
        info.last_lap_l = round(self._history[-1].used_l, 2)
        info.avg_lap_l = round(avg, 3)
        info.laps_left = round(snap.fuel_l / avg, 2)

        lap_time = self._lap_time(snap)
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
        if remaining:
            info.laps_to_finish = round(min(remaining), 2)
            info.to_add_l = round(max(0.0, info.laps_to_finish * avg - snap.fuel_l), 1)
        return info
