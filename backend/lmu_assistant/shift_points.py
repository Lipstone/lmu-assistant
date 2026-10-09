"""Régimes de passage des GT3 (F14), tirés du tableau « LMU GT3 optimal shift point » (Google Sheets).

Le tableau mesure, pour chaque GT3 et chaque feu du shift light du jeu (jaune, 1er, 2e, 3e feu, bleu…), les
temps d'accélération 100-250 km/h au Mans (rapports « Le Mans ») et à Monza (rapports standard), deux essais
chacun. `best` est le feu au total le plus court (Le Mans + Monza) : c'est là qu'il faut passer le rapport.
`lights` donne le régime de chaque feu indiqué dans l'onglet de la voiture.

La voiture est reconnue par son modèle (télémétrie `mVehicleModel`) ou son nom dans le jeu, en GT3 seulement :
une même marque a aussi une Hypercar (Ferrari 499P, Porsche 963…).
"""

from __future__ import annotations

from dataclasses import dataclass

LEDS_BELOW_FIRST_LIGHT = 400  # tr/min : la première LED du widget s'allume un peu avant le premier feu du jeu


@dataclass(frozen=True)
class ShiftPoint:
    car: str  # nom affiché
    match: tuple[str, ...]  # mots cherchés (minuscules) dans le modèle ou le nom de la voiture, un seul suffit
    lights: tuple[tuple[str, int], ...]  # (feu du jeu, tr/min), du premier au dernier
    best: tuple[str, ...]  # feu(x) marqué(s) « OPTIMAL » dans le tableau ; deux feux : passer entre les deux
    note: str = ""

    @property
    def shift_rpm(self) -> int:
        rpms = [dict(self.lights)[b] for b in self.best]
        return round(sum(rpms) / len(rpms))

    @property
    def start_rpm(self) -> int:
        return min(rpm for _, rpm in self.lights) - LEDS_BELOW_FIRST_LIGHT


GT3_SHIFT_POINTS: tuple[ShiftPoint, ...] = (
    ShiftPoint('Aston Martin Vantage', ('aston', 'vantage'),
               (('Yellow', 6550), ('First light', 6650), ('Second light', 6750), ('Third light', 6850), ('Blue light', 6950)),
               ('Blue light',), 'feu bleu ; le tableau indique ~8 200 tr/min, sûrement une faute de frappe (feux tous les 100 tr/min)'),
    ShiftPoint('Lamborghini Huracán', ('lamborghini', 'huracan', 'huracán'),
               (('Yellow', 7750), ('First light', 7850), ('Second light', 8000), ('Third light', 8100), ('Blue light', 8200)),
               ('Third light', 'Blue light'), 'entre le 3e feu et le bleu'),
    ShiftPoint('Mercedes-AMG', ('mercedes', 'amg'),
               (('Yellow low', 7000), ('Yellow', 7100), ('First light', 7200), ('Second light', 7300), ('Third light', 7400), ('Blue light', 7500)),
               ('Yellow low', 'Yellow'), 'entre le jaune bas et le jaune'),
    ShiftPoint('Porsche 911', ('porsche', '911'),
               (('Yellow', 8500), ('First light', 8700), ('Second light', 8800), ('Third light', 8900), ('Blue light', 9000)),
               ('Second light', 'Third light'), 'entre le 2e et le 3e feu'),
    ShiftPoint('McLaren 720S', ('mclaren', '720s'),
               (('Yellow', 7300), ('First light', 7400), ('Second light', 7500), ('Third light', 7600), ('Blue light', 7700)),
               ('Second light', 'Third light'), 'entre le 2e et le 3e feu'),
    ShiftPoint('Lexus RC F', ('lexus', 'rc f'),
               (('Yellow', 6600), ('First light', 6700), ('Second light', 6750), ('Third light', 6850), ('Blue light', 6950), ('Over REV', 7150)),
               ('Blue light',), 'feu bleu'),
    ShiftPoint('Ford Mustang', ('mustang', 'ford'),
               (('Yellow', 7550), ('First light', 7650), ('Second light', 7750), ('Third light', 7850), ('Blue light', 7950), ('Over REV', 8000)),
               ('Blue light',), 'feu bleu'),
    ShiftPoint('Ferrari 296', ('ferrari', '296'),
               (('Yellow', 7300), ('First light', 7400), ('Second light', 7500), ('Third light', 7600), ('Blue light', 7700)),
               ('Yellow',), 'premier feu (jaune)'),
    ShiftPoint('BMW M4', ('bmw', 'm4'),
               (('Yellow', 6850), ('First light', 6950), ('Second light', 7050), ('Third light', 7600), ('Blue light', 7700)),
               ('First light', 'Second light'), 'entre le 1er et le 2e feu'),
    ShiftPoint('Corvette Z06', ('corvette', 'z06'),
               (('Yellow', 7350), ('First light', 7450), ('Second light', 7500), ('Third light', 7600), ('Blue light', 7700)),
               ('Third light', 'Blue light'), 'entre le 3e feu et le bleu'),
)


def is_gt3(*texts: str) -> bool:
    return any("gt3" in (t or "").lower() for t in texts)


def find_car(model: str, name: str = "", car_class: str = "", table: tuple[ShiftPoint, ...] = GT3_SHIFT_POINTS) -> ShiftPoint | None:
    """Voiture du tableau correspondant au modèle ou au nom donné par le jeu, GT3 seulement."""
    if not is_gt3(model, name, car_class):
        return None
    for text in (model, name):
        low = (text or "").lower()
        if not low:
            continue
        for point in table:
            if any(word in low for word in point.match):
                return point
    return None
