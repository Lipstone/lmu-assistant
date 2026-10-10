"""Classement par classe (F08), simplifié pour tenir dans un widget.

Le serveur passe chaque Snapshot à `compute_standings`, qui remplit `snapshot.standings` à partir de
`snapshot.vehicles` : une liste par classe (dans l'ordre de leur meilleure voiture au général, la classe du
joueur en dernier, en bas du widget). Dans chaque classe on garde les `TOP` premiers, plus, dans la classe du joueur, la voiture
juste devant lui, lui-même et celle juste derrière ; `skipped_before` marque un trou dans la liste.

Écarts dans la classe (au leader de la classe, et à la voiture juste devant dans la classe) :
- en tours entiers quand la distance parcourue diffère d'au moins un tour ;
- sinon en secondes, d'après les écarts au leader donnés par le jeu, ou à défaut d'après la distance × le temps
  au tour de la voiture.
"""

from __future__ import annotations

from .model import ClassStandings, StandingEntry, Snapshot, Vehicle
from .opponents import opponent_fields

TOP = 3  # voitures gardées en tête de chaque classe


def _total(v: Vehicle) -> float | None:
    return v.laps + v.lap_fraction if v.lap_fraction is not None else None


def gap(v: Vehicle, ahead: Vehicle) -> tuple[float | None, int]:
    """Écart de `v` avec `ahead` : (secondes, 0) ou (None, tours) quand il y a au moins un tour d'écart."""
    tv, ta = _total(v), _total(ahead)
    dist = ta - tv if tv is not None and ta is not None else float(ahead.laps - v.laps)
    if dist >= 1:
        return None, int(dist)
    if v.time_behind_leader_s is not None and ahead.time_behind_leader_s is not None:
        return round(max(0.0, v.time_behind_leader_s - ahead.time_behind_leader_s), 1), 0
    lap_s = v.best_lap_s or v.estimated_lap_s or v.last_lap_s
    if tv is not None and ta is not None and lap_s:
        return round(max(0.0, dist) * lap_s, 1), 0
    return None, 0


def compute_standings(snap: Snapshot, top: int = TOP) -> Snapshot:
    snap.standings = []
    by_class: dict[str, list[Vehicle]] = {}
    for v in sorted(snap.vehicles, key=lambda v: v.position or 10_000):
        by_class.setdefault(v.car_class, []).append(v)
    player = next((v for v in snap.vehicles if v.is_player), None)
    order = sorted(by_class, key=lambda c: (player is not None and c == player.car_class, by_class[c][0].position))

    for car_class in order:
        cars = by_class[car_class]
        keep = set(range(min(top, len(cars))))
        if player is not None and car_class == player.car_class:
            i = cars.index(player)
            keep |= {j for j in (i - 1, i, i + 1) if 0 <= j < len(cars)}
        entries = []
        prev = -1
        for i in sorted(keep):
            v = cars[i]
            to_leader = gap(v, cars[0]) if i else (None, 0)
            to_ahead = gap(v, cars[i - 1]) if i else (None, 0)
            entries.append(StandingEntry(
                id=v.id, driver=v.driver, number=v.number, class_position=i + 1, position=v.position,
                gap_leader_s=to_leader[0], laps_leader=to_leader[1],
                interval_s=to_ahead[0], laps_interval=to_ahead[1],
                last_lap_s=v.last_lap_s, best_lap_s=v.best_lap_s, in_pits=v.in_pits, pitstops=v.pitstops,
                is_player=v.is_player, skipped_before=i > prev + 1, **opponent_fields(v),
            ))
            prev = i
        snap.standings.append(ClassStandings(car_class=car_class, cars=len(cars), entries=entries))
    return snap
