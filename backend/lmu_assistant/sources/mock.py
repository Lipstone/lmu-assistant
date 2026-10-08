"""Source simulée : une voiture qui tourne en boucle, pour développer sans le jeu."""

import math
import random
import time

from ..model import Snapshot, Vehicle, Wheel
from .base import DataSource

LAP_S = 225.0  # ~3 min 45 s
FUEL_PER_LAP_L = 3.4
ENERGY_PER_LAP_PCT = 4.1  # énergie virtuelle (Hypercar)
PIT_BELOW_L = 8.0  # passage au stand (plein) quand il reste moins que ça au passage de ligne
PIT_S = 25.0  # durée passée « dans les stands » au début du tour suivant
PIT_LOSS_S = 35.0  # temps perdu par l'arrêt (tour de sortie plus long, F09)

# Plateau simulé (F07, F08) : numéro, pilote, classe, temps au tour moyen (s), avance au départ (tour).
PLAYER = ("00", "Vous", "Hypercar")
FIELD = [
    ("7", "K. Kobayashi", "Hypercar", 223.4, 0.012),
    ("50", "A. Fuoco", "Hypercar", 224.1, 0.008),
    ("6", "K. Estre", "Hypercar", 225.6, 0.004),
    ("8", "S. Buemi", "Hypercar", 226.3, -0.004),
    ("38", "J. Button", "Hypercar", 228.0, -0.008),
    ("22", "F. Albuquerque", "LMP2", 236.2, 0.016),
    ("28", "R. Kubica", "LMP2", 237.0, 0.010),
    ("37", "M. Jakobsen", "LMP2", 238.4, -0.012),
    ("92", "M. Bortolotti", "LMGT3", 249.5, 0.020),
    ("31", "A. Farfus", "LMGT3", 250.3, 0.006),
    ("91", "R. Lietz", "LMGT3", 251.2, -0.016),
    ("54", "D. Rigon", "LMGT3", 252.6, -0.020),
]
FIELD_PIT_EVERY = 12  # tours entre deux arrêts des autres voitures

RACE_S = 6 * 3600.0  # course de 6 h
RAIN_START_S = 900.0  # météo (F10) : averses périodiques
RAIN_PERIOD_S = 5400.0
YELLOW_EVERY_S = 900.0  # un jaune local d'une minute toutes les 15 min
YELLOW_S = 60.0
FIRST_HIT_S = 1200.0  # dégâts simulés (F11)
SECOND_HIT_S = 3000.0


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
        self._stops = 0
        self._wetness = 0.0
        self._s1: float | None = None
        self._s2: float | None = None

    def _fraction(self, current: float) -> float:
        x = current / self._lap_target
        return x + self._wobble * math.sin(2 * math.pi * x) / (2 * math.pi) * 6

    def read(self) -> Snapshot:
        now = time.monotonic()
        current = now - self._lap_start
        if current >= self._lap_target:
            self._last = self._lap_target
            # secteurs (F20) : 31 %, 38 %, 31 % du tour, à quelques dixièmes près
            self._s1 = round(self._last * 0.31 + random.uniform(-0.4, 0.4), 3)
            self._s2 = round(self._s1 + self._last * 0.38 + random.uniform(-0.4, 0.4), 3)
            self._best = min(self._best or self._last, self._last)
            self._lap += 1
            self._lap_start = now
            self._fuel = max(0.0, self._fuel - FUEL_PER_LAP_L * current / LAP_S * random.uniform(0.95, 1.05))
            self._energy = max(0.0, self._energy - ENERGY_PER_LAP_PCT * current / LAP_S * random.uniform(0.97, 1.03))
            self._lap_target = LAP_S + random.uniform(-1.5, 1.5)
            self._wobble = random.uniform(-0.01, 0.01)  # temps gagné ou perdu en cours de tour (delta F03)
            current = 0.0
            self._invalid_at = random.uniform(30, 200) if random.random() < 0.15 else None
            self._pit = self._fuel < PIT_BELOW_L or self._energy < 2 * ENERGY_PER_LAP_PCT
            if self._pit:
                self._stops += 1
                self._lap_target += PIT_LOSS_S
                if self._lap - self._stint_start >= 20:  # pneus changés un arrêt sur deux environ
                    self._stint_start = self._lap
                self._fuel = 90.0
                self._energy = 100.0

        phase = current / LAP_S * 2 * math.pi
        speed = 200 + 110 * math.sin(phase * 28)
        if self._pit and current < PIT_S:
            speed = 0.0 if 6 <= current < 18 else 60.0  # limiteur dans la voie des stands, arrêt au stand
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
        # Inputs (F12) : accélère quand la vitesse monte, freine fort avant les points lents
        accel = math.cos(phase * 28)
        throttle = min(max(accel * 1.6 + 0.35, 0.0), 1.0)
        brake = min(max(-accel * 1.8 - 0.75, 0.0), 1.0)
        inputs = dict(
            throttle=round(throttle, 3), brake=round(brake, 3), clutch=0.0,
            steering=round(0.45 * math.sin(phase * 28 + 1.3) + 0.08 * math.sin(phase * 97), 3),
            steering_range_deg=400.0, abs_active=brake > 0.85, tc_active=throttle > 0.9 and speed < 160,
        )
        fraction = round(min(self._fraction(current), 1.0), 4)
        in_pits = self._pit and current < PIT_S
        vehicles = self._field(now - self._start)
        vehicles.append(Vehicle(
            id=0, driver=PLAYER[1], car="Hypercar #00", number=PLAYER[0], car_class=PLAYER[2],
            laps=self._lap - 1, lap_fraction=fraction, last_lap_s=self._last, best_lap_s=self._best,
            estimated_lap_s=LAP_S, in_pits=in_pits, pitstops=self._stops, is_player=True,
        ))
        _classify(vehicles)
        player = vehicles[-1]
        return Snapshot(
            connected=True,
            source=self.name,
            session="Course (simulée)",
            track="Circuit de la Sarthe",
            car="Hypercar #00",
            lap=self._lap,
            position=player.position,
            speed_kmh=round(speed, 1),
            rpm=round(4000 + speed * 25),
            gear=max(1, min(7, int(speed / 45))),
            fuel_l=round(self._fuel - FUEL_PER_LAP_L * current / LAP_S, 2),
            fuel_capacity_l=100.0,
            virtual_energy_pct=round(self._energy - ENERGY_PER_LAP_PCT * current / LAP_S, 2),
            last_lap_s=self._last,
            last_sector1_s=self._s1,
            last_sector2_s=self._s2,
            best_lap_s=self._best,
            current_lap_s=round(current, 3),
            lap_fraction=fraction,
            in_pits=in_pits,
            lap_invalid=self._invalid_at is not None and current >= self._invalid_at,
            session_time_left_s=max(0.0, RACE_S - (now - self._start)),
            wheels=wheels,
            vehicles=sorted(vehicles, key=lambda v: v.position),
            **self._session(now - self._start, fraction),
            **self._damage(now - self._start),
            **inputs,
        )

    @staticmethod
    def _damage(t: float) -> dict:
        """Dégâts (F11) : un léger contact à l'avant gauche à 20 min, un choc plus fort à l'arrière à 50 min."""
        dents = [0] * 8  # AVG, AV, AVD, G, D, ARG, AR, ARD
        d = dict(dents=dents, water_temp_c=round(88 + 4 * math.sin(t / 300), 1),
                 oil_temp_c=round(104 + 5 * math.sin(t / 420), 1), aero_damage=0.0, suspension_damage=[0.0] * 4,
                 repair_time_s=0.0)
        if t >= FIRST_HIT_S:
            dents[0] = dents[1] = 1
            d.update(last_impact_et=FIRST_HIT_S, last_impact_magnitude=1850.0, aero_damage=0.06,
                     suspension_damage=[0.04, 0.0, 0.0, 0.0], repair_time_s=8.0)
        if t >= SECOND_HIT_S:
            dents[6], dents[5], dents[7] = 2, 1, 1
            d.update(last_impact_et=SECOND_HIT_S, last_impact_magnitude=5400.0, aero_damage=0.19,
                     suspension_damage=[0.04, 0.0, 0.0, 0.22], repair_time_s=31.0)
        return d

    def _session(self, t: float, fraction: float) -> dict:
        """Session et piste (F10) : une averse de temps en temps, piste qui chauffe l'après-midi,
        un jaune local d'une minute toutes les 15 min dans un secteur différent."""
        rain = min(max((math.sin(2 * math.pi * (t - RAIN_START_S) / RAIN_PERIOD_S) - 0.7) / 0.3, 0.0), 1.0) * 0.6
        # la piste sèche moins vite qu'elle ne se mouille
        self._wetness += (rain - self._wetness) * (0.004 if rain > self._wetness else 0.001)
        self._wetness = max(0.0, self._wetness)
        cycle = t % YELLOW_EVERY_S
        flags = [0, 0, 0]
        if YELLOW_EVERY_S - YELLOW_S <= cycle:
            flags[int(t // YELLOW_EVERY_S) % 3] = 1
        return dict(
            session_elapsed_s=round(t, 3),
            session_length_s=RACE_S,
            game_phase=5,
            yellow_flag_state=0,
            sector_flags=flags,
            sector=min(3, int(fraction * 3) + 1),
            air_temp_c=round(22 + 3 * math.sin(2 * math.pi * t / 21600) - 2 * rain, 1),
            track_temp_c=round(31 + 7 * math.sin(2 * math.pi * t / 21600) - 9 * self._wetness, 1),
            raining=round(rain, 3),
            wetness=round(self._wetness, 3),
            cloud_coverage=7 if rain > 0.3 else 6 if rain > 0 else 3 if self._wetness > 0.05 else 1,
            track_grip=2 if self._wetness > 0.2 else 3,
            time_of_day_s=(15 * 3600 + t) % 86400,
        )

    @staticmethod
    def _field(t: float) -> list[Vehicle]:
        """Autres voitures : chacune tourne à son rythme, avec un arrêt tous les FIELD_PIT_EVERY tours."""
        cars = []
        for i, (number, driver, car_class, lap_s, start) in enumerate(FIELD, start=1):
            progress = start + t / lap_s + 0.002 * math.sin(t / 40 + i)
            laps = math.floor(progress)
            first_pit = i % FIELD_PIT_EVERY + 1
            stops = 0 if laps < first_pit else (laps - first_pit) // FIELD_PIT_EVERY + 1
            cars.append(Vehicle(
                id=i, driver=driver, car=f"{car_class} #{number}", number=number, car_class=car_class,
                laps=laps, lap_fraction=round(progress - laps, 4),
                last_lap_s=round(lap_s + 0.8 * math.sin(laps * 1.7 + i), 3) if laps >= 1 else None,
                best_lap_s=round(lap_s - 0.6, 3) if laps >= 2 else None,
                estimated_lap_s=lap_s,
                in_pits=laps >= first_pit and (laps - first_pit) % FIELD_PIT_EVERY == 0 and progress - laps < 0.02,
                pitstops=stops,
            ))
        return cars


def _classify(vehicles: list[Vehicle]) -> None:
    """Positions au général et écarts au leader, d'après la distance parcourue."""
    total = {v.id: v.laps + (v.lap_fraction or 0.0) for v in vehicles}
    ranked = sorted(vehicles, key=lambda v: -total[v.id])
    leader = total[ranked[0].id]
    for pos, v in enumerate(ranked, start=1):
        v.position = pos
        behind = leader - total[v.id]
        v.laps_behind_leader = int(behind)
        v.time_behind_leader_s = round(behind * (v.estimated_lap_s or LAP_S), 3)
