"""Lecture des données de Le Mans Ultimate via la mémoire partagée (Windows).

À implémenter (étape 1 du PLAN, T05) :
- ouvrir les zones de mémoire partagée exposées par le jeu (mmap, tagname Windows) ;
- décrire les structures avec ctypes (télémétrie véhicule + scoring) ;
- gérer la cohérence de lecture (compteurs de version avant/après) ;
- convertir vers Snapshot (unités : km/h, °C, kPa, litres).
Le détail des champs sera documenté dans docs/donnees-lmu.md.
"""

from ..model import Snapshot
from .base import DataSource


class LmuSharedMemorySource(DataSource):
    name = "lmu"

    def read(self) -> Snapshot:
        # Pas encore implémenté : on signale simplement « jeu non connecté ».
        return Snapshot(connected=False, source=self.name)
