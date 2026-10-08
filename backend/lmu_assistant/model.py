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
    """Calculs de consommation, remplis par `fuel.FuelCalculator` à partir des Snapshot successifs :
    carburant (F01, en litres) et énergie virtuelle (F02, en %)."""

    unit: str = "L"  # "L" (carburant) ou "%" (énergie virtuelle)
    last_lap: float | None = None  # conso du dernier tour valide
    avg_lap: float | None = None  # moyenne des derniers tours valides
    laps_left: float | None = None  # tours possibles avec ce qu'il reste
    laps_to_finish: float | None = None  # tours restant à parcourir jusqu'au drapeau à damier (estimation)
    to_add: float | None = None  # à ajouter pour finir (0 si assez)
    valid_laps: int = 0  # nombre de tours servant à la moyenne


@dataclass
class DeltaInfo:
    """Delta en direct (F03), rempli par `delta.DeltaCalculator` : écart du tour en cours avec chaque
    référence au même endroit de la piste (s, négatif = plus rapide), et temps au tour de chaque référence."""

    best_s: float | None = None  # meilleur tour de la session
    last_s: float | None = None  # dernier tour valide
    record_s: float | None = None  # record personnel piste + voiture
    vs_best: float | None = None
    vs_last: float | None = None
    vs_record: float | None = None


@dataclass
class LapEntry:
    """Un tour terminé (F04)."""

    lap: int = 0
    time_s: float | None = None
    valid: bool = True  # compte dans la moyenne et la régularité
    pit: bool = False  # passage aux stands pendant le tour (sortie ou rentrée)
    invalid: bool = False  # invalidé par le jeu (limites de piste)
    vs_best: float | None = None  # écart avec le meilleur tour valide de la session (s)


@dataclass
class LapTimesInfo:
    """Temps au tour (F04), rempli par `laptimes.LapTimesCalculator`."""

    recent: list[LapEntry] = field(default_factory=list)  # derniers tours, le plus récent d'abord
    best_valid_s: float | None = None  # meilleur tour valide de la session
    avg_s: float | None = None  # moyenne des N derniers tours valides
    avg_count: int = 0  # nombre de tours dans la moyenne (au plus N)
    stdev_s: float | None = None  # régularité : écart-type de ces tours (au moins 2)
    valid_laps: int = 0  # tours valides depuis le début de la session


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
    virtual_energy_pct: float | None = None  # énergie virtuelle restante (F02), None si la voiture n'en a pas
    last_lap_s: float | None = None
    best_lap_s: float | None = None
    current_lap_s: float = 0.0
    session_time_left_s: float | None = None
    max_laps: int | None = None  # course au nombre de tours (sinon None)
    lap_fraction: float | None = None  # avancement dans le tour en cours, 0..1
    in_pits: bool = False
    lap_invalid: bool = False  # tour en cours invalidé par le jeu (limites de piste)
    wheels: list[Wheel] = field(default_factory=lambda: [Wheel() for _ in range(4)])  # AVG, AVD, ARG, ARD
    fuel: FuelInfo = field(default_factory=FuelInfo)
    energy: FuelInfo = field(default_factory=lambda: FuelInfo(unit="%"))
    delta: DeltaInfo = field(default_factory=DeltaInfo)
    laps: LapTimesInfo = field(default_factory=LapTimesInfo)

    def to_dict(self) -> dict:
        return asdict(self)
