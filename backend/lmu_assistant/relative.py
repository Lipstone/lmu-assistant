"""Relative (F07) : les voitures juste devant et juste derrière le joueur **sur la piste**.

Le serveur passe chaque Snapshot à `compute_relative`, qui remplit `snapshot.relative` à partir de
`snapshot.vehicles` (classement de toutes les voitures fourni par la source) :

- position sur la piste = avancement dans le tour ; l'écart avec le joueur est ramené dans ]−½, ½] tour,
  donc une voiture à 0,9 tour devant est en fait 0,1 tour derrière ;
- écart en secondes = écart sur la piste × temps au tour de référence du joueur (meilleur tour, sinon
  dernier, sinon estimation du jeu) ;
- tours d'avance ou de retard = différence de distance totale parcourue, une fois l'écart sur la piste
  retiré : +1 = la voiture a un tour d'avance sur le joueur au classement (elle va le doubler), −1 = un tour
  de retard (le joueur va la doubler) ;
- position dans la classe d'après la position au général.
"""

from __future__ import annotations

from .model import RelativeEntry, Snapshot, Vehicle
from .opponents import opponent_fields

CARS_EACH_SIDE = 3  # voitures affichées devant et derrière


def class_positions(vehicles: list[Vehicle]) -> dict[int, int]:
    """Position de chaque voiture (par id) dans sa classe, d'après la position au général."""
    counts: dict[str, int] = {}
    result: dict[int, int] = {}
    for v in sorted(vehicles, key=lambda v: v.position or 10_000):
        counts[v.car_class] = counts.get(v.car_class, 0) + 1
        result[v.id] = counts[v.car_class]
    return result


def reference_lap(player: Vehicle, vehicles: list[Vehicle]) -> float | None:
    for t in (player.best_lap_s, player.last_lap_s, player.estimated_lap_s):
        if t and t > 0:
            return t
    times = [v.best_lap_s for v in vehicles if v.best_lap_s and v.best_lap_s > 0]
    return min(times) if times else None


def _track_gap(frac: float, player_frac: float) -> float:
    d = frac - player_frac
    if d > 0.5:
        d -= 1.0
    elif d <= -0.5:
        d += 1.0
    return d


def compute_relative(snap: Snapshot, each_side: int = CARS_EACH_SIDE) -> Snapshot:
    snap.relative = []
    player = next((v for v in snap.vehicles if v.is_player), None)
    if player is None or player.lap_fraction is None:
        return snap
    lap_s = reference_lap(player, snap.vehicles)
    class_pos = class_positions(snap.vehicles)
    player_total = player.laps + player.lap_fraction

    def entry(v: Vehicle, d: float) -> RelativeEntry:
        laps_diff = round(v.laps + v.lap_fraction - player_total - d) if v is not player else 0
        return RelativeEntry(
            id=v.id, driver=v.driver, number=v.number, car_class=v.car_class, position=v.position,
            class_position=class_pos.get(v.id, 0),
            gap_s=round(d * lap_s, 1) if lap_s else None,
            laps_diff=laps_diff, same_class=v.car_class == player.car_class, in_pits=v.in_pits,
            last_lap_s=v.last_lap_s, best_lap_s=v.best_lap_s, is_player=v is player, **opponent_fields(v),
        )

    others = [(v, _track_gap(v.lap_fraction, player.lap_fraction))
              for v in snap.vehicles if v is not player and v.lap_fraction is not None]
    ahead = sorted((o for o in others if o[1] > 0), key=lambda o: o[1])[:each_side]
    behind = sorted((o for o in others if o[1] <= 0), key=lambda o: -o[1])[:each_side]
    rows = list(reversed(ahead)) + [(player, 0.0)] + behind
    snap.relative = [entry(v, d) for v, d in rows]
    return snap
