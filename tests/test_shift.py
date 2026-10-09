from lmu_assistant.model import Snapshot
from lmu_assistant.shift import ShiftCalculator
from lmu_assistant.shift_points import GT3_SHIFT_POINTS, find_car


def snap(**kw):
    base = dict(connected=True, car="Manthey #91", car_model="Porsche 911 GT3 R LMGT3", car_class="LMGT3",
                rpm=7000.0, gear=3, max_rpm=9400.0, max_gears=6)
    base.update(kw)
    return Snapshot(**base)


def test_table_covers_the_ten_gt3():
    assert len(GT3_SHIFT_POINTS) == 10
    for point in GT3_SHIFT_POINTS:
        assert point.start_rpm < point.shift_rpm


def test_find_car_by_model_gt3_only():
    assert find_car("Porsche 911 GT3 R LMGT3").car == "Porsche 911"
    assert find_car("Ferrari 296 LMGT3", car_class="LMGT3").car == "Ferrari 296"
    assert find_car("Corvette Z06 GT3.R").car == "Corvette Z06"
    # Même marque en Hypercar : pas de régime GT3
    assert find_car("Porsche 963", "Porsche Penske #6", "Hypercar") is None
    assert find_car("Ferrari 499P", car_class="Hypercar") is None
    # Modèle vide : on essaie le nom de la voiture
    assert find_car("", "BMW M4 LMGT3 #31", "LMGT3").car == "BMW M4"
    assert find_car("", "Team inconnue #12", "LMGT3") is None


def test_shift_rpm_between_two_optimal_lights():
    porsche = find_car("Porsche 911 GT3 R LMGT3")
    assert porsche.shift_rpm == 8850  # 2e feu 8 800, 3e feu 8 900
    assert find_car("Ferrari 296 LMGT3").shift_rpm == 7300


def test_gt3_from_table():
    s = ShiftCalculator().update(snap(rpm=8850.0)).shift
    assert s.source == "table" and s.car_label == "Porsche 911"
    assert s.shift_rpm == 8850 and s.start_rpm == 8100
    assert s.level == 1.0 and s.shift_now
    s = ShiftCalculator().update(snap(rpm=8475.0)).shift
    assert s.level == 0.5 and not s.shift_now


def test_table_disabled_uses_max_rpm():
    s = ShiftCalculator().update(snap(rpm=9212.0), rpm_pct=98.0, use_table=False).shift
    assert s.source == "max" and s.shift_rpm == 9212 and s.shift_now


def test_other_car_uses_max_rpm():
    s = ShiftCalculator().update(snap(car_model="Ferrari 499P", car_class="Hypercar", rpm=8500.0, max_rpm=9000.0)).shift
    assert s.source == "max" and s.shift_rpm == 8820
    assert 0 < s.level < 1 and not s.shift_now


def test_max_rpm_unknown_uses_highest_seen():
    calc = ShiftCalculator()
    s = calc.update(snap(car_model="", car="Proto", car_class="LMP2", rpm=0.0, max_rpm=0.0)).shift
    assert s.source == "" and s.shift_rpm is None and s.level == 0
    calc.update(snap(car_model="", car="Proto", car_class="LMP2", rpm=8000.0, max_rpm=0.0))
    s = calc.update(snap(car_model="", car="Proto", car_class="LMP2", rpm=7000.0, max_rpm=0.0)).shift
    assert s.max_rpm == 8000 and s.shift_rpm == 7840 and "vu" in s.note


def test_top_gear_and_over_rev():
    s = ShiftCalculator().update(snap(gear=6, rpm=9400.0)).shift
    assert s.top_gear and not s.shift_now and s.over_rev and s.level == 1.0


def test_neutral_no_leds():
    s = ShiftCalculator().update(snap(gear=0, rpm=9000.0)).shift
    assert s.level == 0 and not s.shift_now


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_lead_lights_blue_before_target():
    clock = Clock()
    calc = ShiftCalculator(clock=clock)
    # Montée régulière de 3 000 tr/min par seconde : 8 500 → 8 800 en 0,1 s
    s = None
    for rpm in (8200.0, 8300.0, 8400.0, 8500.0, 8600.0, 8700.0, 8800.0):
        s = calc.update(snap(rpm=rpm), lead_ms=150.0).shift
        clock.t += 1 / 30
    # 8 800 + ~3 000 × 0,15 ≈ 9 250 prévu ≥ 8 850 : bleu avant le régime cible
    assert s.rpm == 8800 and s.predicted_rpm > 8850 and s.shift_now
    s0 = ShiftCalculator(clock=Clock()).update(snap(rpm=8800.0), lead_ms=150.0).shift
    assert not s0.shift_now  # sans historique, pas d'anticipation


def test_no_lead_after_gear_change_or_when_slowing():
    clock = Clock()
    calc = ShiftCalculator(clock=clock)
    calc.update(snap(rpm=8700.0, gear=3))
    clock.t += 1 / 30
    s = calc.update(snap(rpm=8800.0, gear=4)).shift  # rapport changé : pas de vitesse de montée
    assert s.predicted_rpm == 8800 and not s.shift_now
    clock.t += 1 / 30
    s = calc.update(snap(rpm=8700.0, gear=4)).shift  # en décélération
    assert s.predicted_rpm == 8700
