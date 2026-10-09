from lmu_assistant.model import ForecastNode, Snapshot
from lmu_assistant.session import SessionCalculator
from lmu_assistant.sources.lmu_shared_memory import forecast_for, parse_weather
from lmu_assistant.weather import WeatherCalculator


def snap(**kw):
    base = dict(connected=True, session="Course 1", track="Spa", game_phase=5, session_length_s=3600.0,
                session_elapsed_s=1000.0, raining=0.0, wetness=0.0, air_temp_c=20.0, track_temp_c=30.0)
    base.update(kw)
    return Snapshot(**base)


def compute(calc, s):
    return calc.update(SessionCalculator().update(s)).weather


FORECAST = [ForecastNode(at=0.0, sky=1, air_temp_c=20.0, rain_chance_pct=0.0),
            ForecastNode(at=0.25, sky=2, air_temp_c=21.0, rain_chance_pct=10.0),
            ForecastNode(at=0.5, sky=7, air_temp_c=19.0, rain_chance_pct=70.0),
            ForecastNode(at=0.75, sky=3, air_temp_c=18.0, rain_chance_pct=30.0),
            ForecastNode(at=1.0, sky=0, air_temp_c=17.0, rain_chance_pct=0.0)]


def node(sky, temp, rain):
    return {"WNV_SKY": {"currentValue": sky}, "WNV_TEMPERATURE": {"currentValue": temp},
            "WNV_RAIN_CHANCE": {"currentValue": rain}}


def test_parse_weather_answer():
    race = {k: node(i, 20 + i, 10 * i) for i, k in enumerate(("START", "NODE_25", "NODE_50", "NODE_75", "FINISH"))}
    out = parse_weather({"RACE": race, "QUALIFY": {"START": node(1, 20, 0)}, "PRACTICE": "?"})
    assert list(out) == ["RACE"]  # qualif incomplète et essais illisibles ignorés
    assert [n.at for n in out["RACE"]] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert out["RACE"][2] == ForecastNode(at=0.5, sky=2, air_temp_c=22.0, rain_chance_pct=20.0)
    assert parse_weather(None) == {}
    assert forecast_for(out, "Course 1") == out["RACE"] and forecast_for(out, "Warm-up") == out["RACE"]
    assert forecast_for(out, "Essais 2") == []


def test_forecast_slots_and_headline():
    w = compute(WeatherCalculator(), snap(weather_forecast=FORECAST, session_elapsed_s=800.0))
    assert w.from_game and len(w.slots) == 5
    assert [s.past for s in w.slots] == [True, False, False, False, False]
    assert [s.label for s in w.slots] == ["au départ", "dans 2 min", "dans 17 min", "dans 32 min", "à la fin"]
    assert w.slots[2].sky_label == "couvert, pluie fine" and w.slots[2].in_s == 1000.0
    assert (w.headline, w.level) == ("Pluie probable dans 17 min (70 %)", "rain")


def test_headline_without_forecast_and_while_raining():
    assert compute(WeatherCalculator(), snap()).headline == "Temps sec"
    dry = [ForecastNode(at=a, sky=1) for a in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert compute(WeatherCalculator(), snap(weather_forecast=dry)).headline == "Pas de pluie prévue"
    w = compute(WeatherCalculator(), snap(raining=0.3, weather_forecast=FORECAST, session_elapsed_s=2000.0))
    assert w.headline == "Pluie en cours (30 %) · éclaircie prévue à la fin" and w.level == "rain"


def test_lap_race_slots_use_progress():
    w = compute(WeatherCalculator(), snap(max_laps=20, lap=11, lap_fraction=0.0, weather_forecast=FORECAST))
    assert [s.label for s in w.slots] == ["au départ", "à 25 %", "à 50 %", "à 75 %", "à la fin"]
    assert [s.past for s in w.slots] == [True, True, False, False, False] and w.slots[2].in_s is None


def test_estimated_trends_and_drying_eta():
    calc = WeatherCalculator()
    w = None
    for i in range(41):  # 10 min, la piste sèche de 50 % à 30 %, la piste chauffe de 2 °C
        t = 1000.0 + 15 * i
        w = compute(calc, snap(session_elapsed_s=t, wetness=0.5 - 0.2 * i / 40, track_temp_c=30.0 + 2 * i / 40))
    assert w.wetness_trend_pct == -20.0 and w.track_temp_trend_c == 2.0
    assert w.track_temp_in_30min_c == 38.0
    assert w.eta_label == "Piste sèche dans ≈ 12 min"  # 30 % → 5 % à 20 points / 10 min
    assert w.headline == "Piste encore mouillée" and w.level == "warn"
    # nouvelle session : on repart de zéro
    assert compute(calc, snap(session="Course 2", session_elapsed_s=5.0)).wetness_trend_pct is None


def test_wetting_eta():
    calc = WeatherCalculator()
    w = None
    for i in range(9):  # 2 min, piste de 0 à 10 %
        w = compute(calc, snap(session_elapsed_s=1000.0 + 15 * i, raining=0.2, wetness=0.1 * i / 8))
    assert w.wetness_trend_pct == 50.0
    assert w.eta_label == "Piste mouillée à 30 % dans ≈ 4 min"
