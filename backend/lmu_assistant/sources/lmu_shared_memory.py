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
import sys
import time
from typing import Any

from ..model import Snapshot, Wheel
from .base import DataSource

MAP_NAME = "LMU_Data"
MAX_VEHICLES = 104
MAX_PATH_LENGTH = 260
KELVIN = 273.15


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
        ("mBrakeTemp", ctypes.c_double),  # °C
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


def _wheel(w: TelemWheel, left_side: bool) -> Wheel:
    # mTemperature = gauche/centre/droite vu du pilote : côté gauche, l'extérieur est à gauche
    left, middle, right = (t - KELVIN for t in w.mTemperature)
    inner, outer = (right, left) if left_side else (left, right)
    return Wheel(
        temp_c=(round(inner, 1), round(middle, 1), round(outer, 1)),
        pressure_kpa=round(w.mPressure, 1),
        wear=round(w.mWear, 4),
        brake_temp_c=round(w.mBrakeTemp, 1),
    )


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


def to_snapshot(data: ObjectOut) -> Snapshot:
    info = data.scoring.scoringInfo
    snap = Snapshot(connected=True, source="lmu")
    snap.session = session_name(info.mSession)
    snap.track = _text(info.mTrackName)
    if info.mEndET > 0:
        snap.session_time_left_s = round(max(0.0, info.mEndET - info.mCurrentET), 3)

    scoring, telem = find_player(data)
    if scoring is not None:
        snap.car = _text(scoring.mVehicleName)
        snap.lap = scoring.mTotalLaps + 1  # tour en cours
        snap.position = scoring.mPlace
        snap.last_lap_s = _lap_time(scoring.mLastLapTime)
        snap.best_lap_s = _lap_time(scoring.mBestLapTime)
        snap.current_lap_s = round(max(0.0, info.mCurrentET - scoring.mLapStartET), 3)
    if telem is not None:
        v = telem.mLocalVel
        snap.speed_kmh = round(math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) * 3.6, 1)
        snap.rpm = round(telem.mEngineRPM)
        snap.gear = telem.mGear
        snap.fuel_l = round(telem.mFuel, 2)
        snap.fuel_capacity_l = round(telem.mFuelCapacity, 1)
        snap.car = snap.car or _text(telem.mVehicleName)
        snap.track = snap.track or _text(telem.mTrackName)
        if scoring is None:
            snap.lap = telem.mLapNumber
        # Le temps télémétrie est plus fin (mise à jour à chaque frame physique)
        snap.current_lap_s = round(max(0.0, telem.mElapsedTime - telem.mLapStartET), 3)
        snap.wheels = [_wheel(w, left_side=(i % 2 == 0)) for i, w in enumerate(telem.mWheels)]
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
            return to_snapshot(data)
        except (OSError, ValueError):
            self.close()
            return Snapshot(connected=False, source=self.name)

    def close(self) -> None:
        if self._mm is not None:
            try:
                self._mm.close()
            except (OSError, BufferError):
                pass
            self._mm = None
