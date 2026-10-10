import statistics

import pytest

from lmu_assistant.laptimes import LapTimesCalculator
from lmu_assistant.model import Snapshot


def snap(lap, last=None, t=0.0, **kw):
    kw.setdefault("session", "Course 1")
    return Snapshot(connected=True, lap=lap, last_lap_s=last, current_lap_s=t, **kw)


def drive(calc, laps, avg_laps=5):
    """laps = [(tour, dernier temps publié, kwargs)] ; renvoie le dernier Snapshot."""
    out = None
    for lap, last, *kw in laps:
        out = calc.update(snap(lap, last, **(kw[0] if kw else {})), avg_laps)
    return out


def test_average_and_regularity_of_last_valid_laps():
    calc = LapTimesCalculator()
    times = [210.0, 211.0, 209.5, 210.5]
    s = drive(calc, [(1, None)] + [(i + 2, t) for i, t in enumerate(times)])
    info = s.laps
    assert info.valid_laps == 4 and info.avg_count == 4
    assert info.avg_s == pytest.approx(sum(times) / 4)
    assert info.stdev_s == pytest.approx(statistics.stdev(times), abs=1e-3)
    assert info.best_valid_s == 209.5
    assert [e.lap for e in info.recent] == [4, 3, 2, 1]  # le plus récent d'abord
    assert [e.vs_best for e in info.recent] == [1.0, 0.0, 1.5, 0.5]


def test_average_uses_last_n_laps():
    calc = LapTimesCalculator()
    s = drive(calc, [(1, None), (2, 230.0), (3, 210.0), (4, 212.0)], avg_laps=2)
    assert s.laps.avg_s == 211.0 and s.laps.avg_count == 2


def test_pit_invalid_and_partial_laps_excluded():
    calc = LapTimesCalculator()
    s = drive(
        calc,
        [
            (3, None, {"t": 80.0}),  # appli lancée en cours de tour : tour 3 partiel
            (4, 215.0),
            (4, 215.0, {"t": 50.0, "lap_invalid": True}),  # tour 4 invalidé (limites de piste)
            (5, 205.0),
            (5, 205.0, {"t": 30.0}),
            (6, 210.0),  # tour 5 valide
            (6, 210.0, {"t": 10.0, "in_pits": True}),  # tour 6 : rentrée au stand
            (7, 240.0),
        ],
    )
    info = s.laps
    assert [(e.lap, e.valid, e.pit, e.invalid) for e in info.recent] == [
        (6, False, True, False),
        (5, True, False, False),
        (4, False, False, True),
        (3, False, False, False),
    ]
    assert info.valid_laps == 1 and info.avg_s == 210.0
    assert info.stdev_s is None  # il faut au moins 2 tours


def test_lap_time_published_after_the_line():
    calc = LapTimesCalculator()
    drive(calc, [(1, None), (2, 200.0)])
    s = drive(calc, [(3, 200.0, {"t": 0.1}), (3, 201.5, {"t": 0.3})])  # temps du tour 2 publié 0,2 s plus tard
    assert [(e.lap, e.time_s) for e in s.laps.recent] == [(2, 201.5), (1, 200.0)]


def test_reset_on_new_session():
    calc = LapTimesCalculator()
    drive(calc, [(1, None), (2, 200.0), (3, 201.0)])
    s = drive(calc, [(1, None, {"session": "Course 2"})])
    assert s.laps.recent == [] and s.laps.avg_s is None


def test_invalid_lap_without_game_time_uses_measured_duration():
    # LMU ne publie pas de temps (<= 0, donc None) pour un tour invalidé : durée entre deux départs de tour.
    calc = LapTimesCalculator()
    drive(calc, [(1, None, {"lap_start_et": 100.0}), (2, 200.0, {"t": 0.1, "lap_start_et": 300.0})])
    s = drive(calc, [
        (2, 200.0, {"t": 50.0, "lap_start_et": 300.0, "lap_invalid": True}),
        (3, None, {"t": 0.1, "lap_start_et": 503.25}),
    ])
    assert [(e.lap, e.time_s, e.valid, e.invalid) for e in s.laps.recent] == [
        (2, 203.25, False, True), (1, 200.0, True, False)]
    assert s.laps.avg_s == 200.0


def test_measured_duration_waits_for_telemetry():
    # Le numéro de tour change avant le départ du tour en télémétrie : la durée du tour précédent ne compte pas,
    # et le tour n'est pas abandonné parce que le chrono affiche encore le temps du tour fini.
    calc = LapTimesCalculator()
    drive(calc, [(1, None, {"lap_start_et": 0.0}), (2, 200.0, {"t": 0.1, "lap_start_et": 200.0})])
    s = drive(calc, [
        (3, 200.0, {"t": 201.2, "lap_start_et": 200.0}),  # télémétrie en retard : encore le départ du tour 2
        (3, 200.0, {"t": 0.05, "lap_start_et": 401.3}),
        (3, None, {"t": 0.3, "lap_start_et": 401.3}),  # tour invalidé : pas de temps du jeu
    ])
    assert [(e.lap, e.time_s, e.invalid) for e in s.laps.recent] == [(2, 201.3, True), (1, 200.0, False)]
