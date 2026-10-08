import gzip
import json
from pathlib import Path

import pytest

from lmu_assistant.model import Snapshot, Wheel
from lmu_assistant.sources import get_source
from lmu_assistant.sources.recording import (
    FORMAT_NAME,
    RecordingSource,
    ReplaySource,
    load_recording,
    snapshot_from_dict,
)

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "mock_60s.jsonl.gz"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


def _record(path, n=20, dt=0.1):
    clock = FakeClock()
    rec = RecordingSource(get_source("mock"), path, clock=clock)
    snaps = []
    for _ in range(n):
        snaps.append(rec.read().to_dict())
        clock.advance(dt)
    rec.close()
    return snaps


def test_roundtrip_mock_to_replay(tmp_path):
    path = tmp_path / "session.jsonl.gz"
    recorded = _record(path)

    with gzip.open(path, "rt", encoding="utf-8") as f:
        header = json.loads(f.readline())
    assert header["format"] == FORMAT_NAME and header["version"] == 1 and header["source"] == "mock"

    clock = FakeClock()
    replay = ReplaySource(path, clock=clock)
    replayed = []
    for _ in recorded:
        snap = replay.read()
        assert isinstance(snap.wheels[0], Wheel)
        assert isinstance(snap.wheels[0].temp_c, tuple)
        replayed.append(snap.to_dict())
        clock.advance(0.1)
    assert replayed == recorded


def test_speed_factor(tmp_path):
    path = tmp_path / "s.jsonl.gz"
    recorded = _record(path, n=20, dt=0.1)
    clock = FakeClock()
    replay = get_source("replay", path=path, speed=4.0, clock=clock)
    assert replay.read().to_dict() == recorded[0]
    clock.advance(0.25)  # 0,25 s × 4 = 1,0 s d'enregistrement
    assert replay.read().to_dict() == recorded[10]


def test_end_of_file_holds_last_snapshot(tmp_path):
    path = tmp_path / "s.jsonl.gz"
    recorded = _record(path, n=5, dt=1.0)
    clock = FakeClock()
    replay = ReplaySource(path, clock=clock)
    replay.read()
    clock.advance(100)
    assert replay.read().to_dict() == recorded[-1]


def test_loop(tmp_path):
    path = tmp_path / "s.jsonl.gz"
    recorded = _record(path, n=5, dt=1.0)  # t = 0..4, boucle de 5 s
    clock = FakeClock()
    replay = ReplaySource(path, loop=True, clock=clock)
    seen = []
    for _ in range(12):
        seen.append(replay.read().to_dict())
        clock.advance(1.0)
    assert seen == recorded + recorded + recorded[:2]


def test_compat_missing_and_extra_fields(tmp_path):
    path = tmp_path / "old.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"format": FORMAT_NAME, "version": 1, "source": "lmu"}) + "\n")
        data = {"connected": True, "lap": 7, "champ_futur": 42, "wheels": [{"pressure_kpa": 170, "inconnu": 1}]}
        f.write(json.dumps({"t": 0.0, "data": data}) + "\n")
    snap = ReplaySource(path, clock=FakeClock()).read()
    assert snap.connected and snap.lap == 7
    assert snap.fuel_l == Snapshot().fuel_l  # champ absent → valeur par défaut
    assert snap.wheels[0].pressure_kpa == 170 and snap.wheels[0].wear == 1.0
    assert not hasattr(snap, "champ_futur")


def test_snapshot_from_dict_none_values():
    snap = snapshot_from_dict({"last_lap_s": None, "best_lap_s": 101.5})
    assert snap.last_lap_s is None and snap.best_lap_s == 101.5


def test_truncated_file_is_readable(tmp_path):
    path = tmp_path / "s.jsonl.gz"
    recorded = _record(path, n=200)
    raw = path.read_bytes()
    path.write_bytes(raw[: len(raw) * 2 // 3])
    header, frames = load_recording(path)
    assert header["source"] == "mock"
    assert 0 < len(frames) < len(recorded)


def test_recording_creates_default_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rec = RecordingSource(get_source("mock"))
    rec.read()
    rec.close()
    assert rec.path.exists()
    assert rec.path.parent == Path("data") / "recordings"
    assert rec.path.name.endswith("_mock.jsonl.gz")


def test_sample_recording_replays():
    replay = ReplaySource(SAMPLE, speed=10.0, clock=FakeClock())
    snap = replay.read()
    assert snap.connected and len(snap.wheels) == 4


def test_unknown_source():
    with pytest.raises(ValueError):
        get_source("inexistante")
