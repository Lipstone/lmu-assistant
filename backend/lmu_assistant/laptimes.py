"""Temps au tour (F04) : derniers tours, moyenne des N derniers tours valides et régularité.

Le serveur passe chaque Snapshot à `LapTimesCalculator.update`, qui note chaque tour terminé au passage de
la ligne (temps donné par le jeu, `last_lap_s`) et remplit `snapshot.laps`.

Le jeu peut publier ce temps un peu après le passage de la ligne : on attend qu'il change. LMU ne donne pas de
temps (valeur <= 0) pour un tour invalidé : on prend alors la durée mesurée entre deux départs de tour
(`lap_start_et`, horloge du jeu) et le tour est marqué invalide. Si le temps du jeu et la durée mesurée ne
concordent pas, on garde celui du jeu et on le note dans le journal.

Un tour est **valide** (compte dans la moyenne et la régularité) s'il a été suivi depuis la ligne, sans
passage aux stands (tour de sortie et tour de rentrée exclus) et sans être invalidé par le jeu (limites de
piste). Les autres tours restent dans la liste des derniers tours, marqués. La régularité est l'écart-type
des temps des N derniers tours valides. Tout repart de zéro quand la session, la piste ou la voiture change.
"""

from __future__ import annotations

import logging
import math
from collections import deque

from .model import LapEntry, LapTimesInfo, Snapshot

log = logging.getLogger(__name__)

AVG_LAPS = 5  # tours valides pris pour la moyenne et la régularité (réglable)
RECENT_LAPS = 5  # tours affichés dans la liste
HISTORY = 50  # tours gardés en mémoire
LAP_START_S = 2.0  # appli lancée dans les 2 premières secondes d'un tour : il est suivi depuis la ligne
PENDING_S = 10.0  # temps laissé au jeu pour publier le temps du tour après le passage de la ligne
MISMATCH_S = 0.5  # écart au-delà duquel le temps du jeu et la durée mesurée sont notés dans le journal


class LapTimesCalculator:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._lap: int | None = None
        self._tracked = False  # tour en cours suivi depuis la ligne
        self._pit = False  # passage aux stands pendant le tour en cours
        self._invalid = False  # tour en cours invalidé par le jeu
        self._pending: LapEntry | None = None  # tour terminé dont on attend le temps
        self._pending_prev: float | None = None
        self._prev_last: float | None = None  # `last_lap_s` au moment du passage de la ligne
        self._start_et: float | None = None  # dernier `lap_start_et` vu
        self._measured: tuple[float, float] | None = None  # (départ du tour suivant, durée) du dernier tour mesuré
        self._pending_measured: float | None = None
        self._pending_started = False
        self._history: deque[LapEntry] = deque(maxlen=HISTORY)

    def update(self, snap: Snapshot, avg_laps: int = AVG_LAPS) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track, snap.car)
        if key != self._key or (self._lap is not None and snap.lap < self._lap):
            self.reset()
            self._key = key

        # Durée mesurée : écart entre deux départs de tour, sur l'horloge du jeu (la télémétrie passe la ligne
        # avant que le numéro de tour, mis à jour avec le classement, ne change).
        if snap.lap_start_et is not None:
            if self._start_et is not None and snap.lap_start_et > self._start_et:
                self._measured = (snap.lap_start_et, snap.lap_start_et - self._start_et)
            self._start_et = snap.lap_start_et

        if snap.lap != self._lap:
            if self._lap is not None and snap.lap == self._lap + 1:
                self._pending = LapEntry(lap=self._lap, valid=self._tracked and not (self._pit or self._invalid),
                                         pit=self._pit, invalid=self._invalid)
                self._pending_prev = self._prev_last
                self._pending_measured = None
                self._pending_started = False  # chrono du tour suivant parti (la télémétrie peut être en retard)
            else:
                self._pending = None
            if self._lap is None:
                self._tracked = snap.current_lap_s < LAP_START_S
            else:
                self._tracked = snap.lap == self._lap + 1  # sinon tour sauté (relecture, perte de données)
            self._pit = self._invalid = False
            self._lap = snap.lap
            self._prev_last = snap.last_lap_s
        self._pit |= snap.in_pits
        self._invalid |= snap.lap_invalid

        if self._pending is not None:
            self._pending_started |= snap.current_lap_s < PENDING_S
            m = self._measured
            if self._pending_measured is None and m is not None and m[0] == snap.lap_start_et \
                    and snap.current_lap_s < PENDING_S:
                self._pending_measured = m[1]  # durée du tour qui vient de finir (pas celle du précédent)
            # Le temps du tour est celui que le jeu publie au passage de la ligne : on attend qu'il change.
            if snap.last_lap_s != self._pending_prev:
                if snap.last_lap_s is not None:
                    self._finish(snap.last_lap_s)
                else:
                    self._finish(None, invalid=True)  # LMU : pas de temps pour un tour invalidé
            elif self._pending_started and snap.current_lap_s > PENDING_S:
                self._finish(None, invalid=True)  # le jeu n'a rien publié
            self._prev_last = snap.last_lap_s

        snap.laps = self._compute(avg_laps)
        return snap

    def _finish(self, official: float | None, invalid: bool = False) -> None:
        lap, measured = self._pending, self._pending_measured
        self._pending = None
        if official is not None:
            if measured is not None and abs(official - measured) > MISMATCH_S:
                log.warning("Tour %d : temps du jeu %.3f s, durée mesurée %.3f s", lap.lap, official, measured)
            lap.time_s = official
        elif measured is not None:
            lap.time_s = round(measured, 3)
            lap.invalid |= invalid
            lap.valid = lap.valid and not invalid
        else:
            return  # temps inconnu : tour non noté
        self._history.append(lap)

    def _compute(self, avg_laps: int) -> LapTimesInfo:
        valid = [lap.time_s for lap in self._history if lap.valid]
        info = LapTimesInfo(valid_laps=len(valid))
        if valid:
            info.best_valid_s = min(valid)
        recent = list(self._history)[-RECENT_LAPS:]
        best = info.best_valid_s
        info.recent = [
            LapEntry(lap.lap, lap.time_s, lap.valid, lap.pit, lap.invalid,
                     round(lap.time_s - best, 3) if best is not None else None)
            for lap in reversed(recent)
        ]
        last_n = valid[-avg_laps:]
        info.avg_count = len(last_n)
        if last_n:
            avg = sum(last_n) / len(last_n)
            info.avg_s = round(avg, 3)
        if len(last_n) >= 2:
            info.stdev_s = round(math.sqrt(sum((t - avg) ** 2 for t in last_n) / (len(last_n) - 1)), 3)
        return info
