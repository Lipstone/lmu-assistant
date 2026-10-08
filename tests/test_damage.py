from lmu_assistant.damage import DamageCalculator
from lmu_assistant.model import Snapshot, Wheel
from lmu_assistant.sources.lmu_shared_memory import parse_rest


def snap(**kw):
    base = dict(connected=True, session="Course 1", track="Spa", car="GT3", session_elapsed_s=500.0)
    base.update(kw)
    return Snapshot(**base)


def test_intact_car():
    g = DamageCalculator().update(snap()).damage
    assert g.body_pct == 100 and not g.damaged and g.impacts == 0 and g.last_impact_ago_s is None


def test_body_wheels_rest_and_impacts():
    calc = DamageCalculator()
    calc.update(snap(last_impact_et=100.0, last_impact_magnitude=900.0))  # choc d'avant le lancement : pas compté
    wheels = [Wheel(), Wheel(flat=True), Wheel(), Wheel(detached=True)]
    g = calc.update(snap(dents=[2, 1, 0, 0, 0, 0, 1, 0], wheels=wheels, last_impact_et=480.0,
                         last_impact_magnitude=3000.0, aero_damage=0.25, suspension_damage=[0, 0.5, 0, 0],
                         repair_time_s=22.04)).damage
    assert g.body == [2, 1, 0, 0, 0, 0, 1, 0] and g.body_pct == 75.0
    assert g.wheels == ["", "crevé", "", "arrachée"]
    assert g.aero_pct == 75.0 and g.suspension_pct == [100.0, 50.0, 100.0, 100.0] and g.repair_s == 22.0
    assert g.impacts == 1 and g.last_impact_ago_s == 20.0 and g.last_impact_magnitude == 3000.0 and g.damaged
    assert calc.update(snap(last_impact_et=480.0)).damage.impacts == 1  # même choc
    assert calc.update(snap(car="LMP2")).damage.impacts == 0  # autre voiture : on repart de zéro


def test_parse_rest_answers():
    out = parse_rest({"wearables": {"body": {"aero": 0.1}, "suspension": [0.0, 0.2, 0.0, 0.0], "brakes": [1, 1, 1, 1]}},
                     {"total": 35.0, "damage": 12.5})
    assert out == {"aero_damage": 0.1, "suspension_damage": [0.0, 0.2, 0.0, 0.0], "repair_time_s": 12.5}
    assert parse_rest(None, None) == {}
    assert parse_rest({"wearables": {"body": "?", "suspension": [1]}}, {"damage": -1}) == {}
