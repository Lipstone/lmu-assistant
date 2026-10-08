"""Dégâts (F11) : carrosserie, aéro, suspension, roues, chocs et moteur.

Le serveur passe chaque Snapshot à `DamageCalculator.update`, qui remplit `snapshot.damage` :

- **carrosserie** : gravité des déformations en 8 zones autour de la voiture (`mDentSeverity` : 0 rien,
  1 léger, 2 lourd) et état global (100 % − somme / 16, comme TinyPedal) ;
- **aéro** et **suspension** par roue, et **temps de réparation** estimé : donnés par l'API REST locale du jeu
  quand elle répond (sinon non affichés) ;
- **roues** crevées ou arrachées, éléments arrachés ;
- **chocs** : nombre depuis le début de la session, le dernier (il y a combien de temps, force) ;
- **moteur** : alerte surchauffe du jeu, températures eau et huile.
"""

from __future__ import annotations

from .model import DamageInfo, Snapshot


def _pct(fraction: float | None) -> float | None:
    return None if fraction is None else round(100 * (1 - min(max(fraction, 0.0), 1.0)), 1)


class DamageCalculator:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._impact_et: float | None = None
        self._impacts = 0

    def update(self, snap: Snapshot) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track, snap.car)
        if key != self._key:
            self.reset()
            self._key = key
            self._impact_et = snap.last_impact_et  # choc d'avant le lancement de l'appli : pas compté
        elif snap.last_impact_et is not None and snap.last_impact_et != self._impact_et:
            if self._impact_et is None or snap.last_impact_et > self._impact_et:
                self._impacts += 1
            self._impact_et = snap.last_impact_et

        body = [min(max(int(d), 0), 2) for d in (snap.dents + [0] * 8)[:8]]
        info = DamageInfo(
            body=body,
            body_pct=round(100 * (1 - sum(body) / 16), 1),
            aero_pct=_pct(snap.aero_damage),
            suspension_pct=[_pct(x) for x in snap.suspension_damage[:4]] if snap.suspension_damage else None,
            wheels=["arrachée" if w.detached else "crevé" if w.flat else "" for w in snap.wheels[:4]],
            parts_detached=snap.parts_detached,
            impacts=self._impacts,
            repair_s=None if snap.repair_time_s is None else round(snap.repair_time_s, 1),
            engine_overheating=snap.engine_overheating,
            water_temp_c=None if snap.water_temp_c is None else round(snap.water_temp_c, 1),
            oil_temp_c=None if snap.oil_temp_c is None else round(snap.oil_temp_c, 1),
        )
        if snap.last_impact_et is not None and snap.last_impact_et > 0 and snap.session_elapsed_s is not None:
            info.last_impact_ago_s = round(max(0.0, snap.session_elapsed_s - snap.last_impact_et), 1)
            info.last_impact_magnitude = snap.last_impact_magnitude
        info.damaged = bool(
            sum(body) or any(info.wheels) or info.parts_detached
            or (info.aero_pct is not None and info.aero_pct < 100)
            or (info.suspension_pct and any(p is not None and p < 100 for p in info.suspension_pct))
        )
        snap.damage = info
        return snap
