from lmu_assistant.model import FuelInfo, LapEntry, LapTimesInfo, Snapshot, Vehicle
from lmu_assistant.pitstop import PitCalculator


def snap(lap=10, frac=0.5, fuel=None, energy=None, ve=None, recent=(), avg=None, vehicles=(), capacity=100.0):
    return Snapshot(
        connected=True, session="Course 1", lap=lap, lap_fraction=frac, fuel_capacity_l=capacity,
        virtual_energy_pct=ve, fuel=fuel or FuelInfo(), energy=energy or FuelInfo(unit="%"),
        laps=LapTimesInfo(recent=list(recent), avg_s=avg), vehicles=list(vehicles),
    )


def test_window_limited_by_energy():
    # carburant : 10 tours restants, 25 par plein ; énergie : 6,2 tours restants, 20 par plein ; 30 tours à faire
    s = snap(fuel=FuelInfo(avg_lap=4.0, laps_left=10.0, laps_to_finish=30.0),
             energy=FuelInfo(unit="%", avg_lap=5.0, laps_left=6.2, laps_to_finish=30.0), ve=31.0)
    p = PitCalculator().update(s).pit
    assert p.limited_by == "énergie" and p.laps_left == 6.2
    assert p.last_lap == 15  # 0,5 + 6,2 → 6 passages de ligne : T10 à T15
    assert p.stops_left == 2 and p.laps_per_stint == 20.0  # (30 − 6,2) / 20 → 2 arrêts
    assert p.window_open_lap == 10  # 2 pleins couvrent 40 tours : fenêtre déjà ouverte


def test_window_opens_later_with_one_stop():
    s = snap(fuel=FuelInfo(avg_lap=4.0, laps_left=10.0, laps_to_finish=30.0))
    p = PitCalculator().update(s).pit
    assert p.limited_by == "carburant" and p.stops_left == 1 and p.last_lap == 19
    # il faut avoir fait au moins 30 − 25 = 5 tours : fin du tour 10 = 0,5 tour, donc T15 (4,5 + 0,5 = 5)
    assert p.window_open_lap == 15


def test_no_stop_needed_and_must_pit_now():
    p = PitCalculator().update(snap(fuel=FuelInfo(avg_lap=4.0, laps_left=10.0, laps_to_finish=8.0))).pit
    assert p.stops_left == 0 and p.window_open_lap is None
    p = PitCalculator().update(snap(frac=0.6, fuel=FuelInfo(avg_lap=4.0, laps_left=0.3, laps_to_finish=8.0))).pit
    assert p.last_lap == 10


def test_pit_loss_measured_from_pit_laps():
    calc = PitCalculator()
    p = calc.update(snap(), default_loss_s=50).pit
    assert p.loss_s == 50 and not p.loss_measured
    laps = [LapEntry(lap=5, time_s=200.0), LapEntry(lap=6, time_s=212.0, pit=True, valid=False),
            LapEntry(lap=7, time_s=230.0, pit=True, valid=False)]
    p = calc.update(snap(recent=laps, avg=200.0)).pit
    assert not p.loss_measured  # arrêt pas encore terminé
    p = calc.update(snap(recent=laps + [LapEntry(lap=8, time_s=201.0)], avg=200.0)).pit
    assert p.loss_measured and p.loss_s == 42.0 and p.loss_samples == 1


def test_rejoin_position_in_class():
    vs = [
        Vehicle(id=1, position=1, car_class="H", laps=10, lap_fraction=0.6, time_behind_leader_s=0.0),
        Vehicle(id=0, position=2, car_class="H", laps=10, lap_fraction=0.5, time_behind_leader_s=20.0, is_player=True),
        Vehicle(id=2, position=3, car_class="H", laps=10, lap_fraction=0.45, time_behind_leader_s=30.0),
        Vehicle(id=3, position=4, car_class="GT", laps=10, lap_fraction=0.44, time_behind_leader_s=32.0),
        Vehicle(id=4, position=5, car_class="H", laps=10, lap_fraction=0.2, time_behind_leader_s=90.0),
        Vehicle(id=5, position=6, car_class="H", laps=9, lap_fraction=0.6, time_behind_leader_s=230.0),
    ]
    assert PitCalculator().update(snap(vehicles=vs), default_loss_s=60).pit.rejoin_class_position == 3
