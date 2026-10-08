from lmu_assistant.brakes import HYSTERESIS_C, BrakesCalculator
from lmu_assistant.model import Snapshot, Wheel


def snap(lap, temps, **kw):
    kw.setdefault("session", "Course 1")
    return Snapshot(connected=True, lap=lap, wheels=[Wheel(brake_temp_c=t) for t in temps], **kw)


def test_peaks_per_lap():
    calc = BrakesCalculator()
    calc.update(snap(1, [400, 500, 300, 300]))
    s = calc.update(snap(1, [700, 450, 350, 320]))
    assert s.brakes.peak_lap_c == [700, 500, 350, 320] and s.brakes.peak_last_lap_c is None
    s = calc.update(snap(2, [200, 200, 200, 200]))
    assert s.brakes.peak_last_lap_c == [700, 500, 350, 320]
    assert s.brakes.peak_lap_c == [200, 200, 200, 200]


def test_overheat_alert_with_hysteresis():
    calc = BrakesCalculator()
    assert calc.update(snap(1, [790, 0, 0, 0]), 800).brakes.overheat == [False] * 4
    assert calc.update(snap(1, [820, 0, 0, 0]), 800).brakes.overheat[0]
    assert calc.update(snap(1, [800 - HYSTERESIS_C + 5, 0, 0, 0]), 800).brakes.overheat[0]  # encore chaud
    assert not calc.update(snap(1, [700, 0, 0, 0]), 800).brakes.overheat[0]
    assert calc.update(snap(1, [700, 0, 0, 0]), 650).brakes.threshold_c == 650


def test_reset_on_new_session():
    calc = BrakesCalculator()
    calc.update(snap(1, [900, 0, 0, 0]))
    s = calc.update(snap(1, [100, 0, 0, 0], session="Course 2"))
    assert s.brakes.peak_lap_c[0] == 100 and not s.brakes.overheat[0]
