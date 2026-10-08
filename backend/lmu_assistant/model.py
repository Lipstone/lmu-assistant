"""Modèle commun produit par toutes les sources de données."""

from dataclasses import asdict, dataclass, field


@dataclass
class Wheel:
    temp_c: tuple[float, float, float] = (0.0, 0.0, 0.0)  # intérieur, milieu, extérieur
    pressure_kpa: float = 0.0
    wear: float = 1.0  # 1.0 = neuf
    brake_temp_c: float = 0.0


@dataclass
class FuelInfo:
    """Calculs carburant (F01), remplis par `fuel.FuelCalculator` à partir des Snapshot successifs."""

    last_lap_l: float | None = None  # conso du dernier tour valide
    avg_lap_l: float | None = None  # moyenne des derniers tours valides
    laps_left: float | None = None  # tours possibles avec le carburant à bord
    laps_to_finish: float | None = None  # tours restant à parcourir jusqu'au drapeau à damier (estimation)
    to_add_l: float | None = None  # carburant à ajouter pour finir (0 si assez)
    valid_laps: int = 0  # nombre de tours servant à la moyenne


@dataclass
class Snapshot:
    connected: bool = False
    source: str = ""
    session: str = ""
    track: str = ""
    car: str = ""
    lap: int = 0
    position: int = 0
    speed_kmh: float = 0.0
    rpm: float = 0.0
    gear: int = 0
    fuel_l: float = 0.0
    fuel_capacity_l: float = 0.0
    last_lap_s: float | None = None
    best_lap_s: float | None = None
    current_lap_s: float = 0.0
    session_time_left_s: float | None = None
    max_laps: int | None = None  # course au nombre de tours (sinon None)
    lap_fraction: float | None = None  # avancement dans le tour en cours, 0..1
    in_pits: bool = False
    wheels: list[Wheel] = field(default_factory=lambda: [Wheel() for _ in range(4)])  # AVG, AVD, ARG, ARD
    fuel: FuelInfo = field(default_factory=FuelInfo)

    def to_dict(self) -> dict:
        return asdict(self)
