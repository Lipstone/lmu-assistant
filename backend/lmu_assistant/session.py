"""Session et piste (F10) : temps restant, drapeaux, météo, températures et grip.

Le serveur passe chaque Snapshot à `SessionCalculator.update`, qui remplit `snapshot.session_info` à partir des
valeurs brutes de la source (phase de jeu, drapeaux, météo) :

- **temps restant** et avancement de la session ; en course au nombre de tours, tours restants ;
- **drapeau** à afficher, du plus important au moins important : rouge (session arrêtée), damier (terminée),
  FCY / voiture de sécurité (avec l'état des stands), jaune local dans notre secteur ou le suivant, bleu, vert ;
- **météo** : températures air et piste, **évolution de la piste sur 10 min**, pluie, piste mouillée, ciel,
  niveau de gomme (grip) et heure dans le jeu.
"""

from __future__ import annotations

from collections import deque

from .model import SessionInfo, Snapshot

TREND_WINDOW_S = 600.0  # évolution de la température piste sur 10 min
TREND_MIN_S = 120.0  # pas d'évolution affichée avec moins de 2 min de relevés
SAMPLE_EVERY_S = 15.0

PHASES = {0: "avant", 1: "formation", 2: "formation", 3: "formation", 4: "départ", 5: "course", 6: "fcy",
          7: "arrêtée", 8: "terminée", 9: "pause"}
FCY_STATES = {1: "en attente", 2: "stands fermés", 3: "leaders aux stands", 4: "stands ouverts", 5: "dernier tour",
              6: "reprise"}
GRIP = {0: "vert", 1: "faible", 2: "moyen", 3: "élevé", 4: "saturé"}
SKY = {0: "dégagé", 1: "quelques nuages", 2: "nuageux", 3: "très nuageux", 4: "couvert", 5: "bruine",
       6: "pluie fine", 7: "couvert, pluie fine"}
BLUE = 6  # VehicleScoringInfoV01.mFlag


def flag_of(snap: Snapshot) -> tuple[str, str, list[int]]:
    """(drapeau, texte, secteurs sous jaune local)."""
    yellow = [i + 1 for i, f in enumerate(snap.sector_flags[:3]) if f == 1]
    phase = snap.game_phase
    if phase == 7:
        return "red", "Drapeau rouge", yellow
    if phase == 8:
        return "checkered", "Arrivée", yellow
    if phase == 6:
        state = FCY_STATES.get(snap.yellow_flag_state or 0)
        return "fcy", "FCY / voiture de sécurité" + (f" · {state}" if state else ""), yellow
    if yellow:
        # Jaune qui nous concerne : notre secteur ou le suivant ; sinon on le signale sans alerte.
        mine = {snap.sector, snap.sector % 3 + 1} if snap.sector else set(yellow)
        if mine & set(yellow):
            return "yellow", "Jaune " + " ".join(f"S{s}" for s in yellow), yellow
    if snap.player_flag == BLUE:
        return "blue", "Drapeau bleu", yellow
    if phase == 5:
        label = "Vert" + (" · jaune " + " ".join(f"S{s}" for s in yellow) if yellow else "")
        return "green", label, yellow
    if phase in (1, 2, 3, 4):
        return "", "Tour de formation" if phase in (1, 2, 3) else "Départ imminent", yellow
    return "", "", yellow


class SessionCalculator:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._temps: deque[tuple[float, float]] = deque()  # (temps de session, température piste)

    def _trend(self, snap: Snapshot) -> float | None:
        t, temp = snap.session_elapsed_s, snap.track_temp_c
        if t is None or temp is None:
            return None
        if self._temps and t < self._temps[-1][0]:
            self._temps.clear()  # horloge de session repartie en arrière (relecture, redémarrage)
        if not self._temps or t - self._temps[-1][0] >= SAMPLE_EVERY_S:
            self._temps.append((t, temp))
        while len(self._temps) > 1 and t - self._temps[1][0] >= TREND_WINDOW_S:
            self._temps.popleft()
        t0, temp0 = self._temps[0]
        span = t - t0
        if span < TREND_MIN_S:
            return None
        return round((temp - temp0) * TREND_WINDOW_S / span, 1)  # ramené à 10 min

    def update(self, snap: Snapshot) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track)
        if key != self._key:
            self.reset()
            self._key = key

        info = SessionInfo(time_left_s=snap.session_time_left_s)
        if snap.session_length_s and snap.session_elapsed_s is not None:
            info.progress = round(min(max(snap.session_elapsed_s / snap.session_length_s, 0.0), 1.0), 4)
        if snap.max_laps:
            info.laps_left = max(0, snap.max_laps - snap.lap + 1)
            info.progress = round(min(max((snap.lap - 1 + (snap.lap_fraction or 0.0)) / snap.max_laps, 0.0), 1.0), 4)
        info.phase = PHASES.get(snap.game_phase, "") if snap.game_phase is not None else ""
        info.flag, info.flag_label, info.yellow_sectors = flag_of(snap)
        info.air_temp_c = None if snap.air_temp_c is None else round(snap.air_temp_c, 1)
        info.track_temp_c = None if snap.track_temp_c is None else round(snap.track_temp_c, 1)
        info.track_temp_trend_c = self._trend(snap)
        info.rain_pct = None if snap.raining is None else round(100 * snap.raining)
        info.wetness_pct = None if snap.wetness is None else round(100 * snap.wetness)
        info.grip = GRIP.get(snap.track_grip, "") if snap.track_grip is not None else ""
        info.sky = SKY.get(snap.cloud_coverage, "") if snap.cloud_coverage is not None else ""
        info.time_of_day_s = snap.time_of_day_s
        snap.session_info = info
        return snap
