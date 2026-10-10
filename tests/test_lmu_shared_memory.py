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
    t.mEngineMaxRPM = 8999.6
    t.mMaxGears = 6
    t.mVehicleModel = b"Porsche 911 GT3 R LMGT3"
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
        wheel.mBrakeTemp = 273.15 + 400.0 + w
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
    assert snap.max_rpm == 9000 and snap.max_gears == 6  # shift light (F14)
    assert snap.car_model == "Porsche 911 GT3 R LMGT3"
    assert snap.speed_kmh == pytest.approx(180.3, abs=0.1)
    assert snap.fuel_l == pytest.approx(42.35, abs=0.006)
    assert snap.fuel_capacity_l == 90.0
    assert snap.last_lap_s == 210.5
    assert snap.best_lap_s == 208.25
    assert snap.current_lap_s == pytest.approx(40.5)
    assert snap.lap_start_et == 960.0
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
    assert snap.lap_invalid is False
    d.telemetry.telemInfo[2].mLapInvalidated = True
    assert parse_buffer(bytes(d)).lap_invalid is True
    d.telemetry.telemInfo[2].mVirtualEnergy = 0.6243  # fraction
    assert parse_buffer(bytes(d)).virtual_energy_pct == pytest.approx(62.43)
    d.scoring.scoringInfo.mMaxLaps = 2_147_483_647  # course chronométrée
    assert parse_buffer(bytes(d)).max_laps is None


def test_lap_fraction_advanced_to_telemetry_time():
    d = make_data()
    d.scoring.scoringInfo.mLapDist = 13_626.0
    d.scoring.vehScoringInfo[1].mLapDist = 3_406.5
    d.telemetry.telemInfo[2].mElapsedTime = 1000.2  # scoring relevé 0,2 s plus tôt, à ~50 m/s
    speed_ms = parse_buffer(bytes(d)).speed_kmh / 3.6
    assert parse_buffer(bytes(d)).lap_fraction == pytest.approx((3_406.5 + speed_ms * 0.2) / 13_626.0, abs=1e-4)


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


def test_parse_vehicles_for_relative_and_standings():
    d = make_data()
    d.scoring.scoringInfo.mLapDist = 13_626.0
    for i, v in enumerate(d.scoring.vehScoringInfo[:3]):
        v.mDriverName = f"Pilote {i}".encode()
        v.mVehicleClass = b"Hypercar" if i < 2 else b"LMGT3"
        v.mLapDist = 13_626.0 * (0.1 + i / 10)
        v.mVehicleName = f"Equipe #{50 + i}".encode()
        v.mTimeBehindLeader = 1.5 * i
    snap = parse_buffer(bytes(d))
    assert [v.position for v in snap.vehicles] == [1, 2, 3]
    me = [v for v in snap.vehicles if v.is_player]
    assert len(me) == 1 and me[0].id == 7 and me[0].driver == "Pilote 1"
    assert snap.vehicles[2].car_class == "LMGT3" and snap.vehicles[2].number == "52"
    assert snap.vehicles[1].lap_fraction == 0.2 and snap.vehicles[1].laps == 11
    assert snap.vehicles[2].time_behind_leader_s == 3.0


def test_session_and_weather_fields():
    d = make_data()
    info = d.scoring.scoringInfo
    info.mGamePhase = 6
    info.mYellowFlagState = b"\x02"
    info.mSectorFlag[0], info.mSectorFlag[1], info.mSectorFlag[2] = 0, 1, 0  # index 1 = secteur 1
    info.mAmbientTemp, info.mTrackTemp = 21.5, 33.25
    info.mRaining, info.mAvgPathWetness = 0.25, 0.4
    info.mTrackGripLevel, info.mCloudCoverage = 3, 6
    info.mTimeOfDay = 54000.0
    d.scoring.vehScoringInfo[1].mSector = 0  # secteur 3
    d.scoring.vehScoringInfo[1].mFlag = 6
    snap = parse_buffer(bytes(d))
    assert snap.game_phase == 6 and snap.yellow_flag_state == 2
    assert snap.sector_flags == [1, 0, 0] and snap.sector == 3 and snap.player_flag == 6
    assert snap.air_temp_c == 21.5 and snap.track_temp_c == 33.25
    assert snap.raining == 0.25 and snap.wetness == 0.4
    assert snap.track_grip == 3 and snap.cloud_coverage == 6 and snap.time_of_day_s == 54000.0
    assert snap.session_elapsed_s == 1000.0 and snap.session_length_s == 3600.0


def test_damage_fields():
    d = make_data()
    t = d.telemetry.telemInfo[2]
    for i, v in enumerate([1, 2, 0, 0, 0, 0, 0, 1]):  # ordre rF2 : avant, avant gauche, …, avant droit
        t.mDentSeverity[i] = v
    t.mWheels[1].mFlat = True
    t.mLastImpactET, t.mLastImpactMagnitude = 950.0, 1234.56
    t.mEngineWaterTemp, t.mEngineOilTemp = 91.0, 106.5
    t.mOverheating = True
    snap = parse_buffer(bytes(d))
    assert snap.dents == [2, 1, 1, 0, 0, 0, 0, 0]  # AVG, AV, AVD, …
    assert snap.wheels[1].flat and not snap.wheels[0].flat
    assert snap.last_impact_et == 950.0 and snap.last_impact_magnitude == 1234.6
    assert snap.water_temp_c == 91.0 and snap.oil_temp_c == 106.5 and snap.engine_overheating


def test_inputs_fields():
    d = make_data()
    t = d.telemetry.telemInfo[2]
    t.mUnfilteredThrottle, t.mUnfilteredBrake, t.mUnfilteredClutch = 0.756, 1.2, 0.0
    t.mUnfilteredSteering, t.mPhysicalSteeringWheelRange = -0.25, 540.0
    t.mABSActive, t.mTCActive = True, False
    snap = parse_buffer(bytes(d))
    assert (snap.throttle, snap.brake, snap.clutch, snap.steering) == (0.756, 1.0, 0.0, -0.25)
    assert snap.steering_range_deg == 540.0 and snap.abs_active and not snap.tc_active
    assert parse_buffer(bytes(make_data())).steering_range_deg is None  # 0 : inconnu


def test_vehicles_damage_and_fuel_from_telemetry():
    d = make_data()
    t = d.telemetry.telemInfo[0]  # voiture mID 9 (3e en scoring)
    t.mDentSeverity[4] = 2  # arrière
    t.mWheels[3].mDetached = True
    t.mFuel, t.mFuelCapacity, t.mVirtualEnergy = 31.25, 100.0, 0.425
    d.telemetry.telemInfo[1].mFuel = 0.0  # voiture mID 5 : carburant non transmis
    snap = parse_buffer(bytes(d))
    by_id = {v.id: v for v in snap.vehicles}
    assert by_id[9].dents == [0, 0, 0, 0, 0, 0, 2, 0] and by_id[9].wheels_off == 1
    assert by_id[9].fuel_l == 31.25 and by_id[9].energy_pct == 42.5
    assert by_id[5].fuel_l is None and by_id[5].energy_pct is None and by_id[5].dents == [0] * 8
    assert by_id[7].fuel_l == 42.346


def test_vehicles_penalties_and_tyre_wear():
    d = make_data()
    d.scoring.vehScoringInfo[0].mNumPenalties = 2
    for i, w in enumerate(d.telemetry.telemInfo[0].mWheels):  # voiture mID 9
        w.mWear = 0.9 - i / 100
    snap = parse_buffer(bytes(d))
    by_id = {v.id: v for v in snap.vehicles}
    assert by_id[d.scoring.vehScoringInfo[0].mID].penalties == 2
    assert by_id[9].tyre_wear == [0.9, 0.89, 0.88, 0.87]


def test_vehicles_tyre_compound_of_each_wheel():
    d = make_data()
    t = d.telemetry.telemInfo[0]  # voiture mID 9
    t.mFrontTireCompoundName, t.mFrontTireCompoundIndex = b"Soft", 0
    t.mRearTireCompoundName, t.mRearTireCompoundIndex = b"Medium", 1
    for w, idx in zip(t.mWheels, (0, 1, 0, 1)):  # tendre à gauche, medium à droite
        w.mCompoundIndex = idx
    u = d.telemetry.telemInfo[2]  # voiture mID 7 : indice de roue inconnu, gomme de l'essieu
    u.mFrontTireCompoundName, u.mRearTireCompoundName, u.mRearTireCompoundIndex = b"Hard", b"Wet", 2
    for w in u.mWheels:
        w.mCompoundIndex = 5
    by_id = {v.id: v for v in parse_buffer(bytes(d)).vehicles}
    assert by_id[9].compounds == ["Soft", "Medium", "Soft", "Medium"]
    assert by_id[7].compounds == ["Hard", "Hard", "Wet", "Wet"]
    assert by_id[5].compounds is None  # noms vides : gomme inconnue


def test_vehicle_without_telemetry_has_no_damage_or_fuel():
    d = make_data()
    d.telemetry.activeVehicles = 2  # la télémétrie de mID 7 (index 2) n'est plus active
    snap = parse_buffer(bytes(d))
    by_id = {v.id: v for v in snap.vehicles}
    assert by_id[7].dents is None and by_id[7].fuel_l is None


def test_wheels_not_filled_in_garage():
    """Au garage, LMU laisse les pneus à 0 K / 0 kPa : rien plutôt que -273 °C ; freins en Kelvin."""
    d = make_data()
    t = d.telemetry.telemInfo[2]
    for w in range(4):
        wheel = t.mWheels[w]
        for k in range(3):
            wheel.mTemperature[k] = 0.0
        wheel.mPressure = 0.0
        wheel.mBrakeTemp = 296.0
    w = parse_buffer(bytes(d)).wheels
    assert all(x.temp_c is None and x.pressure_kpa is None for x in w)
    assert w[0].brake_temp_c == pytest.approx(22.9, abs=0.05)


def test_tyre_temp_falls_back_to_inner_layer():
    d = make_data()
    wheel = d.telemetry.telemInfo[2].mWheels[1]
    for k in range(3):
        wheel.mTemperature[k] = 0.0
        wheel.mTireInnerLayerTemperature[k] = 273.15 + 70 + k
    assert parse_buffer(bytes(d)).wheels[1].temp_c == pytest.approx((70.0, 71.0, 72.0))


def test_player_wheels_carry_their_compound():
    d = make_data()
    t = d.telemetry.telemInfo[2]  # joueur (mID 7)
    t.mFrontTireCompoundName, t.mFrontTireCompoundIndex = b"Soft", 0
    t.mRearTireCompoundName, t.mRearTireCompoundIndex = b"Wet", 1
    for w, idx in zip(t.mWheels, (0, 0, 1, 1)):
        w.mCompoundIndex = idx
    snap = parse_buffer(bytes(d))
    assert [w.compound for w in snap.wheels] == ["Soft", "Soft", "Wet", "Wet"]
