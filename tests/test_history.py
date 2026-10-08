import types

import pytest
from fastapi.testclient import TestClient

import lmu_assistant.sources.mock as mock
from lmu_assistant.history import HistoryRecorder, HistoryStore
from lmu_assistant.server import Broadcaster, create_app


class Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


@pytest.fixture
def run_mock(monkeypatch):
    """Fait tourner la source mock et tous les calculs du serveur avec une horloge simulée."""
    clock = Clock()
    monkeypatch.setattr(mock, "time", types.SimpleNamespace(monotonic=clock.monotonic))

    def run(seconds, recorder, step=0.5):
        b = Broadcaster(mock.MockSource(), hz=10, records_path=None, history=recorder)
        n = int(seconds / step)
        for _ in range(n):
            b.compute(b.source.read())
            clock.t += step
        return b

    return run


def test_mock_laps_are_recorded(run_mock):
    store = HistoryStore(":memory:")
    run_mock(3 * 226 + 10, HistoryRecorder(store, "on"))
    sessions = store.sessions()
    assert len(sessions) == 1 and sessions[0]["track"] == "Circuit de la Sarthe" and sessions[0]["driver"] == "Vous"
    laps = store.laps(sessions[0]["id"], with_trace=True)
    assert [lap["lap"] for lap in laps] == [1, 2, 3]
    lap = laps[1]
    assert lap["valid"] or lap["invalid"]
    assert abs(lap["s1"] + lap["s2"] + lap["s3"] - lap["time_s"]) < 0.01
    assert 3.0 < lap["fuel_used"] < 3.8 and 3.8 < lap["energy_used"] < 4.4
    assert len(lap["wear"]) == 4 and lap["track_temp"] is not None
    assert len(lap["trace"]["t"]) == 200 and lap["trace"]["t"][100] > 100


def test_auto_mode_ignores_mock(run_mock):
    store = HistoryStore(":memory:")
    run_mock(500, HistoryRecorder(store, "auto"))
    assert store.sessions() == []


def test_pit_stop_detected(run_mock):
    store = HistoryStore(":memory:")
    # 90 L, 3,4 L/tour, plein sous 8 L → arrêt au début du tour 26 environ
    run_mock(27 * 226, HistoryRecorder(store, "on"), step=1.0)
    laps = store.laps(store.sessions()[0]["id"])
    stops = [lap for lap in laps if lap["stop"]]
    assert stops and all(lap["pit"] and lap["refuel"] for lap in stops)
    assert stops[0]["fuel_used"] is None


def test_history_api(tmp_path):
    app = create_app(mock.MockSource(), hz=50, config_path=tmp_path / "c.json", records_path=None,
                     history_path=tmp_path / "h.sqlite")
    store = app.state.history
    sid = store.new_session(source="lmu", session="Course 1", track="Spa", car="GT3")
    lap_id = store.add_lap(sid, lap=1, time_s=140.5, valid=True, wear=[1, 1, 1, 1], trace={"t": [1], "v": [2]})
    with TestClient(app) as client:
        assert client.get("/api/history/sessions").json()[0]["best_s"] == 140.5
        body = client.get(f"/api/history/sessions/{sid}").json()
        assert body["laps"][0]["wear"] == [1, 1, 1, 1] and "trace" not in body["laps"][0]
        assert client.get(f"/api/history/laps/{lap_id}").json()["trace"] == {"t": [1], "v": [2]}
        assert client.get(f"/api/history/compare?a={lap_id}&b={lap_id}").json()["sectors"][3]["diff"] == 0.0
        assert client.get(f"/api/history/compare?a={lap_id}&b=999").status_code == 404
        assert body["theoretical"]["best_lap_s"] == 140.5
        assert client.delete(f"/api/history/sessions/{sid}").status_code == 200
        assert client.get(f"/api/history/sessions/{sid}").status_code == 404
        assert "Historique des tours" in client.get("/analyse.html").text


def test_live_stint_widget_without_database(run_mock):
    b = run_mock(27 * 226, HistoryRecorder(None, "auto"), step=1.0)
    s = b.compute(b.source.read()).stint
    # arrêt vers le tour 24 (consommation simulée aléatoire à ±5 %)
    assert s.number == 2 and 21 <= s.start_lap <= 26 and s.laps >= 1 and s.tyre_age_laps == s.laps
    assert s.avg_s and s.worst_wheel and s.wear_left_pct > 80
