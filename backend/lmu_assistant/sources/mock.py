"""Source simulée : une voiture qui tourne en boucle, pour développer sans le jeu."""

import math
import random
import time

from ..model import Snapshot, Wheel
from .base import DataSource

LAP_S = 225.0  # ~3 min 45 s
FUEL_PER_LAP_L = 3.4
ENERGY_PER_LAP_PCT = 4.1  # énergie virtuelle (Hypercar)
PIT_BELOW_L = 8.0  # passage au stand (plein) quand il reste moins que ça au passage de ligne
PIT_S = 25.0  # durée passée « dans les stands » au début du tour suivant


class MockSource(DataSource):
    name = "mock"

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._lap = 1
        self._lap_start = self._start
        self._fuel = 90.0
        self._energy = 100.0
        self._last: float | None = None
        self._best: float | None = None
        self._lap_target = LAP_S
        self._pit = False
        self._wobble = 0.0
        self._stint_start = 1  # tour où des pneus neufs ont été montés
        self._invalid_at: float | None = None  # instant du tour où il sera invalidé (limites de piste)

    def _fraction(self, current: float) -> float:
        x = current / self._lap_target
        return x + self._wobble * math.sin(2 * math.pi * x) / (2 * math.pi) * 6

    def read(self) -> Snapshot:
        now = time.monotonic()
        current = now - self._lap_start
        if current >= self._lap_target:
            self._last = self._lap_target
            self._best = min(self._best or self._last, self._last)
            self._lap += 1
            self._lap_start = now
            self._fuel = max(0.0, self._fuel - FUEL_PER_LAP_L * random.uniform(0.95, 1.05))
            self._energy = max(0.0, self._energy - ENERGY_PER_LAP_PCT * random.uniform(0.97, 1.03))
            self._lap_target = LAP_S + random.uniform(-1.5, 1.5)
            self._wobble = random.uniform(-0.01, 0.01)  # temps gagné ou perdu en cours de tour (delta F03)
            current = 0.0
            self._invalid_at = random.uniform(30, 200) if random.random() < 0.15 else None
            self._pit = self._fuel < PIT_BELOW_L or self._energy < 2 * ENERGY_PER_LAP_PCT
            if self._pit:
                if self._lap - self._stint_start >= 20:  # pneus changés un arrêt sur deux environ
                    self._stint_start = self._lap
                self._fuel = 90.0
                self._energy = 100.0

        phase = current / LAP_S * 2 * math.pi
        speed = 200 + 110 * math.sin(phase * 7)
        stint = self._lap - self._stint_start  # tours depuis les derniers pneus neufs
        wheels = [
            Wheel(
                # avant plus chaud que l'arrière, intérieur plus chaud que l'extérieur (carrossage)
                temp_c=(
                    round(96 - 6 * (i // 2) + 4 * math.sin(phase * 7 + i), 1),
                    round(90 - 6 * (i // 2) + 3 * math.sin(phase * 7 + i), 1),
                    round(83 - 6 * (i // 2) + 5 * math.sin(phase * 7 + i), 1),
                ),
                pressure_kpa=round(172 - 3 * (i // 2) + min(stint, 3) + math.sin(phase * 7 + i), 1),
                wear=round(max(0.0, 1.0 - (0.014 if i < 2 else 0.011) * stint - 0.014 * current / LAP_S), 3),
                # avant plus sollicité : l'avant gauche dépasse 800 °C dans les gros freinages
                brake_temp_c=round(
                    (300 if i < 2 else 260) + (560 - 30 * i if i < 2 else 380) * max(0.0, math.sin(phase * 7 + 1)) ** 3, 1
                ),
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
            virtual_energy_pct=round(self._energy - ENERGY_PER_LAP_PCT * current / LAP_S, 2),
            last_lap_s=self._last,
            best_lap_s=self._best,
            current_lap_s=round(current, 3),
            lap_fraction=round(min(self._fraction(current), 1.0), 4),
            in_pits=self._pit and current < PIT_S,
            lap_invalid=self._invalid_at is not None and current >= self._invalid_at,
            session_time_left_s=max(0.0, 6 * 3600 - (now - self._start)),
            wheels=wheels,
        )
