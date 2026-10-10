from lmu_assistant.model import Snapshot, Vehicle
from lmu_assistant.sources.mock import MockSource
from lmu_assistant.standings import compute_standings, gap


def car(id, position, car_class, laps, frac, behind=None, **kw):
    return Vehicle(id=id, driver=f"P{id}", position=position, car_class=car_class, laps=laps, lap_fraction=frac,
                   time_behind_leader_s=behind, **kw)


def test_gap_in_seconds_or_laps():
    leader = car(1, 1, "H", 10, 0.5, 0.0)
    assert gap(car(2, 2, "H", 10, 0.4, 12.34), leader) == (12.3, 0)
    assert gap(car(3, 3, "H", 9, 0.4, 250.0), leader) == (None, 1)
    # sans écart du jeu : distance × temps au tour
    assert gap(car(4, 4, "H", 10, 0.4, best_lap_s=200.0), car(5, 1, "H", 10, 0.5)) == (20.0, 0)


def test_standings_player_class_last_with_neighbours():
    vehicles = [car(i, i, "Hypercar", 10, 1 - i / 20, i * 3.0) for i in range(1, 8)]
    vehicles += [car(10 + i, 7 + i, "LMGT3", 9, 0.9 - i / 20, 200.0 + i) for i in range(1, 6)]
    vehicles[11].is_player = True  # LMGT3, P5 de sa classe (id 15)
    s = compute_standings(Snapshot(connected=True, vehicles=vehicles), top=2).standings
    assert [c.car_class for c in s] == ["Hypercar", "LMGT3"]  # classe du joueur en bas
    gt3 = s[1]
    assert gt3.cars == 5 and [e.class_position for e in gt3.entries] == [1, 2, 4, 5]
    assert [e.skipped_before for e in gt3.entries] == [False, False, True, False]
    me = gt3.entries[-1]
    assert me.is_player and me.gap_leader_s == 4.0 and me.interval_s == 1.0
    assert gt3.entries[0].gap_leader_s is None
    assert [e.class_position for e in s[0].entries] == [1, 2]


def test_standings_from_mock():
    snap = compute_standings(MockSource().read())
    assert len(snap.standings) == 3
    assert any(e.is_player for e in snap.standings[-1].entries)
