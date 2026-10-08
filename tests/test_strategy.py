from fastapi.testclient import TestClient

from lmu_assistant.server import create_app
from lmu_assistant.sources import get_source
from lmu_assistant.strategy import StrategyInput, plan, simulate


def params(**kw):
    base = dict(race_laps=50, lap_time_s=100.0, fuel_per_lap=4.0, tank_l=60.0, pit_lane_s=30.0,
                refuel_l_per_s=2.0, tyre_change_s=20.0, tyre_life_laps=30, deg_s_per_lap=0.0)
    base.update(kw)
    return StrategyInput(**base)


def test_lap_race_stops_and_splash():
    r = simulate(params())
    # 15 tours par plein : arrêts après T15, T30, T45 ; le dernier plein ne remet que 5 tours
    assert r["laps"] == 50 and r["stops"] == 3
    assert [s["laps"] for s in r["stints"]] == [15, 15, 15, 5]
    assert r["stints"][1]["fuel_added"] == 60.0 and r["stints"][3]["fuel_added"] == 20.0
    # pneus : 30 tours au plus → changés au 2e arrêt seulement (15 + 15 = 30, puis 15 de plus dépasserait)
    assert [s["tyres"] for s in r["stints"]] == [True, False, True, False]
    assert r["stints"][1]["stop_s"] == 30 + 30.0 and r["stints"][2]["stop_s"] == 30 + 30 + 20


def test_timed_race_finishes_lap_in_progress():
    r = simulate(params(race_laps=None, race_duration_s=1050.0, tank_l=100.0))
    assert r["laps"] == 11 and r["stops"] == 0  # 10 tours = 1000 s < 1050 s : on boucle le 11e


def test_energy_limits_and_margin():
    r = simulate(params(energy_per_lap=10.0, race_laps=25, tank_l=100.0, energy_pct_per_s=5.0))
    assert [s["laps"] for s in r["stints"]] == [10, 10, 5]
    r = simulate(params(race_laps=20, tank_l=100.0, margin_laps=1.0))
    assert r["stops"] == 0  # 100 L pour 80 L + 1 tour de marge


def test_scenarios_saving_can_save_a_stop():
    # 31 tours à 4 L avec 60 L : 2 arrêts ; à −4 % (3,84 L) 15,6 tours par plein → toujours 2 ; à −10 % : 16,6 → 1 arrêt
    out = plan(params(race_laps=31, saving_pct=10.0, saving_cost_s=0.2))["scenarios"]
    base, saving, tyres = out
    assert base["stops"] == 2 and saving["stops"] == 1
    assert saving["vs_base_s"] < 0 and saving.get("best")
    assert all(s["tyres"] for s in tyres["stints"])


def test_strategy_api():
    app = create_app(get_source("mock"), hz=50, records_path=None, history_path=None)
    with TestClient(app) as client:
        d = client.get("/api/strategy/defaults").json()["values"]
        assert d["tank_l"] > 0 and d["lap_time_s"] > 0
        r = client.post("/api/strategy", json=d).json()
        assert [s["key"] for s in r["scenarios"]] == ["base", "saving", "tyres"]
        assert client.post("/api/strategy", json={"lap_time_s": 100}).status_code == 422
