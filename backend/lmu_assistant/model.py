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
class BrakeInfo:
    """Freins (F06), rempli par `brakes.BrakesCalculator` ; listes dans l'ordre des roues (AVG, AVD, ARG, ARD)."""

    peak_lap_c: list[float] = field(default_factory=lambda: [0.0] * 4)  # pic pendant le tour en cours
    peak_last_lap_c: list[float] | None = None  # pic pendant le tour précédent
    overheat: list[bool] = field(default_factory=lambda: [False] * 4)  # alerte surchauffe en cours
    threshold_c: float = 800.0  # seuil de surchauffe utilisé


@dataclass
class Vehicle:
    """Une voiture de la session (classement du jeu), fournie par la source."""

    id: int = 0
    driver: str = ""
    car: str = ""
    number: str = ""  # numéro de course (« 7 »), vide si inconnu
    car_class: str = ""  # Hypercar, LMP2, LMGT3…
    position: int = 0  # position au général, à partir de 1
    laps: int = 0  # tours terminés
    lap_fraction: float | None = None  # avancement dans le tour en cours, 0..1
    last_lap_s: float | None = None
    best_lap_s: float | None = None
    estimated_lap_s: float | None = None  # temps au tour estimé par le jeu
    time_behind_leader_s: float | None = None
    laps_behind_leader: int = 0
    in_pits: bool = False
    pitstops: int = 0
    is_player: bool = False


@dataclass
class RelativeEntry:
    """Une voiture proche sur la piste (F07)."""

    id: int = 0
    driver: str = ""
    number: str = ""
    car_class: str = ""
    position: int = 0  # au général
    class_position: int = 0  # dans sa classe
    gap_s: float | None = None  # écart sur la piste, positif = devant, négatif = derrière
    laps_diff: int = 0  # tours d'avance (+) ou de retard (−) sur le joueur au classement
    same_class: bool = True
    in_pits: bool = False
    last_lap_s: float | None = None
    is_player: bool = False


@dataclass
class StandingEntry:
    """Une ligne du classement par classe (F08)."""

    id: int = 0
    driver: str = ""
    number: str = ""
    class_position: int = 0
    position: int = 0  # au général
    gap_leader_s: float | None = None  # écart au leader de la classe (s), si moins d'un tour
    laps_leader: int = 0  # tours de retard sur le leader de la classe
    interval_s: float | None = None  # écart à la voiture juste devant dans la classe (s)
    laps_interval: int = 0
    last_lap_s: float | None = None
    best_lap_s: float | None = None
    in_pits: bool = False
    pitstops: int = 0
    is_player: bool = False
    skipped_before: bool = False  # des voitures de la classe sont omises juste avant cette ligne


@dataclass
class ClassStandings:
    """Classement d'une classe (F08), classe du joueur en premier."""

    car_class: str = ""
    cars: int = 0  # nombre de voitures dans la classe
    entries: list[StandingEntry] = field(default_factory=list)


@dataclass
class PitInfo:
    """Fenêtre de stand (F09), remplie par `pitstop.PitCalculator`."""

    laps_left: float | None = None  # tours possibles avant de devoir rentrer
    limited_by: str = ""  # « carburant » ou « énergie » : ce qui impose l'arrêt
    last_lap: int | None = None  # dernier tour à la fin duquel rentrer au stand
    window_open_lap: int | None = None  # premier tour où s'arrêter garde le nombre d'arrêts minimum
    stops_left: int | None = None  # arrêts restants jusqu'à l'arrivée (pleins complets)
    laps_per_stint: float | None = None  # tours possibles avec un plein complet
    loss_s: float | None = None  # temps perdu au stand (mesuré, sinon valeur par défaut)
    loss_measured: bool = False
    loss_samples: int = 0  # arrêts mesurés dans la session
    rejoin_class_position: int | None = None  # position estimée dans la classe en sortant si l'on s'arrêtait maintenant


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
    brakes: BrakeInfo = field(default_factory=BrakeInfo)
    vehicles: list[Vehicle] = field(default_factory=list)  # toutes les voitures de la session
    relative: list[RelativeEntry] = field(default_factory=list)  # F07 : voitures proches, la plus en avant d'abord
    standings: list[ClassStandings] = field(default_factory=list)  # F08 : classement simplifié par classe
    pit: PitInfo = field(default_factory=PitInfo)  # F09 : fenêtre de stand

    def to_dict(self) -> dict:
        return asdict(self)
