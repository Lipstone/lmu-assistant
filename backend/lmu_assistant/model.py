"""Modèle commun produit par toutes les sources de données."""

from dataclasses import asdict, dataclass, field


@dataclass
class Wheel:
    temp_c: tuple[float, float, float] = (0.0, 0.0, 0.0)  # intérieur, milieu, extérieur
    pressure_kpa: float = 0.0
    wear: float = 1.0  # 1.0 = neuf
    brake_temp_c: float = 0.0
    flat: bool = False  # crevaison (F11)
    detached: bool = False  # roue arrachée (F11)


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
    # Télémétrie de la voiture (dégâts et consommation des autres voitures), None si le jeu ne la donne pas
    dents: list[int] | None = None  # même ordre que DamageInfo.body
    parts_detached: bool = False
    wheels_off: int = 0  # roues crevées ou arrachées
    fuel_l: float | None = None
    energy_pct: float | None = None  # énergie virtuelle restante, None si la voiture n'en a pas
    # Calculés par `opponents.OpponentsCalculator`
    damage_pct: float | None = None  # état global de la carrosserie, 100 = intacte
    fuel_per_lap: float | None = None  # litres par tour (moyenne des derniers tours sans arrêt)
    energy_per_lap: float | None = None  # % d'énergie virtuelle par tour


@dataclass
class OpponentFields:
    """Colonnes optionnelles des classements (relative, classement par classe) : dégâts et consommation."""

    damage_pct: float | None = None  # état global de la carrosserie, 100 = intacte
    wheels_off: int = 0
    parts_detached: bool = False
    fuel_per_lap: float | None = None
    energy_per_lap: float | None = None
    fuel_l: float | None = None
    energy_pct: float | None = None


@dataclass
class RelativeEntry(OpponentFields):
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
    best_lap_s: float | None = None
    is_player: bool = False


@dataclass
class StandingEntry(OpponentFields):
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
class SessionInfo:
    """Session et piste (F10), remplie par `session.SessionCalculator`."""

    time_left_s: float | None = None  # temps restant (course chronométrée ou essais)
    progress: float | None = None  # avancement de la session, 0..1
    laps_left: int | None = None  # course au nombre de tours : tours restants, tour en cours compris
    phase: str = ""  # avant, formation, départ, course, fcy, arrêtée, terminée
    flag: str = ""  # green, yellow, fcy, blue, red, checkered ou vide (inconnu, avant le départ)
    flag_label: str = ""  # texte prêt à afficher (« Jaune S2 », « FCY · stands fermés »…)
    yellow_sectors: list[int] = field(default_factory=list)  # secteurs sous drapeau jaune local (1 à 3)
    air_temp_c: float | None = None
    track_temp_c: float | None = None
    track_temp_trend_c: float | None = None  # évolution de la température piste sur 10 min
    rain_pct: float | None = None  # intensité de la pluie, 0..100
    wetness_pct: float | None = None  # piste mouillée (trajectoire), 0..100
    grip: str = ""  # niveau de gomme sur la piste : vert, faible, moyen, élevé, saturé
    sky: str = ""  # ciel : dégagé, nuageux, couvert, bruine, pluie…
    time_of_day_s: float | None = None  # heure dans le jeu, secondes depuis minuit


@dataclass
class DamageInfo:
    """Dégâts (F11), remplis par `damage.DamageCalculator`."""

    body: list[int] = field(default_factory=lambda: [0] * 8)  # AVG, AV, AVD, G, D, ARG, AR, ARD : 0 rien, 1 léger, 2 lourd
    body_pct: float = 100.0  # état de la carrosserie, 100 = intacte
    aero_pct: float | None = None  # état de l'aéro (API du jeu), 100 = intacte
    suspension_pct: list[float] | None = None  # état de chaque suspension (AVG, AVD, ARG, ARD), 100 = intacte
    wheels: list[str] = field(default_factory=lambda: [""] * 4)  # « crevé », « arrachée » ou vide
    parts_detached: bool = False  # éléments de carrosserie arrachés
    impacts: int = 0  # chocs depuis le début de la session
    last_impact_ago_s: float | None = None
    last_impact_magnitude: float | None = None
    repair_s: float | None = None  # temps de réparation estimé au stand (API du jeu)
    engine_overheating: bool = False
    water_temp_c: float | None = None
    oil_temp_c: float | None = None
    damaged: bool = False  # au moins un dégât


@dataclass
class StintInfo:
    """Relais en cours (F21, F22), rempli par `history.HistoryRecorder` à partir des tours de la session."""

    number: int = 0  # 0 = aucun tour terminé
    start_lap: int | None = None
    laps: int = 0  # tours terminés dans le relais
    time_s: float | None = None  # durée du relais, tour en cours compris
    avg_s: float | None = None
    best_s: float | None = None
    stdev_s: float | None = None
    deg_s_per_lap: float | None = None  # temps perdu par tour (pente des tours propres)
    fuel_per_lap: float | None = None
    energy_per_lap: float | None = None
    tyre_age_laps: int | None = None  # tours faits par les pneus montés (None si inconnu)
    wear_per_lap_pct: float | None = None  # usure par tour du pneu qui s'use le plus vite (%)
    worst_wheel: str = ""  # pneu le plus usé
    wear_left_pct: float | None = None  # gomme restante de ce pneu (%)
    laps_to_wear_limit: float | None = None  # tours avant qu'un pneu ne descende sous 30 %


@dataclass
class ForecastNode:
    """Un point de la prévision météo du jeu (API REST, /rest/sessions/weather), valeurs brutes."""

    at: float = 0.0  # moment de la session, en fraction de sa durée (0 départ, 0,25, 0,5, 0,75, 1 fin)
    sky: int = 0  # 0 dégagé … 4 couvert, 5 à 9 de la bruine à la forte pluie, 10 orage
    air_temp_c: float | None = None
    rain_chance_pct: float = 0.0  # 0..100


@dataclass
class WeatherSlot:
    """Un point de la prévision, prêt à afficher (widget Météo)."""

    label: str = ""  # « dans 12 min », « fin », « à 50 % »…
    in_s: float | None = None  # temps avant ce point (None si la session n'a pas de durée)
    past: bool = False  # point déjà dépassé
    sky: int = 0
    sky_label: str = ""
    air_temp_c: float | None = None
    rain_chance_pct: float = 0.0


@dataclass
class WeatherInfo:
    """Météo et prévision (widget Météo), remplie par `weather.WeatherCalculator`.

    La prévision (`slots`) vient du jeu ; les tendances et `eta_label` sont estimées par l'appli
    à partir des relevés des dernières minutes."""

    from_game: bool = False  # prévision du jeu disponible
    headline: str = ""  # résumé : « Pluie probable dans 14 min », « Pluie en cours »…
    level: str = ""  # "" calme, "warn" pluie possible, "rain" pluie en cours ou probable
    slots: list[WeatherSlot] = field(default_factory=list)
    rain_pct: float | None = None  # pluie maintenant, 0..100
    rain_trend_pct: float | None = None  # estimé : évolution de la pluie sur 10 min (points de %)
    wetness_pct: float | None = None  # piste mouillée maintenant, 0..100
    wetness_trend_pct: float | None = None  # estimé : évolution de la piste mouillée sur 10 min (points de %)
    air_temp_c: float | None = None
    track_temp_c: float | None = None
    track_temp_trend_c: float | None = None  # estimé : évolution de la température piste sur 10 min
    track_temp_in_30min_c: float | None = None  # estimé : température piste dans 30 min si la tendance continue
    eta_label: str = ""  # estimé : « piste sèche dans ≈ 12 min », « piste mouillée à 30 % dans ≈ 5 min »


@dataclass
class ShiftInfo:
    """Shift light (F14), rempli par `shift.ShiftCalculator` : régime de passage du rapport et allumage des
    LED. Régime du tableau des GT3 quand la voiture y est, sinon un % du régime max donné par le jeu."""

    rpm: float = 0.0
    gear: int = 0
    predicted_rpm: float = 0.0  # régime prévu après l'anticipation (latence + réaction), sert aux LED
    max_rpm: float | None = None  # régime max (limiteur) donné par le jeu, sinon le plus haut vu
    shift_rpm: float | None = None  # régime où passer le rapport supérieur
    start_rpm: float | None = None  # première LED
    level: float = 0.0  # 0 aucune LED … 1 toutes allumées (régime de passage atteint)
    shift_now: bool = False  # passer maintenant (LED bleues)
    over_rev: bool = False  # au-delà du régime max (rupteur)
    top_gear: bool = False  # dernier rapport : rien à passer
    source: str = ""  # "table" : tableau des GT3 ; "max" : % du régime max ; "" : pas de régime connu
    car_label: str = ""  # voiture reconnue dans le tableau
    note: str = ""  # explication courte du régime choisi


@dataclass
class Snapshot:
    connected: bool = False
    source: str = ""
    session: str = ""
    track: str = ""
    car: str = ""
    car_model: str = ""  # modèle de la voiture (« Corvette Z06 GT3.R »…), vide si inconnu
    car_class: str = ""  # classe de la voiture du joueur (Hypercar, LMP2, LMGT3…)
    lap: int = 0
    position: int = 0
    speed_kmh: float = 0.0
    rpm: float = 0.0
    gear: int = 0
    max_rpm: float = 0.0  # régime max (limiteur) donné par le jeu, 0 inconnu
    max_gears: int = 0  # nombre de rapports avant, 0 inconnu
    fuel_l: float = 0.0
    fuel_capacity_l: float = 0.0
    virtual_energy_pct: float | None = None  # énergie virtuelle restante (F02), None si la voiture n'en a pas
    last_lap_s: float | None = None
    best_lap_s: float | None = None
    current_lap_s: float = 0.0
    last_sector1_s: float | None = None  # dernier tour : fin du secteur 1 (s depuis la ligne)
    last_sector2_s: float | None = None  # dernier tour : fin du secteur 2 (s depuis la ligne, S1 + S2)
    session_time_left_s: float | None = None
    max_laps: int | None = None  # course au nombre de tours (sinon None)
    lap_fraction: float | None = None  # avancement dans le tour en cours, 0..1
    in_pits: bool = False
    lap_invalid: bool = False  # tour en cours invalidé par le jeu (limites de piste)
    wheels: list[Wheel] = field(default_factory=lambda: [Wheel() for _ in range(4)])  # AVG, AVD, ARG, ARD
    # Session et piste (F10), valeurs brutes de la source
    session_elapsed_s: float | None = None
    session_length_s: float | None = None
    game_phase: int | None = None  # 0 avant, 1-4 procédure de départ, 5 vert, 6 FCY, 7 arrêtée, 8 terminée, 9 pause
    yellow_flag_state: int | None = None  # FCY : 1 en attente, 2 stands fermés, 3 leaders, 4 stands ouverts, 5 dernier tour, 6 reprise
    sector_flags: list[int] = field(default_factory=lambda: [0, 0, 0])  # jaune local par secteur (S1, S2, S3), 1 = jaune
    player_flag: int = 0  # drapeau montré au joueur : 0 vert, 6 bleu
    sector: int = 0  # secteur en cours (1 à 3), 0 inconnu
    air_temp_c: float | None = None
    track_temp_c: float | None = None
    raining: float | None = None  # 0..1
    wetness: float | None = None  # 0..1, moyenne sur la trajectoire
    cloud_coverage: int | None = None  # 0 dégagé … 7 couvert et pluie fine
    track_grip: int | None = None  # 0 vert, 1 faible, 2 moyen, 3 élevé, 4 saturé
    time_of_day_s: float | None = None
    weather_forecast: list[ForecastNode] = field(default_factory=list)  # prévision du jeu pour cette session (API REST)
    # Dégâts (F11), valeurs brutes de la source
    dents: list[int] = field(default_factory=lambda: [0] * 8)  # même ordre que DamageInfo.body
    parts_detached: bool = False
    last_impact_et: float | None = None  # instant du dernier choc (temps de session)
    last_impact_magnitude: float | None = None
    engine_overheating: bool = False
    water_temp_c: float | None = None
    oil_temp_c: float | None = None
    aero_damage: float | None = None  # 0 intacte … 1 détruite (API REST du jeu)
    suspension_damage: list[float] | None = None  # 0..1 par roue (API REST du jeu)
    repair_time_s: float | None = None  # API REST du jeu
    # Inputs (F12) : commandes du pilote
    throttle: float = 0.0  # 0..1
    brake: float = 0.0  # 0..1
    clutch: float = 0.0  # 0..1
    steering: float = 0.0  # -1 (gauche) .. 1 (droite)
    steering_range_deg: float | None = None  # rotation totale du volant (butée à butée)
    abs_active: bool = False
    tc_active: bool = False
    fuel: FuelInfo = field(default_factory=FuelInfo)
    energy: FuelInfo = field(default_factory=lambda: FuelInfo(unit="%"))
    delta: DeltaInfo = field(default_factory=DeltaInfo)
    laps: LapTimesInfo = field(default_factory=LapTimesInfo)
    brakes: BrakeInfo = field(default_factory=BrakeInfo)
    vehicles: list[Vehicle] = field(default_factory=list)  # toutes les voitures de la session
    relative: list[RelativeEntry] = field(default_factory=list)  # F07 : voitures proches, la plus en avant d'abord
    standings: list[ClassStandings] = field(default_factory=list)  # F08 : classement simplifié par classe
    pit: PitInfo = field(default_factory=PitInfo)  # F09 : fenêtre de stand
    session_info: SessionInfo = field(default_factory=SessionInfo)  # F10 : session et piste
    damage: DamageInfo = field(default_factory=DamageInfo)  # F11 : dégâts
    stint: StintInfo = field(default_factory=StintInfo)  # F21, F22 : relais en cours
    weather: WeatherInfo = field(default_factory=WeatherInfo)  # F13 : météo et prévision
    shift: ShiftInfo = field(default_factory=ShiftInfo)  # F14 : shift light

    def to_dict(self) -> dict:
        return asdict(self)
