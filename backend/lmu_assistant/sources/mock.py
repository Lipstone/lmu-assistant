"""Source simulée : une voiture qui tourne en boucle, pour développer sans le jeu."""

import math
import random
import time

from ..model import Snapshot, Wheel
from .base import DataSource

LAP_S = 225.0  # ~3 min 45 s
FUEL_PER_LAP_L = 3.4


class MockSource(DataSource):
    name = "mock"

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._lap = 1
        self._lap_start = self._start
        self._fuel = 90.0
        self._last: float | None = None
        self._best: float | None = None
        self._lap_target = LAP_S

    def read(self) -> Snapshot:
        now = time.monotonic()
        current = now - self._lap_start
        if current >= self._lap_target:
            self._last = self._lap_target
            self._best = min(self._best or self._last, self._last)
            self._lap += 1
            self._lap_start = now
            self._fuel = max(0.0, self._fuel - FUEL_PER_LAP_L * random.uniform(0.95, 1.05))
            self._lap_target = LAP_S + random.uniform(-1.5, 1.5)
            current = 0.0

        phase = current / LAP_S * 2 * math.pi
        speed = 200 + 110 * math.sin(phase * 7)
        wheels = [
            Wheel(
                temp_c=(85 + i + 5 * math.sin(phase), 88 + i, 84 + i),
                pressure_kpa=165 + i,
                wear=max(0.0, 1.0 - 0.012 * self._lap),
                brake_temp_c=350 + 150 * max(0.0, math.sin(phase * 7 + 1)),
            )
            for i in range(4)
        ]
        return Snapshot(
            connected=True,
            source=self.name,
            session="Course (simulée)",
            track="Circuit de la Sarthe",
            car="Hypercar #00",
            lap=self._lap,
            position=3,
            speed_kmh=round(speed, 1),
            rpm=round(4000 + speed * 25),
            gear=max(1, min(7, int(speed / 45))),
            fuel_l=round(self._fuel - FUEL_PER_LAP_L * current / LAP_S, 2),
            fuel_capacity_l=100.0,
            last_lap_s=self._last,
            best_lap_s=self._best,
            current_lap_s=round(current, 3),
            session_time_left_s=max(0.0, 6 * 3600 - (now - self._start)),
            wheels=wheels,
        )
