from lmu_assistant.model import Snapshot, Vehicle
from lmu_assistant.opponents import OpponentsCalculator, damage_pct
from lmu_assistant.relative import compute_relative
from lmu_assistant.standings import compute_standings


def snap(*vehicles):
    return Snapshot(connected=True, session="Course", track="Spa", vehicles=list(vehicles))


def car(laps, fuel=None, energy=None, in_pits=False, pitstops=0, **kw):
    return Vehicle(id=1, laps=laps, lap_fraction=0.5, fuel_l=fuel, energy_pct=energy, in_pits=in_pits,
                   pitstops=pitstops, position=1, **kw)


def test_damage_pct():
    assert damage_pct(None) is None
    assert damage_pct([0] * 8) == 100.0
    assert damage_pct([2, 1, 0, 0, 0, 0, 1, 0]) == 75.0


def test_consumption_needs_a_full_lap_seen_from_the_line():
    calc = OpponentsCalculator()
    v = calc.update(snap(car(4, 50.0, 80.0))).vehicles[0]  # vue en cours de tour : pas de mesure
    assert v.fuel_per_lap is None
    calc.update(snap(car(5, 47.0, 76.0)))  # 1er passage : point de départ (tour 4 incomplet ignoré)
    v = calc.update(snap(car(6, 43.6, 71.9))).vehicles[0]
    assert v.fuel_per_lap == 3.4 and v.energy_per_lap == 4.1
    v = calc.update(snap(car(7, 40.4, 67.9))).vehicles[0]
    assert v.fuel_per_lap == 3.3 and v.energy_per_lap == 4.05


def test_consumption_ignores_pit_laps_and_refuels():
    calc = OpponentsCalculator()
    calc.update(snap(car(5, 47.0)))
    calc.update(snap(car(6, 43.0)))
    assert calc.update(snap(car(7, 39.0))).vehicles[0].fuel_per_lap == 4.0
    calc.update(snap(car(7, 38.0, in_pits=True)))  # arrêt pendant le tour 8
    v = calc.update(snap(car(8, 90.0, pitstops=1))).vehicles[0]  # plein : ignoré
    assert v.fuel_per_lap == 4.0
    v = calc.update(snap(car(9, 87.0, pitstops=1))).vehicles[0]
    assert v.fuel_per_lap == 3.5  # tours mesurés : 4 (tour 7) et 3 (tour 9) ; tour 6 vu en cours de route


def test_unknown_fuel_stays_unknown():
    calc = OpponentsCalculator()
    for lap in range(5, 9):
        v = calc.update(snap(car(lap))).vehicles[0]
    assert v.fuel_per_lap is None and v.energy_per_lap is None and v.damage_pct is None


def test_new_session_resets():
    calc = OpponentsCalculator()
    calc.update(snap(car(5, 47.0)))
    calc.update(snap(car(6, 43.0)))
    other = Snapshot(connected=True, session="Qualif", track="Spa", vehicles=[car(1, 20.0)])
    assert calc.update(other).vehicles[0].fuel_per_lap is None


def test_fields_reach_relative_and_standings():
    me = Vehicle(id=0, laps=3, lap_fraction=0.5, position=2, is_player=True, best_lap_s=200.0, car_class="H")
    other = Vehicle(id=1, laps=3, lap_fraction=0.6, position=1, car_class="H", dents=[2, 2, 0, 0, 0, 0, 0, 0],
                    wheels_off=1, fuel_l=30.0)
    s = compute_standings(compute_relative(OpponentsCalculator().update(snap(me, other))))
    rel = {r.id: r for r in s.relative}
    assert rel[1].damage_pct == 75.0 and rel[1].wheels_off == 1 and rel[1].fuel_l == 30.0
    assert rel[0].damage_pct is None
    assert s.standings[0].entries[0].damage_pct == 75.0


def test_mock_field_reports_damage_and_consumption(monkeypatch):
    from lmu_assistant.sources import mock

    t = [1000.0]
    monkeypatch.setattr(mock.time, "monotonic", lambda: t[0])
    src = mock.MockSource()
    calc = OpponentsCalculator()
    for _ in range(int(3 * 3600 / 5)):  # 3 h de course, une lecture toutes les 5 s
        t[0] += 5
        s = calc.update(src.read())
    by_number = {v.number: v for v in s.vehicles}
    assert by_number["8"].damage_pct < 100 and by_number["7"].damage_pct == 100
    assert 3.0 < by_number["7"].fuel_per_lap < 3.8 and 3.8 < by_number["7"].energy_per_lap < 4.4
    assert by_number["22"].fuel_per_lap is not None and by_number["22"].energy_per_lap is None  # LMP2 sans EV
    assert by_number["00"].fuel_per_lap is not None


def test_tyre_stints_count_stops_since_tyre_change():
    calc = OpponentsCalculator()
    worn = [0.9] * 4
    assert calc.update(snap(car(5, tyre_wear=worn))).vehicles[0].tyre_stints == 1
    # arrêt sans changer les pneus : 2e relais sur le même train
    calc.update(snap(car(12, in_pits=True, pitstops=1, tyre_wear=[0.8] * 4)))
    assert calc.update(snap(car(12, pitstops=1, tyre_wear=[0.8] * 4))).vehicles[0].tyre_stints == 2
    # arrêt avec pneus neufs (l'usure remonte) : compté à la sortie des stands
    calc.update(snap(car(20, in_pits=True, pitstops=2, tyre_wear=[0.7] * 4)))
    calc.update(snap(car(20, in_pits=True, pitstops=2, tyre_wear=[1.0] * 4)))
    assert calc.update(snap(car(20, pitstops=2, tyre_wear=[1.0] * 4))).vehicles[0].tyre_stints == 1
    assert calc.update(snap(car(21, pitstops=2))).vehicles[0].tyre_stints is None  # usure non transmise


def test_penalties_and_tyre_wear_from_shared_memory_reach_standings():
    v = Vehicle(id=1, laps=3, position=1, car_class="GT3", penalties=2, tyre_wear=[0.95] * 4)
    s = compute_standings(compute_relative(OpponentsCalculator().update(snap(v))))
    e = s.standings[0].entries[0]
    assert e.penalties == 2 and e.tyre_stints == 1
