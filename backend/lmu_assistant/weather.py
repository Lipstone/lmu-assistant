"""Météo et prévision (F13) : ce que le jeu prévoit et ce que l'appli estime.

Le serveur passe chaque Snapshot à `WeatherCalculator.update` (après `SessionCalculator`), qui remplit
`snapshot.weather` :

- **prévision du jeu** : LMU donne pour chaque session 5 points (départ, 25 %, 50 %, 75 %, fin) avec le ciel,
  la température de l'air et le risque de pluie (API REST locale, `/rest/sessions/weather`). Chaque point est
  placé dans le temps à partir de la durée de la session (« dans 12 min ») ; course au nombre de tours : en % ;
- **estimations de l'appli** (relevés toutes les 15 s, sur les 10 dernières minutes) : évolution de la pluie, de
  la piste mouillée et de la température piste, température piste dans 30 min si la tendance continue, et temps
  avant que la piste soit sèche (ou mouillée à 30 %) au rythme actuel ;
- **résumé** : pluie en cours, pluie probable au prochain point de la prévision, sinon temps sec.
"""

from __future__ import annotations

from collections import deque

from .model import Snapshot, WeatherInfo, WeatherSlot

WINDOW_S = 600.0  # tendances ramenées à 10 min
MIN_SPAN_S = 120.0  # pas de tendance avec moins de 2 min de relevés
SAMPLE_EVERY_S = 15.0
DRY_PCT = 5.0  # piste considérée sèche sous 5 % mouillée
WET_PCT = 30.0  # seuil « piste mouillée » de l'estimation
RAIN_LIKELY_PCT = 50.0  # risque de pluie à partir duquel la pluie est annoncée « probable »
RAIN_POSSIBLE_PCT = 20.0
MAX_ETA_S = 3600.0  # au-delà d'une heure, l'estimation n'a plus de sens

SKY = {0: "dégagé", 1: "quelques nuages", 2: "partiellement nuageux", 3: "très nuageux", 4: "couvert",
       5: "bruine", 6: "pluie fine", 7: "couvert, pluie fine", 8: "pluie", 9: "forte pluie", 10: "orage"}
RAINY_SKY = 5  # ciel 5 et plus : il pleut


def fmt_minutes(seconds: float) -> str:
    m = max(1, round(seconds / 60))
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


class _Trend:
    """Évolution d'une valeur sur les 10 dernières minutes (temps de session)."""

    def __init__(self) -> None:
        self.points: deque[tuple[float, float]] = deque()

    def update(self, t: float, value: float | None) -> float | None:
        if value is None:
            return None
        if self.points and t < self.points[-1][0]:
            self.points.clear()  # horloge de session repartie en arrière (relecture, redémarrage)
        if not self.points or t - self.points[-1][0] >= SAMPLE_EVERY_S:
            self.points.append((t, value))
        while len(self.points) > 1 and t - self.points[1][0] >= WINDOW_S:
            self.points.popleft()
        t0, v0 = self.points[0]
        span = t - t0
        if span < MIN_SPAN_S:
            return None
        return round((value - v0) * WINDOW_S / span, 1)


def _eta(value: float, trend: float | None, target: float) -> float | None:
    """Temps (s) pour atteindre `target` au rythme `trend` (par 10 min), None si on s'en éloigne ou trop loin."""
    if trend is None or trend == 0 or (target - value) / trend <= 0:
        return None
    eta = (target - value) / trend * WINDOW_S
    return eta if eta <= MAX_ETA_S else None


class WeatherCalculator:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple | None = None
        self._rain = _Trend()
        self._wet = _Trend()
        self._track = _Trend()

    def _slots(self, snap: Snapshot) -> list[WeatherSlot]:
        length, elapsed = snap.session_length_s, snap.session_elapsed_s
        progress = snap.session_info.progress
        slots = []
        for node in sorted(snap.weather_forecast, key=lambda n: n.at):
            slot = WeatherSlot(sky=node.sky, sky_label=SKY.get(node.sky, ""), air_temp_c=node.air_temp_c,
                               rain_chance_pct=round(node.rain_chance_pct))
            if length and elapsed is not None and not snap.max_laps:
                slot.in_s = round(node.at * length - elapsed, 1)
                slot.past = slot.in_s <= 0
                if node.at >= 1:
                    slot.label = "à la fin"
                elif node.at <= 0:
                    slot.label = "au départ"
                else:
                    slot.label = f"il y a {fmt_minutes(-slot.in_s)}" if slot.past else f"dans {fmt_minutes(slot.in_s)}"
            else:
                slot.past = progress is not None and node.at < progress
                slot.label = "au départ" if node.at <= 0 else "à la fin" if node.at >= 1 else f"à {round(node.at * 100)} %"
            slots.append(slot)
        return slots

    @staticmethod
    def _headline(w: WeatherInfo) -> tuple[str, str]:
        upcoming = [s for s in w.slots if not s.past]
        raining = (w.rain_pct or 0) > 0
        if raining:
            text = f"Pluie en cours ({round(w.rain_pct)} %)"
            dry = next((s for s in upcoming if s.rain_chance_pct < RAIN_POSSIBLE_PCT and s.sky < RAINY_SKY), None)
            if dry is not None:
                text += f" · éclaircie prévue {dry.label}"
            return text, "rain"
        likely = next((s for s in upcoming if s.rain_chance_pct >= RAIN_LIKELY_PCT or s.sky >= RAINY_SKY), None)
        if likely is not None:
            return f"Pluie probable {likely.label} ({round(likely.rain_chance_pct)} %)", "rain"
        possible = next((s for s in upcoming if s.rain_chance_pct >= RAIN_POSSIBLE_PCT), None)
        if possible is not None:
            return f"Risque de pluie {possible.label} ({round(possible.rain_chance_pct)} %)", "warn"
        if (w.wetness_pct or 0) >= DRY_PCT:
            return "Piste encore mouillée", "warn"
        if w.from_game:
            return "Pas de pluie prévue", ""
        return "Temps sec", ""

    def update(self, snap: Snapshot) -> Snapshot:
        if not snap.connected:
            return snap
        key = (snap.session, snap.track)
        if key != self._key:
            self.reset()
            self._key = key

        w = WeatherInfo(from_game=bool(snap.weather_forecast))
        w.slots = self._slots(snap)
        w.rain_pct = None if snap.raining is None else round(100 * snap.raining)
        w.wetness_pct = None if snap.wetness is None else round(100 * snap.wetness)
        w.air_temp_c = None if snap.air_temp_c is None else round(snap.air_temp_c, 1)
        w.track_temp_c = None if snap.track_temp_c is None else round(snap.track_temp_c, 1)
        t = snap.session_elapsed_s
        if t is not None:
            w.rain_trend_pct = self._rain.update(t, None if snap.raining is None else 100 * snap.raining)
            w.wetness_trend_pct = self._wet.update(t, None if snap.wetness is None else 100 * snap.wetness)
            w.track_temp_trend_c = self._track.update(t, snap.track_temp_c)
        if w.track_temp_c is not None and w.track_temp_trend_c is not None:
            w.track_temp_in_30min_c = round(w.track_temp_c + 3 * w.track_temp_trend_c, 1)
        if w.wetness_pct is not None and w.wetness_trend_pct:
            wet = 100 * snap.wetness
            if w.wetness_trend_pct < 0 and wet >= DRY_PCT:
                eta = _eta(wet, w.wetness_trend_pct, DRY_PCT)
                if eta is not None:
                    w.eta_label = f"Piste sèche dans ≈ {fmt_minutes(eta)}"
            elif w.wetness_trend_pct > 0 and wet < WET_PCT:
                eta = _eta(wet, w.wetness_trend_pct, WET_PCT)
                if eta is not None:
                    w.eta_label = f"Piste mouillée à {round(WET_PCT)} % dans ≈ {fmt_minutes(eta)}"
        w.headline, w.level = self._headline(w)
        snap.weather = w
        return snap
