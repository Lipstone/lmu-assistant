import pytest

from lmu_assistant.fuel import FuelCalculator
from lmu_assistant.model import Snapshot
from lmu_assistant.sources.mock import MockSource


def snap(lap, fuel, t=0.0, **kw):
    kw.setdefault("session", "Course 1")
    kw.setdefault("last_lap_s", 200.0)
    return Snapshot(connected=True, lap=lap, fuel_l=fuel, current_lap_s=t, **kw)


def drive(calc, laps):
    """laps = [(lap, carburant au passage de ligne, kwargs)] ; renvoie le dernier Snapshot."""
    out = None
    for lap, fuel, *kw in laps:
        out = calc.update(snap(lap, fuel, **(kw[0] if kw else {})))
    return out


def test_no_data_before_first_full_lap():
    calc = FuelCalculator()
    s = drive(calc, [(3, 50.0, {"t": 80.0}), (4, 47.0)])  # 3e tour pris en route : ignoré
    assert s.fuel.avg_lap is None and s.fuel.valid_laps == 0


def test_last_average_and_laps_left():
    calc = FuelCalculator()
    s = drive(calc, [(1, 60.0), (2, 57.0), (3, 53.0), (4, 50.0)])
    assert s.fuel.last_lap == 3.0
    assert s.fuel.avg_lap == pytest.approx(10 / 3, abs=1e-3)
    assert s.fuel.laps_left == pytest.approx(50 / (10 / 3), abs=0.01)
    assert s.fuel.valid_laps == 3


def test_average_uses_last_n_laps():
    calc = FuelCalculator(avg_laps=2)
    s = drive(calc, [(1, 60.0), (2, 50.0), (3, 47.0), (4, 44.0)])  # 1er tour à 10 L oublié
    assert s.fuel.avg_lap == 3.0


def test_pit_and_refuel_laps_excluded():
    calc = FuelCalculator()
    s = drive(
        calc,
        [
            (1, 60.0),
            (2, 57.0),  # tour 1 valide : 3 L
            (2, 56.0, {"in_pits": True, "t": 50.0}),  # passage au stand pendant le tour 2
            (3, 54.0),  # tour 2 ignoré
            (3, 90.0, {"t": 30.0}),  # ravitaillement pendant le tour 3
            (4, 88.0),  # tour 3 ignoré
            (5, 85.0),  # tour 4 valide : 3 L
        ],
    )
    assert s.fuel.valid_laps == 2
    assert s.fuel.avg_lap == 3.0


def test_reset_on_new_session():
    calc = FuelCalculator()
    drive(calc, [(1, 60.0), (2, 57.0), (3, 54.0)])
    s = calc.update(snap(1, 90.0, session="Course 2"))
    assert s.fuel.valid_laps == 0


def test_lap_race_fuel_to_add():
    calc = FuelCalculator()
    race = {"max_laps": 10}
    drive(calc, [(1, 60.0, race), (2, 57.0, race), (3, 54.0, race)])  # 3 L/tour
    # Début du tour 4 d'une course en 10 tours : 7 tours à faire = 21 L
    s = calc.update(snap(4, 51.0, lap_fraction=0.0, **race))
    assert s.fuel.laps_to_finish == 7.0
    assert s.fuel.to_add == 0.0
    s = calc.update(snap(4, 20.0, t=20.0, lap_fraction=0.1, **race))  # (fuite fictive) 6,9 tours = 20,7 L
    assert s.fuel.laps_to_finish == pytest.approx(6.9)
    assert s.fuel.to_add == pytest.approx(0.7)


def test_timed_race_rounds_to_next_line():
    calc = FuelCalculator()
    drive(calc, [(1, 60.0), (2, 57.0), (3, 54.0)])  # 3 L/tour, tours de 200 s
    # À mi-tour, 450 s restantes : 0,5 + 2,25 = 2,75 → on finit au 3e passage de ligne → 2,5 tours à faire
    s = calc.update(snap(3, 52.5, t=100.0, lap_fraction=0.5, session_time_left_s=450.0))
    assert s.fuel.laps_to_finish == 2.5
    assert s.fuel.to_add == 0.0  # 7,5 L nécessaires, 52,5 à bord
    s = calc.update(snap(3, 5.0, t=101.0, lap_fraction=0.5, session_time_left_s=450.0))
    assert s.fuel.to_add == 2.5


def test_disconnected_snapshot_untouched():
    s = FuelCalculator().update(Snapshot())
    assert s.fuel.avg_lap is None


def test_mock_pits_when_low():
    src = MockSource()
    src._fuel = 5.0
    src._lap_start -= src._lap_target  # force le passage de ligne
    s = src.read()
    assert s.in_pits and s.fuel_l == pytest.approx(90.0)
    assert 0.0 <= s.lap_fraction <= 1.0


def test_virtual_energy_tracked_like_fuel():
    calc = FuelCalculator()
    # 3 L et 4 % par tour ; course en 10 tours
    race = {"max_laps": 10}
    for lap, fuel, ve in [(1, 60.0, 100.0), (2, 57.0, 96.0), (3, 54.0, 92.0)]:
        s = calc.update(snap(lap, fuel, virtual_energy_pct=ve, **race))
    e = s.energy
    assert e.unit == "%" and s.fuel.unit == "L"
    assert e.last_lap == 4.0 and e.avg_lap == 4.0 and e.valid_laps == 2
    assert e.laps_left == 23.0
    # Début du tour 3 : 8 tours à faire = 32 %, 92 % à bord
    assert e.laps_to_finish == 8.0 and e.to_add == 0.0
    s = calc.update(snap(3, 53.0, t=5.0, lap_fraction=0.0, virtual_energy_pct=20.0, **race))
    assert s.energy.to_add == 12.0


def test_energy_refill_invalidates_lap():
    calc = FuelCalculator()
    calc.update(snap(1, 60.0, virtual_energy_pct=50.0))
    calc.update(snap(2, 57.0, virtual_energy_pct=46.0))
    calc.update(snap(2, 56.0, t=60.0, virtual_energy_pct=100.0))  # énergie remise sans changer le carburant
    s = calc.update(snap(3, 54.0, virtual_energy_pct=98.0))
    assert s.energy.valid_laps == 1 and s.fuel.valid_laps == 1


def test_car_without_energy():
    calc = FuelCalculator()
    s = drive(calc, [(1, 60.0), (2, 57.0), (3, 54.0)])
    assert s.energy.avg_lap is None and s.energy.valid_laps == 0
    assert s.fuel.avg_lap == 3.0


def test_mock_has_virtual_energy():
    s = MockSource().read()
    assert s.virtual_energy_pct == pytest.approx(100.0, abs=0.5)
