"""Freins (F06) : pic de température par roue sur le tour et alerte surchauffe.

Le serveur passe chaque Snapshot à `BrakesCalculator.update`, qui remplit `snapshot.brakes` :

- pic de température de chaque frein pendant le tour en cours et pendant le tour précédent ;
- alerte **surchauffe** par roue : active dès que la température dépasse le seuil, et jusqu'à ce qu'elle
  redescende de `HYSTERESIS_C` sous le seuil (évite le clignotement autour du seuil).
"""

from __future__ import annotations

from .model import BrakeInfo, Snapshot

OVERHEAT_C = 800.0  # seuil par défaut (réglable)
HYSTERESIS_C = 30.0


class BrakesCalculator:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._lap: int | None = None
        self._peak = [0.0] * 4
        self._last_peak: list[float] | None = None
        self._overheat = [False] * 4

    def update(self, snap: Snapshot, threshold_c: float = OVERHEAT_C) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track, snap.car)
        if key != self._key:
            self.reset()
            self._key = key
        if snap.lap != self._lap:
            if self._lap is not None and snap.lap == self._lap + 1:
                self._last_peak = self._peak
            else:
                self._last_peak = None
            self._peak = [0.0] * 4
            self._lap = snap.lap

        temps = [w.brake_temp_c for w in snap.wheels[:4]]
        for i, t in enumerate(temps):
            if t is None:
                continue
            self._peak[i] = max(self._peak[i], t)
            if t > threshold_c:
                self._overheat[i] = True
            elif t < threshold_c - HYSTERESIS_C:
                self._overheat[i] = False

        snap.brakes = BrakeInfo(
            peak_lap_c=[round(p, 1) for p in self._peak],
            peak_last_lap_c=[round(p, 1) for p in self._last_peak] if self._last_peak else None,
            overheat=list(self._overheat),
            threshold_c=threshold_c,
        )
        return snap
