import json

import pytest

from lmu_assistant.delta import DeltaCalculator, Trace
from lmu_assistant.model import Snapshot
from lmu_assistant.sources.mock import MockSource


def snap(lap, frac, t, **kw):
    kw.setdefault("session", "Course 1")
    kw.setdefault("track", "Spa")
    kw.setdefault("car", "Hypercar")
    return Snapshot(connected=True, lap=lap, lap_fraction=frac, current_lap_s=t, **kw)


def drive_lap(calc, lap, lap_s, pace=lambda f: f, steps=50, start=0.0, **kw):
    """Fait un tour complet : avancement 0..1, temps = pace(avancement) × lap_s ; renvoie le dernier Snapshot."""
    out = None
    for i in range(steps):
        f = start + (1 - start) * i / steps
        out = calc.update(snap(lap, round(f, 4), round(pace(f) * lap_s, 3), **kw))
    return out


def cross_line(calc, lap, last_lap_s, **kw):
    return calc.update(snap(lap, 0.0, 0.0, last_lap_s=last_lap_s, **kw))


def test_trace_interpolation():
    tr = Trace(100.0, [0.0, 0.5, 1.0], [0.0, 40.0, 100.0])
    assert tr.time_at(0.25) == pytest.approx(20.0)
    assert tr.time_at(0.75) == pytest.approx(70.0)
    assert tr.time_at(1.0) == pytest.approx(100.0)


def test_no_reference_before_first_full_lap():
    calc = DeltaCalculator(None)
    drive_lap(calc, 1, 100.0, start=0.4)  # appli lancée en cours de tour : pas une référence
    s = cross_line(calc, 2, 100.0)
    assert s.delta.best_s is None and s.delta.vs_best is None


def test_delta_to_best_and_last():
    calc = DeltaCalculator(None)
    drive_lap(calc, 1, 100.0)
    cross_line(calc, 2, 100.0)
    drive_lap(calc, 2, 102.0)
    s = cross_line(calc, 3, 102.0)
    assert (s.delta.best_s, s.delta.last_s) == (100.0, 102.0)
    # Mi-tour en 50,5 s : +0,5 s sur le meilleur (50 s), −0,5 s sur le dernier (51 s).
    s = calc.update(snap(3, 0.5, 50.5))
    assert s.delta.vs_best == pytest.approx(0.5)
    assert s.delta.vs_last == pytest.approx(-0.5)
    assert s.delta.vs_record is None  # source simulée : pas de record


def test_delta_follows_where_time_is_lost():
    calc = DeltaCalculator(None)
    # Référence : 1re moitié du tour en 40 s, 2e en 60 s.
    drive_lap(calc, 1, 100.0, pace=lambda f: 0.8 * f if f <= 0.5 else 0.4 + 1.2 * (f - 0.5), steps=100)
    cross_line(calc, 2, 100.0)
    assert calc.update(snap(2, 0.5, 42.0)).delta.vs_best == pytest.approx(2.0, abs=0.01)
    assert calc.update(snap(2, 0.75, 70.0)).delta.vs_best == pytest.approx(0.0, abs=0.01)


def test_pit_lap_not_a_reference():
    calc = DeltaCalculator(None)
    drive_lap(calc, 1, 100.0)
    cross_line(calc, 2, 100.0)
    drive_lap(calc, 2, 90.0, in_pits=True)  # tour plus rapide mais passé par les stands
    s = cross_line(calc, 3, 90.0)
    assert s.delta.best_s == 100.0 and s.delta.last_s == 100.0


def test_lap_with_gap_not_a_reference():
    calc = DeltaCalculator(None)
    drive_lap(calc, 1, 100.0, steps=5)  # relevés tous les 20 % du tour
    assert cross_line(calc, 2, 100.0).delta.best_s is None


def test_stale_fraction_at_line_ignored():
    calc = DeltaCalculator(None)
    drive_lap(calc, 1, 100.0)
    cross_line(calc, 2, 100.0)
    drive_lap(calc, 2, 99.0)
    calc.update(snap(3, 0.999, 0.1, last_lap_s=99.0))  # avancement pas encore remis à zéro
    s = drive_lap(calc, 3, 98.0)
    assert s.delta.best_s == 99.0 and s.delta.vs_best is not None
    assert cross_line(calc, 4, 98.0).delta.best_s == 98.0


def test_reset_on_new_session():
    calc = DeltaCalculator(None)
    drive_lap(calc, 1, 100.0)
    cross_line(calc, 2, 100.0)
    s = calc.update(snap(1, 0.0, 0.0, session="Course 2"))
    assert s.delta.best_s is None


def test_absurd_delta_hidden():
    calc = DeltaCalculator(None)
    drive_lap(calc, 1, 100.0)
    cross_line(calc, 2, 100.0)
    assert calc.update(snap(2, 0.2, 80.0)).delta.vs_best is None  # arrêté sur la piste, aux stands…


def test_personal_record_saved_and_reloaded(tmp_path):
    path = tmp_path / "records.json"
    calc = DeltaCalculator(path)
    drive_lap(calc, 1, 100.0, source="lmu")
    cross_line(calc, 2, 100.0, source="lmu")
    drive_lap(calc, 2, 101.0, source="lmu")
    s = cross_line(calc, 3, 101.0, source="lmu")
    assert s.delta.record_s == 100.0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["records"]["Spa | Hypercar"]["lap_s"] == 100.0

    calc = DeltaCalculator(path)  # nouvelle session de l'appli
    s = calc.update(snap(1, 0.5, 49.0, source="lmu"))
    assert s.delta.record_s == 100.0 and s.delta.best_s is None
    assert s.delta.vs_record == pytest.approx(-1.0)
    assert calc.update(snap(1, 0.5, 49.0, source="lmu", car="LMGT3")).delta.record_s is None


def test_mock_and_replay_do_not_touch_records(tmp_path):
    path = tmp_path / "records.json"
    calc = DeltaCalculator(path)
    drive_lap(calc, 1, 100.0, source="mock")
    cross_line(calc, 2, 100.0, source="mock")
    assert not path.exists()


def test_corrupt_records_file_ignored(tmp_path):
    path = tmp_path / "records.json"
    path.write_text("{pas du json", encoding="utf-8")
    s = DeltaCalculator(path).update(snap(1, 0.5, 49.0, source="lmu"))
    assert s.delta.record_s is None


def test_mock_source_gives_delta(monkeypatch):
    import lmu_assistant.sources.mock as mock

    clock = [0.0]
    monkeypatch.setattr(mock.time, "monotonic", lambda: clock[0])
    src, calc = MockSource(), DeltaCalculator(None)
    s = None
    while clock[0] < 2.6 * mock.LAP_S:
        s = calc.update(src.read())
        clock[0] += 0.5
    assert s.delta.best_s is not None and s.delta.vs_best is not None
