from lmu_assistant.model import Snapshot
from lmu_assistant.session import SessionCalculator, flag_of


def snap(**kw):
    base = dict(connected=True, session="Course 1", track="Spa", game_phase=5, lap=3)
    base.update(kw)
    return Snapshot(**base)


def test_flag_priority():
    assert flag_of(snap(game_phase=7))[0] == "red"
    assert flag_of(snap(game_phase=8))[0] == "checkered"
    assert flag_of(snap(game_phase=6, yellow_flag_state=2))[1] == "FCY / voiture de sécurité · stands fermés"
    # jaune dans notre secteur ou le suivant : alerte ; plus loin : simple mention
    assert flag_of(snap(sector=1, sector_flags=[0, 1, 0]))[:2] == ("yellow", "Jaune S2")
    assert flag_of(snap(sector=3, sector_flags=[1, 0, 0]))[0] == "yellow"  # après S3 vient S1
    assert flag_of(snap(sector=1, sector_flags=[0, 0, 1]))[:2] == ("green", "Vert · jaune S3")
    assert flag_of(snap(player_flag=6))[0] == "blue"
    assert flag_of(snap(game_phase=3))[:2] == ("", "Tour de formation")


def test_time_left_progress_and_labels():
    s = SessionCalculator().update(snap(session_time_left_s=1800.0, session_elapsed_s=1800.0, session_length_s=3600.0,
                                        track_grip=4, cloud_coverage=0, raining=0.123, wetness=0.5))
    i = s.session_info
    assert i.time_left_s == 1800.0 and i.progress == 0.5 and i.laps_left is None
    assert i.grip == "saturé" and i.sky == "dégagé" and i.rain_pct == 12 and i.wetness_pct == 50


def test_lap_race_laps_left():
    i = SessionCalculator().update(snap(max_laps=20, lap=18, lap_fraction=0.5)).session_info
    assert i.laps_left == 3 and i.progress == 0.875


def test_track_temp_trend_over_ten_minutes():
    calc = SessionCalculator()
    assert calc.update(snap(session_elapsed_s=0.0, track_temp_c=30.0)).session_info.track_temp_trend_c is None
    assert calc.update(snap(session_elapsed_s=60.0, track_temp_c=30.2)).session_info.track_temp_trend_c is None
    # +1 °C en 5 min → +2 °C ramené à 10 min
    assert calc.update(snap(session_elapsed_s=300.0, track_temp_c=31.0)).session_info.track_temp_trend_c == 2.0
    for t in range(315, 1201, 15):
        info = calc.update(snap(session_elapsed_s=float(t), track_temp_c=31.0 + (t - 300) / 300)).session_info
    assert info.track_temp_trend_c == 2.0  # fenêtre glissante de 10 min
    # nouvelle session : on repart de zéro
    assert calc.update(snap(session="Course 2", session_elapsed_s=5.0, track_temp_c=20.0)).session_info.track_temp_trend_c is None
