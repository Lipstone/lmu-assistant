"""Enregistrement et relecture de sessions (T07).

Format du fichier : JSON Lines compressé en gzip (``.jsonl.gz``).

- 1re ligne : en-tête ``{"format": "lmu-assistant-recording", "version": 1, ...}``
  (source enregistrée, date de début, version de l'application) ;
- lignes suivantes : une image par lecture, ``{"t": <secondes depuis le début>, "data": <Snapshot.to_dict()>}``.

``RecordingSource`` enveloppe n'importe quelle source et écrit chaque Snapshot lu
(donc au rythme de diffusion du serveur). ``ReplaySource`` relit un fichier et
renvoie les Snapshot selon le temps écoulé × vitesse, ce qui permet de développer
et tester les fonctionnalités sans lancer le jeu.
"""

from __future__ import annotations

import bisect
import dataclasses
import gzip
import json
import time
import types
import typing
import zlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..model import Snapshot
from ..paths import data_dir, is_frozen
from .base import DataSource

FORMAT_NAME = "lmu-assistant-recording"
FORMAT_VERSION = 1
FLUSH_EVERY_S = 5.0  # vidage périodique : un arrêt brutal ne perd que les dernières secondes

Clock = Callable[[], float]


def default_recording_path(source_name: str, directory: str | Path | None = None) -> Path:
    if directory is None:
        # Exécutable : à côté de l'exe ; sinon relatif au dossier courant.
        directory = data_dir() / "recordings" if is_frozen() else Path("data") / "recordings"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path(directory) / f"{stamp}_{source_name}.jsonl.gz"


def _app_version() -> str:
    try:
        from importlib.metadata import version

        return version("lmu-assistant")
    except Exception:
        return "inconnue"


class RecordingSource(DataSource):
    """Enveloppe une source et enregistre chaque Snapshot lu dans un fichier."""

    def __init__(self, inner: DataSource, path: str | Path | None = None, clock: Clock = time.monotonic) -> None:
        self.inner = inner
        self.name = inner.name
        self.path = Path(path) if path else default_recording_path(inner.name)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._start: float | None = None
        self._last_flush = 0.0
        self._file = gzip.open(self.path, "wt", encoding="utf-8", newline="\n")
        header = {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "source": inner.name,
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "app_version": _app_version(),
        }
        self._write(header)

    def _write(self, obj: dict) -> None:
        self._file.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")

    def read(self) -> Snapshot:
        snap = self.inner.read()
        if self._file is None:
            return snap
        now = self._clock()
        if self._start is None:
            self._start = self._last_flush = now
        self._write({"t": round(now - self._start, 4), "data": snap.to_dict()})
        if now - self._last_flush >= FLUSH_EVERY_S:
            self._file.flush()
            self._file.buffer.flush(zlib.Z_SYNC_FLUSH)  # rend les données lisibles même sans fermeture
            self._last_flush = now
        return snap

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        self.inner.close()


# --- Reconstruction des dataclasses depuis un dict (tolérante) -----------------


def _convert(value: Any, hint: Any) -> Any:
    if value is None:
        return None
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Union or origin is types.UnionType:
        # Optionnel (X | None) : on convertit selon le premier type non None.
        non_none = [a for a in args if a is not type(None)]
        return _convert(value, non_none[0]) if len(non_none) == 1 else value
    if dataclasses.is_dataclass(hint) and isinstance(value, dict):
        return from_dict(hint, value)
    if origin is list and isinstance(value, list):
        return [_convert(v, args[0]) for v in value] if args else list(value)
    if origin is tuple and isinstance(value, (list, tuple)):
        return tuple(value)
    return value


def from_dict(cls: type, data: dict) -> Any:
    """Construit une dataclass depuis un dict : champs absents → valeur par défaut,
    champs inconnus ignorés (compatibilité avec les enregistrements plus anciens/récents)."""
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name in data:
            kwargs[f.name] = _convert(data[f.name], hints.get(f.name))
    return cls(**kwargs)


def snapshot_from_dict(data: dict) -> Snapshot:
    return from_dict(Snapshot, data)


# --- Relecture -------------------------------------------------------------------


def load_recording(path: str | Path) -> tuple[dict, list[tuple[float, dict]]]:
    """Lit un enregistrement : (en-tête, [(t, data), ...]).

    Un fichier tronqué (arrêt brutal pendant l'enregistrement) est lu jusqu'à la
    dernière ligne complète."""
    header: dict = {}
    frames: list[tuple[float, dict]] = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        try:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    break  # dernière ligne incomplète
                if "t" in obj and "data" in obj:
                    frames.append((float(obj["t"]), obj["data"]))
                elif not frames and not header:
                    header = obj
        except (EOFError, zlib.error, OSError):
            pass  # flux gzip tronqué : on garde ce qui a été lu
    if header and header.get("format") not in (None, FORMAT_NAME):
        raise ValueError(f"Fichier non reconnu : {path}")
    if not frames:
        raise ValueError(f"Enregistrement vide : {path}")
    frames.sort(key=lambda fr: fr[0])
    return header, frames


class ReplaySource(DataSource):
    """Rejoue un enregistrement selon le temps écoulé × ``speed``.

    En fin de fichier : reprend au début si ``loop``, sinon renvoie la dernière image.
    Le temps démarre à la première lecture."""

    name = "replay"

    def __init__(self, path: str | Path, speed: float = 1.0, loop: bool = False, clock: Clock = time.monotonic) -> None:
        if speed <= 0:
            raise ValueError("La vitesse de relecture doit être > 0")
        self.path = Path(path)
        self.speed = speed
        self.loop = loop
        self._clock = clock
        self._start: float | None = None
        self.header, frames = load_recording(self.path)
        self._times = [t for t, _ in frames]
        self._data = [d for _, d in frames]
        # Durée d'une boucle : dernière image + un intervalle, pour ne pas sauter la 1re image.
        step = self._times[-1] - self._times[-2] if len(self._times) > 1 else 0.0
        self.duration = self._times[-1] + step

    def position(self) -> float:
        """Temps de l'enregistrement (s) correspondant à maintenant."""
        now = self._clock()
        if self._start is None:
            self._start = now
        t = (now - self._start) * self.speed + self._times[0]
        period = self.duration - self._times[0]
        if self.loop and period > 0:
            t = self._times[0] + (t - self._times[0]) % period
        return t

    def read(self) -> Snapshot:
        i = bisect.bisect_right(self._times, self.position()) - 1
        return snapshot_from_dict(self._data[max(0, i)])
