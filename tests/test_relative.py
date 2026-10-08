from lmu_assistant.model import Snapshot, Vehicle
from lmu_assistant.relative import class_positions, compute_relative
from lmu_assistant.sources.mock import MockSource


def car(id, laps, frac, position, car_class="Hypercar", **kw):
    return Vehicle(id=id, driver=f"P{id}", laps=laps, lap_fraction=frac, position=position, car_class=car_class, **kw)


def test_relative_orders_cars_around_player_on_track():
    me = car(0, 10, 0.95, 3, best_lap_s=200.0, is_player=True)
    vehicles = [
        me,
        car(1, 11, 0.02, 1),  # 0,07 tour devant, même tour (passée la ligne avant moi)
        car(2, 11, 0.90, 2),  # 0,05 tour derrière mais un tour d'avance : va me doubler
        car(3, 9, 0.97, 5, "LMGT3"),  # 0,02 tour devant, un tour de retard
        car(4, 10, 0.50, 4),  # 0,45 tour derrière
        car(5, 10, 0.10, 6, "LMGT3"),  # 0,15 tour devant (-0,85 ramené dans ]-½, ½])
    ]
    rel = compute_relative(Snapshot(connected=True, vehicles=vehicles), each_side=2).relative
    assert [r.id for r in rel] == [1, 3, 0, 2, 4]
    by_id = {r.id: r for r in rel}
    assert by_id[3].gap_s == 4.0 and by_id[3].laps_diff == -1 and not by_id[3].same_class
    assert by_id[1].gap_s == 14.0 and by_id[1].laps_diff == 0
    assert by_id[2].gap_s == -10.0 and by_id[2].laps_diff == 1
    assert by_id[0].is_player and by_id[0].gap_s == 0
    assert by_id[3].class_position == 1 and by_id[4].class_position == 4


def test_relative_empty_without_player():
    snap = compute_relative(Snapshot(connected=True, vehicles=[car(1, 1, 0.5, 1)]))
    assert snap.relative == []


def test_class_positions():
    vs = [car(1, 0, 0, 2, "LMP2"), car(2, 0, 0, 1, "Hypercar"), car(3, 0, 0, 3, "LMP2")]
    assert class_positions(vs) == {2: 1, 1: 1, 3: 2}


def test_mock_field_has_player_and_relative():
    snap = compute_relative(MockSource().read())
    player = [v for v in snap.vehicles if v.is_player]
    assert len(player) == 1 and player[0].position == snap.position
    assert len(snap.vehicles) >= 10 and len(snap.relative) == 7
