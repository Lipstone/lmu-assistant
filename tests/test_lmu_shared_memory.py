import ctypes

import pytest

from lmu_assistant.sources import get_source
from lmu_assistant.sources import lmu_shared_memory as lmu
from lmu_assistant.sources.lmu_shared_memory import (
    MAP_SIZE,
    ObjectOut,
    parse_buffer,
    read_consistent,
    session_name,
)


def test_layout_matches_known_offsets():
    # Valeurs relevées indépendamment dans la crate Rust lmu-shared-memory 0.1.0
    assert MAP_SIZE == 324_820
    assert ObjectOut.scoring.offset == 1_632
    assert ctypes.sizeof(lmu.VehicleScoring) == 584
    assert ctypes.sizeof(lmu.TelemInfo) == 1_888
    assert ObjectOut.telemetry.offset == 128_464
    assert lmu.VehicleScoring.mPlace.offset == 199
    assert lmu.TelemInfo.mUnfilteredThrottle.offset == 388


def make_data() -> ObjectOut:
    """Session avec 3 voitures : le joueur est la 2e en scoring et la 3e en télémétrie."""
    d = ObjectOut()
    info = d.scoring.scoringInfo
    info.mTrackName = b"Circuit de la Sarthe"
    info.mSession = 10
    info.mCurrentET = 1000.0
    info.mEndET = 3600.0
    info.mNumVehicles = 3

    for i, (vid, player, control) in enumerate([(5, False, 1), (7, True, 0), (9, False, 2)]):
        v = d.scoring.vehScoringInfo[i]
        v.mID = vid
        v.mIsPlayer = player
        v.mControl = control
        v.mVehicleName = f"Voiture {vid}".encode()
        v.mPlace = i + 1
        v.mTotalLaps = 11
        v.mLastLapTime = 210.5
        v.mBestLapTime = 208.25
        v.mLapStartET = 960.0

    tele = d.telemetry
    tele.activeVehicles = 3
    tele.playerHasVehicle = True
    tele.playerVehicleIdx = 2
    for i, vid in enumerate([9, 5, 7]):
        t = tele.telemInfo[i]
        t.mID = vid
        t.mEngineRPM = 1000.0 * (i + 1)
    t = tele.telemInfo[2]
    t.mVehicleName = b"Voiture 7"
    t.mLocalVel.x, t.mLocalVel.y, t.mLocalVel.z = 3.0, 0.0, -50.0  # ~50,09 m/s
    t.mEngineRPM = 7432.6
    t.mGear = 5
    t.mFuel = 42.346
    t.mFuelCapacity = 90.0
    t.mElapsedTime = 1000.5
    t.mLapStartET = 960.0
    for w in range(4):
        wheel = t.mWheels[w]
        wheel.mTemperature[0] = 273.15 + 80 + w  # gauche
        wheel.mTemperature[1] = 273.15 + 85 + w  # centre
        wheel.mTemperature[2] = 273.15 + 90 + w  # droite
        wheel.mPressure = 170.0 + w
        wheel.mWear = 0.9 - w / 100
        wheel.mBrakeTemp = 400.0 + w
    return d


def test_parse_player_snapshot():
    snap = parse_buffer(bytes(make_data()))
    assert snap.connected and snap.source == "lmu"
    assert snap.track == "Circuit de la Sarthe"
    assert snap.session == "Course 1"
    assert snap.car == "Voiture 7"
    assert snap.position == 2
    assert snap.lap == 12
    assert snap.rpm == 7433  # télémétrie du joueur retrouvée par mID, pas par index
    assert snap.gear == 5
    assert snap.speed_kmh == pytest.approx(180.3, abs=0.1)
    assert snap.fuel_l == pytest.approx(42.35, abs=0.006)
    assert snap.fuel_capacity_l == 90.0
    assert snap.last_lap_s == 210.5
    assert snap.best_lap_s == 208.25
    assert snap.current_lap_s == pytest.approx(40.5)
    assert snap.session_time_left_s == pytest.approx(2600.0)
    assert snap.max_laps is None  # mMaxLaps = 0
    assert snap.virtual_energy_pct is None  # mVirtualEnergy = 0 : voiture sans énergie virtuelle
    assert snap.in_pits is False


def test_lap_race_pits_and_lap_fraction():
    d = make_data()
    d.scoring.scoringInfo.mLapDist = 13_626.0
    d.scoring.scoringInfo.mMaxLaps = 30
    d.scoring.vehScoringInfo[1].mLapDist = 3_406.5
    d.scoring.vehScoringInfo[1].mInPits = True
    snap = parse_buffer(bytes(d))
    assert snap.max_laps == 30
    assert snap.lap_fraction == pytest.approx(0.25)
    assert snap.in_pits is True
    d.telemetry.telemInfo[2].mVirtualEnergy = 0.6243  # fraction
    assert parse_buffer(bytes(d)).virtual_energy_pct == pytest.approx(62.43)
    d.scoring.scoringInfo.mMaxLaps = 2_147_483_647  # course chronométrée
    assert parse_buffer(bytes(d)).max_laps is None


def test_wheels_kelvin_and_inner_outer():
    w = parse_buffer(bytes(make_data())).wheels
    # Roues gauches (AVG, ARG) : intérieur = droite ; roues droites : intérieur = gauche
    assert w[0].temp_c == pytest.approx((90.0, 85.0, 80.0))
    assert w[1].temp_c == pytest.approx((81.0, 86.0, 91.0))
    assert w[2].temp_c == pytest.approx((92.0, 87.0, 82.0))
    assert w[3].temp_c == pytest.approx((83.0, 88.0, 93.0))
    assert [x.pressure_kpa for x in w] == [170.0, 171.0, 172.0, 173.0]
    assert w[3].wear == pytest.approx(0.87)
    assert w[1].brake_temp_c == 401.0


def test_player_fallback_on_control_and_no_lap_times():
    d = make_data()
    d.scoring.vehScoringInfo[1].mIsPlayer = False  # reste mControl == 0
    d.scoring.vehScoringInfo[1].mLastLapTime = -1.0
    d.scoring.vehScoringInfo[1].mBestLapTime = 0.0
    snap = parse_buffer(bytes(d))
    assert snap.position == 2 and snap.rpm == 7433
    assert snap.last_lap_s is None and snap.best_lap_s is None


def test_empty_buffer_without_player():
    snap = parse_buffer(bytes(MAP_SIZE))
    assert snap.connected
    assert snap.speed_kmh == 0 and snap.position == 0
    assert snap.session_time_left_s is None


def test_short_buffer_rejected():
    with pytest.raises(ValueError):
        parse_buffer(b"\0" * 100)


def test_session_names():
    assert session_name(0) == "Journée test"
    assert session_name(3) == "Essais 3"
    assert session_name(5) == "Qualification 1"
    assert session_name(9) == "Warm-up"
    assert session_name(42) == ""


class TornBuffer:
    """Simule le jeu qui écrit pendant les premières copies complètes."""

    def __init__(self, data: ObjectOut, writes: int) -> None:
        self.buf = bytearray(bytes(data))
        self.data = ObjectOut.from_buffer(self.buf)
        self.writes = writes
        self.copies = 0

    def __len__(self) -> int:
        return len(self.buf)

    def __getitem__(self, key: slice) -> bytes:
        out = bytes(self.buf[key])
        if key.stop - (key.start or 0) >= MAP_SIZE:  # copie complète
            self.copies += 1
            if self.writes > 0:
                self.writes -= 1
                self.data.generic.events.SME_UPDATE_TELEMETRY += 1
                self.data.telemetry.telemInfo[2].mElapsedTime += 0.01
                self.data.telemetry.telemInfo[2].mFuel -= 0.01
        return out


def test_read_consistent_retries_on_torn_read():
    torn = TornBuffer(make_data(), writes=2)
    raw = read_consistent(torn)
    assert torn.copies == 3
    assert parse_buffer(raw).fuel_l == pytest.approx(42.325, abs=0.006)


def test_read_consistent_gives_up_after_tries():
    torn = TornBuffer(make_data(), writes=100)
    read_consistent(torn, tries=4)
    assert torn.copies == 4


def test_source_without_game_is_disconnected():
    src = get_source("lmu")
    for _ in range(2):
        snap = src.read()
        assert not snap.connected and snap.source == "lmu"
    src.close()
