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
    mock.random.seed(7)  # tours invalidés et consommation de la source mock : tirages reproductibles

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


def test_conditions_recorded_every_30_s(run_mock):
    store = HistoryStore(":memory:")
    run_mock(600, HistoryRecorder(store, "on"))
    sid = store.sessions()[0]["id"]
    c = store.conditions(sid)
    assert 19 <= len(c) <= 21 and c[1]["session_time_s"] - c[0]["session_time_s"] >= 30
    assert c[0]["track_temp"] is not None and c[0]["grip"] == 3


def test_exports_report_and_notes(tmp_path):
    app = create_app(mock.MockSource(), hz=50, config_path=tmp_path / "c.json", records_path=None,
                     history_path=tmp_path / "h.sqlite")
    store = app.state.history
    sid = store.new_session(source="lmu", session="Course 1", track="Spa", car="GT3")
    store.add_lap(sid, lap=1, time_s=140.5, valid=True, fuel_used=3.25, driver="Rémy", position=4)
    store.add_lap(sid, lap=2, time_s=141.0, valid=True, fuel_used=3.35, driver="Rémy", position=3, impacts=1)
    with TestClient(app) as client:
        r = client.get(f"/api/history/sessions/{sid}").json()["report"]
        assert r["pace"]["best_s"] == 140.5 and r["consumption"]["fuel_used"] == 6.6
        assert r["incidents"]["impact_laps"] == [2] and r["positions"] == {"start": 4, "end": 3, "best": 3}
        csv = client.get(f"/api/history/sessions/{sid}/laps.csv")
        assert csv.headers["content-disposition"].startswith("attachment")
        text = csv.content.decode("utf-8-sig")
        assert text.splitlines()[0].startswith("tour;") and text.splitlines()[1].startswith("1;140,5")
        intl = client.get(f"/api/history/sessions/{sid}/laps.csv?excel=false").text
        assert intl.splitlines()[0].startswith("tour,") and "140.5" in intl
        assert client.get(f"/api/history/sessions/{sid}/stints.csv").status_code == 200
        note = client.post("/api/notes", json={"car": "GT3", "track": "Spa", "session_id": sid,
                                               "title": "Aileron −1", "text": "plus stable"}).json()
        dump = client.get(f"/api/history/sessions/{sid}/export.json").json()
        assert len(dump["laps"]) == 2 and dump["notes"][0]["title"] == "Aileron −1"
        assert client.put(f"/api/notes/{note['id']}", json={"car": "GT3", "track": "Spa", "title": "x"}).json()["title"] == "x"
        assert [n["id"] for n in client.get("/api/notes?car=GT3&track=Spa").json()] == [note["id"]]
        assert client.get("/api/notes?car=GT3&track=Monza").json() == []
        client.delete(f"/api/history/sessions/{sid}")
        assert client.get("/api/notes?car=GT3&track=Spa").json()[0]["session_id"] is None
        assert client.delete(f"/api/notes/{note['id']}").status_code == 200
        assert client.get("/api/notes").json() == []


def test_bulk_delete_and_compare_sessions(tmp_path):
    app = create_app(mock.MockSource(), hz=50, config_path=tmp_path / "c.json", records_path=None,
                     history_path=tmp_path / "h.sqlite")
    store = app.state.history
    sids = [store.new_session(source="lmu", session="Essais", track="Spa", car="GT3") for _ in range(4)]
    for k, sid in enumerate(sids[:3]):
        for lap in (1, 2, 3):
            store.add_lap(sid, lap=lap, time_s=140.0 + k + lap / 10, valid=True, s1=40.0 + k, s2=50.0, s3=50.0 + lap / 10,
                          trace={"t": [10.0 + k, 20.0 + k], "v": [200, 210]})
    with TestClient(app) as client:
        c = client.get(f"/api/history/compare-sessions?ids={sids[1]},{sids[0]},{sids[3]}").json()
        assert c["reference"] == sids[0]
        by_id = {s["session"]["id"]: s for s in c["sessions"]}
        assert [s["session"]["id"] for s in c["sessions"]] == [sids[1], sids[0], sids[3]]
        assert by_id[sids[1]]["best_vs_ref"]["sectors"][3]["diff"] == 1.0
        assert by_id[sids[1]]["best_vs_ref"]["delta"][0] == [0.0, 1.0]
        assert by_id[sids[0]]["laps"][0] == [1, 140.1]
        assert by_id[sids[3]]["best_lap"] is None and "best_vs_ref" not in by_id[sids[3]]
        assert client.get(f"/api/history/compare-sessions?ids={sids[0]}").status_code == 400
        assert client.get(f"/api/history/compare-sessions?ids={sids[0]},999").status_code == 404
        r = client.post("/api/history/sessions/delete", json={"ids": [sids[0], sids[2], 999]})
        assert r.json() == {"deleted": [sids[0], sids[2]]}
        assert [s["id"] for s in client.get("/api/history/sessions").json()] == [sids[3], sids[1]]
        assert store.laps(sids[0]) == []
        assert "Comparaison de sessions" in client.get("/analyse.html").text
