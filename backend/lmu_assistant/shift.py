"""Shift light (F14) : quand passer le rapport supérieur.

Le serveur passe chaque Snapshot à `ShiftCalculator.update`, qui remplit `snapshot.shift` :

- **GT3 du tableau** (`shift_points.GT3_SHIFT_POINTS`) : la voiture est reconnue par son nom dans le jeu et le
  régime de passage est celui qui a donné les meilleures accélérations 100-250 km/h dans le tableau de mesures
  « LMU GT3 optimal shift point » (Le Mans et Monza) ;
- **autres voitures** : un pourcentage du régime max donné par le jeu (réglage `shift_rpm_pct`). Si le jeu ne
  donne pas de régime max, on prend le plus haut régime vu avec cette voiture.

Les LED s'allument de `start_rpm` à `shift_rpm` ; au régime de passage elles passent toutes au bleu.

**Anticipation** (réglage `shift_lead_ms`, 150 ms par défaut) : entre la mesure du jeu et le geste du pilote il y a
la chaîne d'affichage (lecture, envoi, rendu : quelques dizaines de ms) et le temps de réaction. Les LED et le bleu
suivent donc le régime prévu dans `shift_lead_ms` à la vitesse de montée actuelle (moyenne lissée), pas le régime
mesuré : le bleu s'allume avant le régime cible pour que le rapport passe au bon régime.
Sur le dernier rapport il n'y a rien à passer : les LED s'allument quand même mais sans le bleu.
"""

from __future__ import annotations

import time

from .model import ShiftInfo, Snapshot
from .shift_points import GT3_SHIFT_POINTS, ShiftPoint, find_car

SHIFT_RPM_PCT = 98.0  # autres voitures : régime de passage en % du régime max
LEDS_SPAN = 0.07  # autres voitures : la première LED s'allume 7 % sous le régime de passage
MIN_SEEN_RPM = 3000.0  # en dessous, le régime vu ne sert pas de régime max
LEAD_MS = 150.0  # anticipation : latence d'affichage et temps de réaction
RATE_SMOOTHING = 0.3  # poids de la dernière mesure dans la vitesse de montée lissée
MAX_GAP_S = 0.5  # au-delà, deux images ne servent pas à mesurer la vitesse de montée


class ShiftCalculator:
    def __init__(self, table: tuple[ShiftPoint, ...] = GT3_SHIFT_POINTS, clock=time.monotonic) -> None:
        self.table = table
        self.clock = clock
        self._car = ""
        self._seen_max = 0.0
        self._last: tuple[float, float, int] | None = None  # instant, régime, rapport de l'image précédente
        self._rate = 0.0  # tr/min par seconde, lissé

    def _rise_rate(self, rpm: float, gear: int) -> float:
        now = self.clock()
        last, self._last = self._last, (now, rpm, gear)
        if last is None or last[2] != gear or not 0 < now - last[0] <= MAX_GAP_S:
            self._rate = 0.0  # changement de rapport, pause : on repart de zéro
            return 0.0
        rate = (rpm - last[1]) / (now - last[0])
        self._rate += RATE_SMOOTHING * (rate - self._rate)
        return max(self._rate, 0.0)  # en décélération, pas d'anticipation

    def update(self, snap: Snapshot, rpm_pct: float = SHIFT_RPM_PCT, use_table: bool = True,
               lead_ms: float = LEAD_MS) -> Snapshot:
        rising = self._rise_rate(snap.rpm, snap.gear)
        car = snap.car_model or snap.car
        if car != self._car:
            self._car = car
            self._seen_max = 0.0
        if snap.rpm >= MIN_SEEN_RPM:
            self._seen_max = max(self._seen_max, snap.rpm)
        info = ShiftInfo(rpm=snap.rpm, gear=snap.gear)
        info.max_rpm = snap.max_rpm or (self._seen_max or None)
        info.top_gear = snap.max_gears > 0 and snap.gear >= snap.max_gears

        point = find_car(snap.car_model, snap.car, snap.car_class, self.table) if use_table else None
        if point is not None:
            info.source = "table"
            info.car_label = point.car
            info.shift_rpm = float(point.shift_rpm)
            info.start_rpm = float(point.start_rpm)
            info.note = point.note
        elif info.max_rpm:
            info.source = "max"
            info.shift_rpm = round(info.max_rpm * rpm_pct / 100)
            info.start_rpm = round(info.shift_rpm * (1 - LEDS_SPAN))
            info.note = f"{rpm_pct:g} % du régime max" + ("" if snap.max_rpm else " vu")

        info.predicted_rpm = round(snap.rpm + rising * lead_ms / 1000)
        if info.shift_rpm and info.start_rpm is not None and snap.gear > 0:
            span = max(info.shift_rpm - info.start_rpm, 1.0)
            info.level = round(min(max((info.predicted_rpm - info.start_rpm) / span, 0.0), 1.0), 3)
            info.shift_now = info.predicted_rpm >= info.shift_rpm and not info.top_gear
        info.over_rev = bool(snap.max_rpm) and snap.rpm >= snap.max_rpm
        snap.shift = info
        return snap
