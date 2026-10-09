"""Lecture des données de Le Mans Ultimate via sa mémoire partagée native (Windows).

LMU expose une zone de mémoire partagée nommée « LMU_Data » (interface native,
en-tête SharedMemoryInterface.hpp fourni dans le dossier Support du jeu).
Structures et sources : voir docs/donnees-lmu.md.

Organisation :
- structures ctypes (indépendantes de l'OS) ;
- parse_buffer() : octets → Snapshot, testable sur n'importe quel OS ;
- read_consistent() : copie cohérente du tampon (relecture si le jeu écrivait) ;
- LmuSharedMemorySource : ouverture Windows (mmap + tagname), reconnexion.
"""

from __future__ import annotations

import ctypes
import math
import re
import sys
import time
from typing import Any

from ..model import ForecastNode, Snapshot, Vehicle, Wheel
from .base import DataSource

MAP_NAME = "LMU_Data"
MAX_VEHICLES = 104
MAX_PATH_LENGTH = 260
KELVIN = 273.15
MAX_RACE_LAPS = 10_000  # au-delà, mMaxLaps signifie « pas de limite de tours »


class _Struct(ctypes.Structure):
    # En-têtes du jeu : #pragma pack(push, 4) ; _layout_ "ms" = disposition MSVC partout
    _pack_ = 4
    _layout_ = "ms"


# --- InternalsPlugin.hpp -------------------------------------------------


class Vect3(_Struct):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("z", ctypes.c_double)]


class TelemWheel(_Struct):
    """TelemWheelV01."""

    _fields_ = [
        ("mSuspensionDeflection", ctypes.c_double),
        ("mRideHeight", ctypes.c_double),
        ("mSuspForce", ctypes.c_double),
        ("mBrakeTemp", ctypes.c_double),  # Kelvin dans LMU (l'en-tête rF2 dit °C : 296 au stand = 23 °C)
        ("mBrakePressure", ctypes.c_double),
        ("mRotation", ctypes.c_double),
        ("mLateralPatchVel", ctypes.c_double),
        ("mLongitudinalPatchVel", ctypes.c_double),
        ("mLateralGroundVel", ctypes.c_double),
        ("mLongitudinalGroundVel", ctypes.c_double),
        ("mCamber", ctypes.c_double),
        ("mLateralForce", ctypes.c_double),
        ("mLongitudinalForce", ctypes.c_double),
        ("mTireLoad", ctypes.c_double),
        ("mGripFract", ctypes.c_double),
        ("mPressure", ctypes.c_double),  # kPa
        ("mTemperature", ctypes.c_double * 3),  # Kelvin, gauche/centre/droite (pas int/ext !)
        ("mWear", ctypes.c_double),  # 0-1, supposé 1.0 = neuf (à vérifier en jeu)
        ("mTerrainName", ctypes.c_char * 16),
        ("mSurfaceType", ctypes.c_ubyte),
        ("mFlat", ctypes.c_bool),
        ("mDetached", ctypes.c_bool),
        ("mStaticUndeflectedRadius", ctypes.c_ubyte),
        ("mVerticalTireDeflection", ctypes.c_double),
        ("mWheelYLocation", ctypes.c_double),
        ("mToe", ctypes.c_double),
        ("mTireCarcassTemperature", ctypes.c_double),
        ("mTireInnerLayerTemperature", ctypes.c_double * 3),
        ("mOptimalTemp", ctypes.c_float),
        ("mCompoundIndex", ctypes.c_ubyte),
        ("mCompoundType", ctypes.c_ubyte),
        ("mExpansion", ctypes.c_ubyte * 18),
    ]


class TelemInfo(_Struct):
    """TelemInfoV01 : télémétrie d'un véhicule."""

    _fields_ = [
        ("mID", ctypes.c_int),
        ("mDeltaTime", ctypes.c_double),
        ("mElapsedTime", ctypes.c_double),
        ("mLapNumber", ctypes.c_int),
        ("mLapStartET", ctypes.c_double),
        ("mVehicleName", ctypes.c_char * 64),
        ("mTrackName", ctypes.c_char * 64),
        ("mPos", Vect3),
        ("mLocalVel", Vect3),  # m/s
        ("mLocalAccel", Vect3),
        ("mOri", Vect3 * 3),
        ("mLocalRot", Vect3),
        ("mLocalRotAccel", Vect3),
        ("mGear", ctypes.c_int),  # -1 = R, 0 = N
        ("mEngineRPM", ctypes.c_double),
        ("mEngineWaterTemp", ctypes.c_double),
        ("mEngineOilTemp", ctypes.c_double),
        ("mClutchRPM", ctypes.c_double),
        ("mUnfilteredThrottle", ctypes.c_double),
        ("mUnfilteredBrake", ctypes.c_double),
        ("mUnfilteredSteering", ctypes.c_double),
        ("mUnfilteredClutch", ctypes.c_double),
        ("mFilteredThrottle", ctypes.c_double),
        ("mFilteredBrake", ctypes.c_double),
        ("mFilteredSteering", ctypes.c_double),
        ("mFilteredClutch", ctypes.c_double),
        ("mSteeringShaftTorque", ctypes.c_double),
        ("mFront3rdDeflection", ctypes.c_double),
        ("mRear3rdDeflection", ctypes.c_double),
        ("mFrontWingHeight", ctypes.c_double),
        ("mFrontRideHeight", ctypes.c_double),
        ("mRearRideHeight", ctypes.c_double),
        ("mDrag", ctypes.c_double),
        ("mFrontDownforce", ctypes.c_double),
        ("mRearDownforce", ctypes.c_double),
        ("mFuel", ctypes.c_double),  # litres
        ("mEngineMaxRPM", ctypes.c_double),
        ("mScheduledStops", ctypes.c_ubyte),
        ("mOverheating", ctypes.c_bool),
        ("mDetached", ctypes.c_bool),
        ("mHeadlights", ctypes.c_bool),
        ("mDentSeverity", ctypes.c_ubyte * 8),
        ("mLastImpactET", ctypes.c_double),
        ("mLastImpactMagnitude", ctypes.c_double),
        ("mLastImpactPos", Vect3),
        ("mEngineTorque", ctypes.c_double),
        ("mCurrentSector", ctypes.c_int),
        ("mSpeedLimiter", ctypes.c_ubyte),
        ("mMaxGears", ctypes.c_ubyte),
        ("mFrontTireCompoundIndex", ctypes.c_ubyte),
        ("mRearTireCompoundIndex", ctypes.c_ubyte),
        ("mFuelCapacity", ctypes.c_double),  # litres
        ("mFrontFlapActivated", ctypes.c_ubyte),
        ("mRearFlapActivated", ctypes.c_ubyte),
        ("mRearFlapLegalStatus", ctypes.c_ubyte),
        ("mIgnitionStarter", ctypes.c_ubyte),
        ("mFrontTireCompoundName", ctypes.c_char * 18),
        ("mRearTireCompoundName", ctypes.c_char * 18),
        ("mSpeedLimiterAvailable", ctypes.c_ubyte),
        ("mAntiStallActivated", ctypes.c_ubyte),
        ("mUnused", ctypes.c_ubyte * 2),
        ("mVisualSteeringWheelRange", ctypes.c_float),
        ("mRearBrakeBias", ctypes.c_double),
        ("mTurboBoostPressure", ctypes.c_double),
        ("mPhysicsToGraphicsOffset", ctypes.c_float * 3),
        ("mPhysicalSteeringWheelRange", ctypes.c_float),
        ("mDeltaBest", ctypes.c_double),
        ("mBatteryChargeFraction", ctypes.c_double),
        ("mElectricBoostMotorTorque", ctypes.c_double),
        ("mElectricBoostMotorRPM", ctypes.c_double),
        ("mElectricBoostMotorTemperature", ctypes.c_double),
        ("mElectricBoostWaterTemperature", ctypes.c_double),
        ("mElectricBoostMotorState", ctypes.c_ubyte),
        ("mLapInvalidated", ctypes.c_bool),
        ("mABSActive", ctypes.c_bool),
        ("mTCActive", ctypes.c_bool),
        ("mSpeedLimiterActive", ctypes.c_bool),
        ("mWiperState", ctypes.c_uint8),
        ("mTC", ctypes.c_uint8),
        ("mTCMax", ctypes.c_uint8),
        ("mTCSlip", ctypes.c_uint8),
        ("mTCSlipMax", ctypes.c_uint8),
        ("mTCCut", ctypes.c_uint8),
        ("mTCCutMax", ctypes.c_uint8),
        ("mABS", ctypes.c_uint8),
        ("mABSMax", ctypes.c_uint8),
        ("mMotorMap", ctypes.c_uint8),
        ("mMotorMapMax", ctypes.c_uint8),
        ("mMigration", ctypes.c_uint8),
        ("mMigrationMax", ctypes.c_uint8),
        ("mFrontAntiSway", ctypes.c_uint8),
        ("mFrontAntiSwayMax", ctypes.c_uint8),
        ("mRearAntiSway", ctypes.c_uint8),
        ("mRearAntiSwayMax", ctypes.c_uint8),
        ("mLiftAndCoastProgress", ctypes.c_uint8),
        ("mTrackLimitsSteps", ctypes.c_uint8),
        ("mRegen", ctypes.c_float),
        ("mStateOfCharge", ctypes.c_float),
        ("mVirtualEnergy", ctypes.c_float),
        ("mTimeGapCarAhead", ctypes.c_float),
        ("mTimeGapCarBehind", ctypes.c_float),
        ("mTimeGapPlaceAhead", ctypes.c_float),
        ("mTimeGapPlaceBehind", ctypes.c_float),
        ("mVehicleModel", ctypes.c_char * 30),
        ("mVehicleClass", ctypes.c_uint8),
        ("mVehicleChampionship", ctypes.c_uint8),
        ("mExpansion", ctypes.c_ubyte * 20),
        ("mWheels", TelemWheel * 4),  # 0 = AVG, 1 = AVD, 2 = ARG, 3 = ARD
    ]


class VehicleScoring(_Struct):
    """VehicleScoringInfoV01 : classement d'un véhicule."""

    _fields_ = [
        ("mID", ctypes.c_int),
        ("mDriverName", ctypes.c_char * 32),
        ("mVehicleName", ctypes.c_char * 64),
        ("mTotalLaps", ctypes.c_short),  # tours terminés
        ("mSector", ctypes.c_byte),
        ("mFinishStatus", ctypes.c_byte),
        ("mLapDist", ctypes.c_double),
        ("mPathLateral", ctypes.c_double),
        ("mTrackEdge", ctypes.c_double),
        ("mBestSector1", ctypes.c_double),
        ("mBestSector2", ctypes.c_double),
        ("mBestLapTime", ctypes.c_double),  # s, <= 0 si aucun
        ("mLastSector1", ctypes.c_double),
        ("mLastSector2", ctypes.c_double),
        ("mLastLapTime", ctypes.c_double),  # s, <= 0 si aucun
        ("mCurSector1", ctypes.c_double),
        ("mCurSector2", ctypes.c_double),
        ("mNumPitstops", ctypes.c_short),
        ("mNumPenalties", ctypes.c_short),
        ("mIsPlayer", ctypes.c_bool),
        ("mControl", ctypes.c_byte),  # 0 = joueur local, 1 = IA, 2 = distant, 3 = replay
        ("mInPits", ctypes.c_bool),
        ("mPlace", ctypes.c_ubyte),  # position, à partir de 1
        ("mVehicleClass", ctypes.c_char * 32),
        ("mTimeBehindNext", ctypes.c_double),
        ("mLapsBehindNext", ctypes.c_int),
        ("mTimeBehindLeader", ctypes.c_double),
        ("mLapsBehindLeader", ctypes.c_int),
        ("mLapStartET", ctypes.c_double),
        ("mPos", Vect3),
        ("mLocalVel", Vect3),
        ("mLocalAccel", Vect3),
        ("mOri", Vect3 * 3),
        ("mLocalRot", Vect3),
        ("mLocalRotAccel", Vect3),
        ("mHeadlights", ctypes.c_ubyte),
        ("mPitState", ctypes.c_ubyte),
        ("mServerScored", ctypes.c_ubyte),
        ("mIndividualPhase", ctypes.c_ubyte),
        ("mQualification", ctypes.c_int),
        ("mTimeIntoLap", ctypes.c_double),
        ("mEstimatedLapTime", ctypes.c_double),
        ("mPitGroup", ctypes.c_char * 24),
        ("mFlag", ctypes.c_ubyte),
        ("mUnderYellow", ctypes.c_bool),
        ("mCountLapFlag", ctypes.c_ubyte),
        ("mInGarageStall", ctypes.c_bool),
        ("mUpgradePack", ctypes.c_ubyte * 16),
        ("mPitLapDist", ctypes.c_float),
        ("mBestLapSector1", ctypes.c_float),
        ("mBestLapSector2", ctypes.c_float),
        ("mSteamID", ctypes.c_ulonglong),
        ("mVehFilename", ctypes.c_char * 32),
        ("mAttackMode", ctypes.c_short),
        ("mFuelFraction", ctypes.c_ubyte),
        ("mDRSState", ctypes.c_bool),
        ("mExpansion", ctypes.c_ubyte * 4),
    ]


class ScoringInfo(_Struct):
    """ScoringInfoV01 : session et piste."""

    _fields_ = [
        ("mTrackName", ctypes.c_char * 64),
        ("mSession", ctypes.c_int),  # 0 test, 1-4 essais, 5-8 qualif, 9 warm-up, 10-13 course
        ("mCurrentET", ctypes.c_double),  # s
        ("mEndET", ctypes.c_double),  # s
        ("mMaxLaps", ctypes.c_int),
        ("mLapDist", ctypes.c_double),
        ("mResultsStreamPointer", ctypes.c_ubyte * 8),
        ("mNumVehicles", ctypes.c_int),
        ("mGamePhase", ctypes.c_ubyte),
        ("mYellowFlagState", ctypes.c_char),
        ("mSectorFlag", ctypes.c_ubyte * 3),
        ("mStartLight", ctypes.c_ubyte),
        ("mNumRedLights", ctypes.c_ubyte),
        ("mInRealtime", ctypes.c_bool),
        ("mPlayerName", ctypes.c_char * 32),
        ("mPlrFileName", ctypes.c_char * 64),
        ("mDarkCloud", ctypes.c_double),
        ("mRaining", ctypes.c_double),
        ("mAmbientTemp", ctypes.c_double),
        ("mTrackTemp", ctypes.c_double),
        ("mWind", Vect3),
        ("mMinPathWetness", ctypes.c_double),
        ("mMaxPathWetness", ctypes.c_double),
        ("mGameMode", ctypes.c_ubyte),
        ("mIsPasswordProtected", ctypes.c_bool),
        ("mServerPort", ctypes.c_ushort),
        ("mServerPublicIP", ctypes.c_uint),
        ("mMaxPlayers", ctypes.c_int),
        ("mServerName", ctypes.c_char * 32),
        ("mStartET", ctypes.c_float),
        ("mAvgPathWetness", ctypes.c_double),
        ("mSessionTimeRemaining", ctypes.c_float),
        ("mTimeOfDay", ctypes.c_float),
        ("mIsFixedSetup", ctypes.c_bool),
        ("mTrackGripLevel", ctypes.c_uint8),
        ("mCloudCoverage", ctypes.c_uint8),
        ("mTrackLimitsStepsPerPenalty", ctypes.c_uint8),
        ("mTrackLimitsStepsPerPoint", ctypes.c_uint8),
        ("mExpansion", ctypes.c_ubyte * 187),
        ("mVehiclePointer", ctypes.c_ubyte * 8),
    ]


class ApplicationState(_Struct):
    """ApplicationStateV01."""

    _fields_ = [
        ("mAppWindow", ctypes.c_ulonglong),  # HWND de la fenêtre du jeu
        ("mWidth", ctypes.c_uint),
        ("mHeight", ctypes.c_uint),
        ("mRefreshRate", ctypes.c_uint),
        ("mWindowed", ctypes.c_uint),
        ("mOptionsLocation", ctypes.c_ubyte),
        ("mOptionsPage", ctypes.c_char * 31),
        ("mExpansion", ctypes.c_ubyte * 204),
    ]


# --- SharedMemoryInterface.hpp -------------------------------------------


class Events(_Struct):
    """Compteurs par événement (enum SharedMemoryEvent, SME_MAX omis)."""

    _fields_ = [
        (name, ctypes.c_uint)
        for name in (
            "SME_ENTER", "SME_EXIT", "SME_STARTUP", "SME_SHUTDOWN", "SME_LOAD", "SME_UNLOAD",
            "SME_START_SESSION", "SME_END_SESSION", "SME_ENTER_REALTIME", "SME_EXIT_REALTIME",
            "SME_UPDATE_SCORING", "SME_UPDATE_TELEMETRY", "SME_INIT_APPLICATION",
            "SME_UNINIT_APPLICATION", "SME_SET_ENVIRONMENT", "SME_FFB",
        )
    ]


class Generic(_Struct):
    _fields_ = [
        ("events", Events),
        ("gameVersion", ctypes.c_int),
        ("FFBTorque", ctypes.c_float),
        ("appInfo", ApplicationState),
    ]


class PathData(_Struct):
    _fields_ = [
        ("userData", ctypes.c_char * MAX_PATH_LENGTH),
        ("customVariables", ctypes.c_char * MAX_PATH_LENGTH),
        ("stewardResults", ctypes.c_char * MAX_PATH_LENGTH),
        ("playerProfile", ctypes.c_char * MAX_PATH_LENGTH),
        ("pluginsFolder", ctypes.c_char * MAX_PATH_LENGTH),
    ]


class ScoringData(_Struct):
    _fields_ = [
        ("scoringInfo", ScoringInfo),
        ("scoringStreamSize", ctypes.c_ubyte * 12),
        ("vehScoringInfo", VehicleScoring * MAX_VEHICLES),
        ("scoringStream", ctypes.c_char * 65536),
    ]


class TelemetryData(_Struct):
    _fields_ = [
        ("activeVehicles", ctypes.c_uint8),
        ("playerVehicleIdx", ctypes.c_uint8),
        ("playerHasVehicle", ctypes.c_bool),
        ("telemInfo", TelemInfo * MAX_VEHICLES),
    ]


class ObjectOut(_Struct):
    """SharedMemoryObjectOut : contenu complet de « LMU_Data »."""

    _fields_ = [
        ("generic", Generic),
        ("paths", PathData),
        ("scoring", ScoringData),
        ("telemetry", TelemetryData),
    ]


MAP_SIZE = ctypes.sizeof(ObjectOut)  # 324 820 octets attendus

# Positions utiles pour vérifier la cohérence sans tout recopier
_OFF_EVENTS = ObjectOut.generic.offset
_OFF_APP_WINDOW = ObjectOut.generic.offset + Generic.appInfo.offset
_OFF_SCORING_ET = ObjectOut.scoring.offset + ScoringInfo.mCurrentET.offset
_OFF_TELEMETRY = ObjectOut.telemetry.offset
_OFF_TELEM_INFO = _OFF_TELEMETRY + TelemetryData.telemInfo.offset
_TELEM_SIZE = ctypes.sizeof(TelemInfo)


# --- Conversion vers Snapshot ---------------------------------------------


def _text(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()


def _lap_time(value: float) -> float | None:
    return value if value > 0 and math.isfinite(value) else None


def session_name(session: int) -> str:
    if session == 0:
        return "Journée test"
    if 1 <= session <= 4:
        return f"Essais {session}"
    if 5 <= session <= 8:
        return f"Qualification {session - 4}"
    if session == 9:
        return "Warm-up"
    if 10 <= session <= 13:
        return f"Course {session - 9}"
    return ""


def _kelvin(values) -> list[float] | None:
    """Températures en Kelvin → °C ; None si le jeu ne les remplit pas (0 K, voiture au garage)."""
    values = list(values)
    if not all(math.isfinite(v) and v > 0 for v in values):
        return None
    return [round(v - KELVIN, 1) for v in values]


def _wheel(w: TelemWheel, left_side: bool) -> Wheel:
    # mTemperature = gauche/centre/droite vu du pilote : côté gauche, l'extérieur est à gauche.
    # Surface à 0 K → couche interne, puis carcasse ; rien de rempli → None (affiché « – »).
    temps = _kelvin(w.mTemperature) or _kelvin(w.mTireInnerLayerTemperature) or _kelvin([w.mTireCarcassTemperature] * 3)
    if temps is not None:
        left, middle, right = temps
        temps = (right, middle, left) if left_side else (left, middle, right)
    brake = _kelvin([w.mBrakeTemp])
    return Wheel(
        temp_c=temps,
        pressure_kpa=round(w.mPressure, 1) if math.isfinite(w.mPressure) and w.mPressure > 0 else None,
        wear=round(w.mWear, 4),
        brake_temp_c=brake[0] if brake else None,
        flat=bool(w.mFlat),
        detached=bool(w.mDetached),
    )


# mDentSeverity (ordre rF2 : 0 avant, 1 avant gauche, 2 gauche, 3 arrière gauche, 4 arrière, 5 arrière droit,
# 6 droite, 7 avant droit) → AVG, AV, AVD, G, D, ARG, AR, ARD (ligne par ligne, vue de dessus)
DENT_ORDER = (1, 0, 7, 2, 6, 3, 4, 5)


def _damage(snap: Snapshot, telem: TelemInfo) -> None:
    """Dégâts (F11) lus dans la télémétrie."""
    dents = list(telem.mDentSeverity)
    snap.dents = [dents[i] for i in DENT_ORDER]
    snap.parts_detached = bool(telem.mDetached)
    snap.last_impact_et = _finite(telem.mLastImpactET, 0)
    snap.last_impact_magnitude = _finite(telem.mLastImpactMagnitude, 0)
    if snap.last_impact_magnitude is not None:
        snap.last_impact_magnitude = round(snap.last_impact_magnitude, 1)
    snap.engine_overheating = bool(telem.mOverheating)
    snap.water_temp_c = _finite(telem.mEngineWaterTemp, -50, 300)
    snap.oil_temp_c = _finite(telem.mEngineOilTemp, -50, 300)


_NUMBER = re.compile(r"#\s*(\d+)")


def car_number(name: str) -> str:
    """Numéro de course tiré du nom de la voiture (« Toyota GR010 #7 » → « 7 »), vide sinon."""
    m = _NUMBER.search(name)
    return m.group(1) if m else ""


def vehicles(data: ObjectOut, player_id: int | None) -> list[Vehicle]:
    """Classement de toutes les voitures (F07, F08), trié par position."""
    info = data.scoring.scoringInfo
    n = max(0, min(info.mNumVehicles, MAX_VEHICLES))
    tele = data.telemetry
    telem = {t.mID: t for t in tele.telemInfo[:min(max(tele.activeVehicles, 0), MAX_VEHICLES)]}
    result = []
    for v in data.scoring.vehScoringInfo[:n]:
        name = _text(v.mVehicleName)
        frac = None
        if info.mLapDist > 0:
            frac = round(min(max(v.mLapDist / info.mLapDist, 0.0), 0.9999), 4)
        result.append(Vehicle(
            id=v.mID, driver=_text(v.mDriverName), car=name, number=car_number(name),
            car_class=_text(v.mVehicleClass), position=v.mPlace, laps=max(0, v.mTotalLaps), lap_fraction=frac,
            last_lap_s=_lap_time(v.mLastLapTime), best_lap_s=_lap_time(v.mBestLapTime),
            estimated_lap_s=_lap_time(v.mEstimatedLapTime),
            time_behind_leader_s=round(v.mTimeBehindLeader, 3) if math.isfinite(v.mTimeBehindLeader) else None,
            laps_behind_leader=max(0, v.mLapsBehindLeader), in_pits=bool(v.mInPits), pitstops=max(0, v.mNumPitstops),
            is_player=v.mID == player_id,
        ))
        t = telem.get(v.mID)
        if t is not None:
            _vehicle_telemetry(result[-1], t)
    result.sort(key=lambda v: v.position or 10_000)
    return result


def _vehicle_telemetry(car: Vehicle, t: TelemInfo) -> None:
    """Dégâts et carburant d'une voiture (colonnes optionnelles des classements). Le jeu donne la télémétrie
    de toutes les voitures ; carburant à 0 sans réservoir connu = valeur non transmise (laissée à None)."""
    dents = list(t.mDentSeverity)
    car.dents = [min(max(int(dents[i]), 0), 2) for i in DENT_ORDER]
    car.parts_detached = bool(t.mDetached)
    car.wheels_off = sum(1 for w in t.mWheels if w.mFlat or w.mDetached)
    fuel = _finite(t.mFuel, 0, 1000)
    if fuel is not None and (fuel > 0 or t.mFuelCapacity > 0):
        car.fuel_l = round(fuel, 3)
    if 0 < t.mVirtualEnergy <= 1.5:
        car.energy_pct = round(min(t.mVirtualEnergy, 1.0) * 100, 3)


def find_player(data: ObjectOut) -> tuple[VehicleScoring | None, TelemInfo | None]:
    """Véhicule du joueur : scoring (mIsPlayer, sinon mControl == 0) et télémétrie (même mID)."""
    n = max(0, min(data.scoring.scoringInfo.mNumVehicles, MAX_VEHICLES))
    vehicles = data.scoring.vehScoringInfo[:n]
    scoring = next((v for v in vehicles if v.mIsPlayer), None)
    if scoring is None:
        scoring = next((v for v in vehicles if v.mControl == 0), None)

    tele = data.telemetry
    active = min(tele.activeVehicles, MAX_VEHICLES)
    telem = None
    if scoring is not None:
        telem = next((t for t in tele.telemInfo[:active] if t.mID == scoring.mID), None)
    if telem is None and tele.playerHasVehicle and tele.playerVehicleIdx < active:
        telem = tele.telemInfo[tele.playerVehicleIdx]
    return scoring, telem


# mSector et mSectorFlag : 0 = secteur 3, 1 = secteur 1, 2 = secteur 2
SECTORS = {0: 3, 1: 1, 2: 2}


def _finite(value: float, lo: float = -1e6, hi: float = 1e6) -> float | None:
    return float(value) if math.isfinite(value) and lo <= value <= hi else None


def _session_and_track(snap: Snapshot, info: ScoringInfo) -> None:
    """Session et piste (F10) : phase, drapeaux, météo."""
    snap.session_elapsed_s = _finite(info.mCurrentET, 0)
    if info.mEndET > 0:
        snap.session_length_s = _finite(info.mEndET, 0)
    snap.game_phase = info.mGamePhase
    state = info.mYellowFlagState  # c_char : un octet
    state = state[0] if state else 0
    snap.yellow_flag_state = state - 256 if state > 127 else state  # char signé : -1 = invalide
    raw = list(info.mSectorFlag)
    snap.sector_flags = [raw[1], raw[2], raw[0]]
    snap.air_temp_c = _finite(info.mAmbientTemp, -60, 80)
    snap.track_temp_c = _finite(info.mTrackTemp, -60, 100)
    snap.raining = _finite(info.mRaining, 0, 1)
    snap.wetness = _finite(info.mAvgPathWetness, 0, 1)
    snap.cloud_coverage = info.mCloudCoverage if info.mCloudCoverage <= 7 else None
    snap.track_grip = info.mTrackGripLevel if info.mTrackGripLevel <= 4 else None
    snap.time_of_day_s = _finite(info.mTimeOfDay, 0, 86400)


def to_snapshot(data: ObjectOut) -> Snapshot:
    info = data.scoring.scoringInfo
    snap = Snapshot(connected=True, source="lmu")
    snap.session = session_name(info.mSession)
    snap.track = _text(info.mTrackName)
    if info.mEndET > 0:
        snap.session_time_left_s = round(max(0.0, info.mEndET - info.mCurrentET), 3)
    if 0 < info.mMaxLaps < MAX_RACE_LAPS:  # course chronométrée : mMaxLaps vaut un très grand nombre
        snap.max_laps = info.mMaxLaps
    _session_and_track(snap, info)

    scoring, telem = find_player(data)
    snap.vehicles = vehicles(data, scoring.mID if scoring is not None else None)
    if scoring is not None:
        snap.car = _text(scoring.mVehicleName)
        snap.car_class = _text(scoring.mVehicleClass)
        snap.lap = scoring.mTotalLaps + 1  # tour en cours
        snap.position = scoring.mPlace
        snap.last_lap_s = _lap_time(scoring.mLastLapTime)
        snap.last_sector1_s = _lap_time(scoring.mLastSector1)
        snap.last_sector2_s = _lap_time(scoring.mLastSector2)
        snap.best_lap_s = _lap_time(scoring.mBestLapTime)
        snap.current_lap_s = round(max(0.0, info.mCurrentET - scoring.mLapStartET), 3)
        snap.in_pits = bool(scoring.mInPits)
        snap.player_flag = scoring.mFlag
        snap.sector = SECTORS.get(scoring.mSector, 0)
        if info.mLapDist > 0:
            snap.lap_fraction = round(min(max(scoring.mLapDist / info.mLapDist, 0.0), 1.0), 4)
    if telem is not None:
        v = telem.mLocalVel
        snap.speed_kmh = round(math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) * 3.6, 1)
        snap.rpm = round(telem.mEngineRPM)
        snap.gear = telem.mGear
        snap.max_rpm = round(max(telem.mEngineMaxRPM, 0.0))
        snap.max_gears = telem.mMaxGears
        snap.car_model = _text(telem.mVehicleModel)
        snap.fuel_l = round(telem.mFuel, 2)
        snap.fuel_capacity_l = round(telem.mFuelCapacity, 1)
        if telem.mVirtualEnergy > 0:  # fraction 0-1 ; 0 pour les voitures sans énergie virtuelle
            snap.virtual_energy_pct = round(min(telem.mVirtualEnergy, 1.0) * 100, 2)
        snap.car = snap.car or _text(telem.mVehicleName)
        snap.track = snap.track or _text(telem.mTrackName)
        if scoring is None:
            snap.lap = telem.mLapNumber
        # Le temps télémétrie est plus fin (mise à jour à chaque frame physique)
        snap.current_lap_s = round(max(0.0, telem.mElapsedTime - telem.mLapStartET), 3)
        snap.lap_invalid = bool(telem.mLapInvalidated)
        snap.wheels = [_wheel(w, left_side=(i % 2 == 0)) for i, w in enumerate(telem.mWheels)]
        _damage(snap, telem)
        _inputs(snap, telem)
        if scoring is not None and info.mLapDist > 0:
            # mLapDist n'est mis à jour qu'au rythme du scoring (~5 Hz) : on l'avance à l'instant de la
            # télémétrie avec la vitesse, sinon le delta (F03) tremblerait de quelques dixièmes.
            dt = telem.mElapsedTime - info.mCurrentET
            if 0 < dt < 0.5:
                dist = scoring.mLapDist + snap.speed_kmh / 3.6 * dt
                snap.lap_fraction = round(min(max(dist / info.mLapDist, 0.0), 1.0), 4)
    return snap


def parse_buffer(buf: Any) -> Snapshot:
    """Convertit un tampon « LMU_Data » (bytes, bytearray, mmap…) en Snapshot."""
    if len(buf) < MAP_SIZE:
        raise ValueError(f"tampon trop court : {len(buf)} < {MAP_SIZE}")
    return to_snapshot(ObjectOut.from_buffer_copy(buf[:MAP_SIZE]))


# --- Lecture cohérente ------------------------------------------------------


def _signature(buf: Any) -> bytes:
    """Petits champs qui changent à chaque écriture du jeu : compteurs d'événements,
    horloge du scoring, en-tête télémétrie et horloge de la voiture du joueur."""
    header = bytes(buf[_OFF_TELEMETRY:_OFF_TELEMETRY + 3])
    sig = bytes(buf[_OFF_EVENTS:_OFF_EVENTS + ctypes.sizeof(Events)])
    sig += bytes(buf[_OFF_SCORING_ET:_OFF_SCORING_ET + 8]) + header
    active, idx, has_player = header
    if has_player and idx < min(active, MAX_VEHICLES):
        off = _OFF_TELEM_INFO + idx * _TELEM_SIZE + TelemInfo.mElapsedTime.offset
        sig += bytes(buf[off:off + 8])
    return sig


def read_consistent(buf: Any, tries: int = 5) -> bytes:
    """Copie le tampon ; recommence si le jeu a écrit pendant la copie
    (signature différente avant/après). Après `tries` essais, garde la dernière copie."""
    copy = b""
    for _ in range(max(1, tries)):
        before = _signature(buf)
        copy = bytes(buf[:MAP_SIZE])
        if _signature(buf) == before:
            break
    return copy


def _unit(value: float, lo: float = 0.0) -> float:
    return round(min(max(value, lo), 1.0), 3) if math.isfinite(value) else 0.0


def _inputs(snap: Snapshot, telem: TelemInfo) -> None:
    """Inputs (F12) : commandes brutes du pilote (avant filtrage, aides comprises)."""
    snap.throttle = _unit(telem.mUnfilteredThrottle)
    snap.brake = _unit(telem.mUnfilteredBrake)
    snap.clutch = _unit(telem.mUnfilteredClutch)
    snap.steering = _unit(telem.mUnfilteredSteering, -1.0)
    rng = telem.mPhysicalSteeringWheelRange
    snap.steering_range_deg = round(float(rng), 1) if math.isfinite(rng) and 90 <= rng <= 2000 else None
    snap.abs_active = bool(telem.mABSActive)
    snap.tc_active = bool(telem.mTCActive)


# --- API REST locale du jeu (aéro, suspension, réparation) ---------------------

REST_URL = "http://127.0.0.1:6397"
REST_EVERY_S = 2.0


def parse_rest(repair_and_refuel: dict | None, pitstop_estimate: dict | None) -> dict:
    """Réponses de /rest/garage/UIScreen/RepairAndRefuel et /rest/strategy/pitstop-estimate →
    champs du Snapshot (aero_damage, suspension_damage, repair_time_s). Champs absents ignorés."""
    out: dict = {}
    wear = (repair_and_refuel or {}).get("wearables") or {}
    aero = (wear.get("body") or {}).get("aero") if isinstance(wear.get("body"), dict) else None
    if isinstance(aero, (int, float)) and 0 <= aero <= 1:
        out["aero_damage"] = float(aero)
    susp = wear.get("suspension")
    if isinstance(susp, list) and len(susp) >= 4 and all(isinstance(x, (int, float)) for x in susp[:4]):
        out["suspension_damage"] = [float(x) for x in susp[:4]]
    repair = (pitstop_estimate or {}).get("damage")
    if isinstance(repair, (int, float)) and repair >= 0:
        out["repair_time_s"] = float(repair)
    return out


FORECAST_NODES = (("START", 0.0), ("NODE_25", 0.25), ("NODE_50", 0.5), ("NODE_75", 0.75), ("FINISH", 1.0))
WEATHER_EVERY_S = 15.0  # la prévision change rarement


def parse_weather(data: dict | None) -> dict[str, list[ForecastNode]]:
    """Réponse de /rest/sessions/weather → prévision par type de session (PRACTICE, QUALIFY, RACE) :
    5 points (départ, 25 %, 50 %, 75 %, fin), chacun avec WNV_SKY (0-10), WNV_TEMPERATURE (°C) et
    WNV_RAIN_CHANCE (%). Une session illisible est ignorée."""
    out: dict[str, list[ForecastNode]] = {}
    for session, nodes in (data or {}).items():
        if not isinstance(nodes, dict):
            continue
        try:
            points = []
            for name, at in FORECAST_NODES:
                node = nodes[name]
                sky = int(node["WNV_SKY"]["currentValue"])
                temp = float(node["WNV_TEMPERATURE"]["currentValue"])
                rain = float(node["WNV_RAIN_CHANCE"]["currentValue"])
                if not (0 <= sky <= 10 and math.isfinite(temp) and -60 < temp < 80 and math.isfinite(rain)):
                    raise ValueError
                points.append(ForecastNode(at=at, sky=sky, air_temp_c=round(temp, 1),
                                           rain_chance_pct=min(max(rain, 0.0), 100.0)))
        except (KeyError, TypeError, ValueError):
            continue
        out[str(session).upper()] = points
    return out


def forecast_for(forecasts: dict[str, list[ForecastNode]], session: str) -> list[ForecastNode]:
    """Prévision de la session en cours (nom donné par `session_name`)."""
    kind = "RACE" if session.startswith(("Course", "Warm-up")) else "QUALIFY" if session.startswith("Qualif") else "PRACTICE"
    return list(forecasts.get(kind, []))


class RestPoller:
    """Interroge l'API REST locale du jeu dans un fil séparé (la lecture de la mémoire partagée ne doit
    jamais attendre le réseau). `latest` = derniers champs lus, vide si l'API ne répond pas."""

    def __init__(self, base_url: str = REST_URL, every_s: float = REST_EVERY_S) -> None:
        self.base_url = base_url
        self.every_s = every_s
        self.latest: dict = {}
        self.forecasts: dict[str, list[ForecastNode]] = {}
        self._weather_at = 0.0
        self._stop = None
        self._thread = None

    def _get(self, path: str) -> dict | None:
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(self.base_url + path, timeout=1.0) as r:
                data = json.load(r)
                return data if isinstance(data, dict) else None
        except Exception:
            return None

    def poll_once(self) -> None:
        self.latest = parse_rest(self._get("/rest/garage/UIScreen/RepairAndRefuel"),
                                 self._get("/rest/strategy/pitstop-estimate"))
        now = time.monotonic()
        if now >= self._weather_at:
            self._weather_at = now + WEATHER_EVERY_S
            self.forecasts = parse_weather(self._get("/rest/sessions/weather"))

    def start(self) -> None:
        import threading

        if self._thread is not None:
            return
        stop = self._stop = threading.Event()

        def run() -> None:
            while not stop.is_set():
                self.poll_once()
                stop.wait(self.every_s)

        self._thread = threading.Thread(target=run, name="lmu-rest", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        self._thread = None
        self.latest = {}
        self.forecasts = {}
        self._weather_at = 0.0


# --- Source Windows ----------------------------------------------------------


def _map_exists(name: str) -> bool:
    """Vrai si le jeu a créé la zone (OpenFileMappingW, sans la créer nous-mêmes)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenFileMappingW.restype = ctypes.c_void_p
    k32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = k32.OpenFileMappingW(0x0004, False, name)  # FILE_MAP_READ
    if not handle:
        return False
    k32.CloseHandle(handle)
    return True


def _window_alive(hwnd: int) -> bool:
    if not hwnd:
        return True  # pas de fenêtre connue : on ne conclut pas
    user32 = ctypes.WinDLL("user32")
    user32.IsWindow.argtypes = [ctypes.c_void_p]
    return bool(user32.IsWindow(ctypes.c_void_p(hwnd)))


class LmuSharedMemorySource(DataSource):
    name = "lmu"
    RETRY_S = 2.0  # délai entre deux tentatives d'ouverture

    def __init__(self) -> None:
        self._mm: Any = None
        self._next_try = 0.0
        self.rest = RestPoller()

    def _open(self) -> bool:
        now = time.monotonic()
        if now < self._next_try:
            return False
        self._next_try = now + self.RETRY_S
        if sys.platform != "win32":
            return False
        import mmap

        try:
            if not _map_exists(MAP_NAME):
                return False
            self._mm = mmap.mmap(-1, MAP_SIZE, tagname=MAP_NAME, access=mmap.ACCESS_READ)
        except OSError:
            self._mm = None
            return False
        return True

    def read(self) -> Snapshot:
        if self._mm is None and not self._open():
            return Snapshot(connected=False, source=self.name)
        try:
            raw = read_consistent(self._mm)
            data = ObjectOut.from_buffer_copy(raw)
            if not _window_alive(data.generic.appInfo.mAppWindow):
                # Jeu fermé : notre handle garderait la zone en vie, on la libère
                self.close()
                return Snapshot(connected=False, source=self.name)
            self.rest.start()
            snap = to_snapshot(data)
            for k, v in self.rest.latest.items():
                setattr(snap, k, v)
            snap.weather_forecast = forecast_for(self.rest.forecasts, snap.session)
            return snap
        except (OSError, ValueError):
            self.close()
            return Snapshot(connected=False, source=self.name)

    def close(self) -> None:
        self.rest.stop()
        if self._mm is not None:
            try:
                self._mm.close()
            except (OSError, BufferError):
                pass
            self._mm = None
