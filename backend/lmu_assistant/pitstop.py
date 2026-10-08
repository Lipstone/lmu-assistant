"""Fenêtre de stand (F09) : quand s'arrêter et combien de temps ça coûte.

Le serveur passe chaque Snapshot à `PitCalculator.update` après les calculs carburant (F01, F02), temps au
tour (F04) et classement (F07), qui remplit `snapshot.pit` :

- **tours avant l'arrêt obligatoire** : le plus petit des tours restants en carburant et en énergie virtuelle
  (on dit lequel limite) ; **dernier tour pour rentrer** = dernier passage de ligne possible avec ce qu'il reste ;
- **arrêts restants** jusqu'à l'arrivée et **ouverture de la fenêtre** : premier tour où l'on peut s'arrêter en
  gardant ce nombre d'arrêts minimum, avec un plein complet (réservoir, ou 100 % d'énergie) à chaque arrêt ;
- **temps perdu au stand** : mesuré sur nos arrêts de la session (temps des tours de rentrée et de sortie moins
  autant de tours de la moyenne F04), sinon la valeur par défaut des réglages ;
- **position estimée à la sortie** dans la classe : les voitures de la classe derrière nous à moins de ce temps
  nous repasseraient.
"""

from __future__ import annotations

import math

from .model import PitInfo, Snapshot

PIT_LOSS_S = 60.0  # valeur par défaut tant qu'aucun arrêt n'a été mesuré (réglable)
WARN_LAPS = 2  # le widget alerte quand il reste moins de 2 tours avant de devoir rentrer


class PitCalculator:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._seen: set[int] = set()  # tours terminés déjà pris en compte
        self._group: list[float] = []  # temps des tours « stand » consécutifs en cours
        self._losses: list[float] = []

    def _record_laps(self, snap: Snapshot) -> None:
        avg = snap.laps.avg_s
        for lap in sorted(snap.laps.recent, key=lambda e: e.lap):
            if lap.lap in self._seen or lap.time_s is None:
                continue
            self._seen.add(lap.lap)
            if lap.pit:
                self._group.append(lap.time_s)
            elif self._group:
                if avg:
                    loss = sum(self._group) - len(self._group) * avg
                    if 0 < loss < 600:
                        self._losses.append(loss)
                self._group = []

    def update(self, snap: Snapshot, default_loss_s: float = PIT_LOSS_S) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track, snap.car)
        if key != self._key:
            self.reset()
            self._key = key
        self._record_laps(snap)

        info = PitInfo(loss_s=default_loss_s)
        if self._losses:
            recent = self._losses[-3:]
            info.loss_s = round(sum(recent) / len(recent), 1)
            info.loss_measured = True
            info.loss_samples = len(self._losses)

        # (tours restants, tours par plein) pour chaque ressource mesurée
        resources = {}
        if snap.fuel.laps_left is not None and snap.fuel.avg_lap:
            per_tank = snap.fuel_capacity_l / snap.fuel.avg_lap if snap.fuel_capacity_l > 0 else None
            resources["carburant"] = (snap.fuel.laps_left, per_tank)
        if snap.virtual_energy_pct is not None and snap.energy.laps_left is not None and snap.energy.avg_lap:
            resources["énergie"] = (snap.energy.laps_left, 100.0 / snap.energy.avg_lap)
        if resources:
            limit = min(resources, key=lambda r: resources[r][0])
            info.laps_left = round(resources[limit][0], 1)
            info.limited_by = limit
            frac = min(max(snap.lap_fraction or 0.0, 0.0), 0.999)
            # Passages de ligne encore possibles ; on rentre au plus tard à la fin du tour qui précède la panne.
            crossings = math.floor(frac + resources[limit][0] + 1e-9)
            info.last_lap = snap.lap + crossings - 1 if crossings >= 1 else snap.lap

            per_stint = [p for _, p in resources.values() if p]
            to_finish = snap.fuel.laps_to_finish or snap.energy.laps_to_finish
            if per_stint and to_finish is not None:
                stint = min(per_stint)
                info.laps_per_stint = round(stint, 1)
                missing = to_finish - resources[limit][0]
                info.stops_left = 0 if missing <= 0 else math.ceil(missing / stint)
                if info.stops_left:
                    # S'arrêter à la fin du tour L laisse to_finish − x tours à couvrir avec stops_left pleins,
                    # x = tours jusqu'à la fin du tour L.
                    x_min = to_finish - info.stops_left * stint
                    info.window_open_lap = min(info.last_lap, snap.lap + max(0, math.ceil(x_min - (1 - frac))))

        info.rejoin_class_position = self._rejoin(snap, info.loss_s)
        snap.pit = info
        return snap

    @staticmethod
    def _rejoin(snap: Snapshot, loss_s: float | None) -> int | None:
        """Position dans la classe à la sortie des stands si l'on s'arrêtait maintenant."""
        me = next((v for v in snap.vehicles if v.is_player), None)
        if me is None or loss_s is None or me.lap_fraction is None:
            return None
        lap_s = me.best_lap_s or me.last_lap_s or me.estimated_lap_s
        me_total = me.laps + me.lap_fraction
        position = 1
        for v in snap.vehicles:
            if v is me or v.car_class != me.car_class:
                continue
            if v.position and v.position < me.position:
                position += 1
                continue
            if v.lap_fraction is None:
                continue
            dist = me_total - (v.laps + v.lap_fraction)  # tours d'avance sur cette voiture
            if not 0 <= dist < 1:
                continue  # elle a un tour de retard ou plus : elle ne nous repasse pas au classement
            if v.time_behind_leader_s is not None and me.time_behind_leader_s is not None:
                gap = v.time_behind_leader_s - me.time_behind_leader_s
            elif lap_s:
                gap = dist * lap_s
            else:
                continue
            if gap < loss_s:
                position += 1
        return position
