from lmu_assistant.analysis import linear_fit, split_stints, stints


def lap(n, t=200.0, **kw):
    d = dict(lap=n, time_s=t, valid=True, pit=False, stop=False, refuel=False, tyres_changed=False,
             fuel_used=3.0, energy_used=None, driver="A", wear=[1 - 0.01 * n] * 4, track_temp=30.0)
    d.update(kw)
    return d


def test_linear_fit():
    assert linear_fit([0, 1, 2], [1, 3, 5]) == (2.0, 1.0)
    assert linear_fit([1], [1]) is None and linear_fit([1, 1], [1, 2]) is None


def test_split_on_stop_and_driver_change():
    laps = [lap(1), lap(2), lap(3, stop=True, pit=True, valid=False), lap(4), lap(5, driver="B"), lap(6, driver="B")]
    assert [[x["lap"] for x in g] for g in split_stints(laps)] == [[1, 2], [3, 4], [5, 6]]


def test_stint_summary_degradation_and_tyre_age():
    # relais 1 : 6 tours, +0,1 s par tour ; relais 2 sans changer les pneus ; relais 3 pneus neufs
    laps = [lap(n, 200 + 0.1 * (n - 1), wear=[1 - 0.02 * n, 1 - 0.01 * n, 1, 1]) for n in range(1, 7)]
    laps += [lap(7, 260, stop=True, pit=True, valid=False, refuel=True, fuel_used=None), lap(8), lap(9)]
    laps += [lap(10, 255, stop=True, pit=True, valid=False, tyres_changed=True, wear=[1, 1, 1, 1]), lap(11, wear=[0.98] * 4)]
    s1, s2, s3 = stints(laps)
    assert s1["laps"] == 6 and s1["avg_s"] == 200.25 and s1["best_s"] == 200.0 and s1["deg_s_per_lap"] == 0.1
    assert s1["wear_per_lap"][0] == 0.02 and s1["tyre_age_start"] == 0
    assert s1["laps_to_wear_limit"] == 29.0  # AVG à 88 %, −2 % par tour, limite 30 %
    assert s1["fuel_per_lap"] == 3.0 and s1["fuel_used"] == 18.0
    assert s2["tyres_new"] is False and s2["tyre_age_start"] == 6 and s2["clean_laps"] == 2
    assert s3["tyres_new"] is True and s3["tyre_age_start"] == 0


def test_first_stint_joined_late_has_unknown_tyre_age():
    s = stints([lap(5), lap(6)])[0]
    assert s["tyre_age_start"] is None


def test_theoretical_best_and_compare():
    from lmu_assistant.analysis import compare_laps, theoretical_best

    laps = [lap(1, 100.0, s1=30.0, s2=40.0, s3=30.0, id=1), lap(2, 99.5, s1=30.5, s2=39.0, s3=30.0, id=2),
            lap(3, 98.0, s1=29.0, s2=38.0, s3=31.0, valid=False, id=3)]
    th = theoretical_best(laps)
    assert [s["time_s"] for s in th["sectors"]] == [30.0, 39.0, 30.0] and [s["lap"] for s in th["sectors"]] == [1, 2, 1]
    assert th["time_s"] == 99.0 and th["best_lap"] == 2 and th["gain_s"] == 0.5

    ta = [i * 1.0 for i in range(100)]
    tb = [i * 1.0 + (0.5 if i >= 50 else 0) for i in range(100)]
    tb[10] = None  # trou dans la trace : interpolé
    a = dict(laps[0], trace={"t": ta, "v": [200.0] * 100})
    b = dict(laps[1], trace={"t": tb, "v": [190.0] * 100})
    c = compare_laps(a, b)
    assert [s["diff"] for s in c["sectors"]] == [0.5, -1.0, 0.0, -0.5]
    assert dict(map(tuple, c["delta"]))[10.0] == 0.0 and dict(map(tuple, c["delta"]))[60.0] == 0.5
    assert c["delta"][-1] == [100.0, -0.5] and c["speed_b"][0] == [0.0, 190.0]
