"""Dégâts et consommation de toutes les voitures, pour les colonnes optionnelles des classements (relative F07,
classement par classe F08).

Le serveur passe chaque Snapshot à `OpponentsCalculator.update`, avant le relative et le classement, qui remplit
pour chaque voiture de `snapshot.vehicles` :

- **dégâts globaux** (`damage_pct`) : état de la carrosserie d'après les 8 zones de déformation, même calcul que
  le widget Dégâts du joueur (100 % − somme des gravités / 16) ; `None` si le jeu ne donne pas la télémétrie de
  la voiture ;
- **consommation par tour** (`fuel_per_lap` en litres, `energy_per_lap` en % d'énergie virtuelle) : le jeu ne
  la donne pas directement, elle est **estimée** à partir du carburant / de l'énergie restants relevés à chaque
  passage de ligne : moyenne des `AVG_LAPS` derniers tours sans passage au stand (un tour avec arrêt, un plein ou
  une valeur qui ne baisse pas est ignoré). `None` tant qu'aucun tour complet n'a été mesuré.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import OpponentFields, Snapshot, Vehicle

AVG_LAPS = 3  # tours utilisés pour la moyenne de consommation


def damage_pct(dents: list[int] | None) -> float | None:
    if dents is None:
        return None
    body = [min(max(int(d), 0), 2) for d in (list(dents) + [0] * 8)[:8]]
    return round(100 * (1 - sum(body) / 16), 1)


@dataclass
class _Tracker:
    """Suivi d'une voiture : niveau au dernier passage de ligne et consommations des derniers tours."""

    laps: int = -1
    pitstops: int = 0
    fuel: float | None = None
    energy: float | None = None
    pitted: bool = False  # passage au stand pendant le tour en cours
    fuel_laps: list[float] = field(default_factory=list)
    energy_laps: list[float] = field(default_factory=list)


def _used(before: float | None, after: float | None, history: list[float]) -> None:
    if before is None or after is None:
        return
    used = before - after
    if used > 0:
        history.append(used)
        del history[:-AVG_LAPS]


def _avg(history: list[float], digits: int) -> float | None:
    return round(sum(history) / len(history), digits) if history else None


class OpponentsCalculator:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._cars: dict[int, _Tracker] = {}

    def update(self, snap: Snapshot) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track)
        if key != self._key:
            self.reset()
            self._key = key
        for v in snap.vehicles:
            v.damage_pct = damage_pct(v.dents)
            self._consumption(v)
        return snap

    def _consumption(self, v: Vehicle) -> None:
        t = self._cars.setdefault(v.id, _Tracker())
        first = t.laps < 0
        t.pitted = t.pitted or v.in_pits or v.pitstops != t.pitstops
        if v.laps != t.laps:
            # Tour complet (un seul tour de plus) sans arrêt : consommation = niveau d'avant − niveau d'après
            if v.laps == t.laps + 1 and not t.pitted:
                _used(t.fuel, v.fuel_l, t.fuel_laps)
                _used(t.energy, v.energy_pct, t.energy_laps)
            # Première voiture vue en cours de tour : le tour suivant n'est pas complet, il est ignoré
            t.laps, t.fuel, t.energy, t.pitted = v.laps, v.fuel_l, v.energy_pct, v.in_pits or first
        t.pitstops = v.pitstops
        v.fuel_per_lap = _avg(t.fuel_laps, 2)
        v.energy_per_lap = _avg(t.energy_laps, 2)


def opponent_fields(v: Vehicle) -> dict:
    """Valeurs des colonnes optionnelles pour une ligne de classement."""
    return {k: getattr(v, k) for k in OpponentFields.__dataclass_fields__}
