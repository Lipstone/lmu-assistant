"""Emplacements des fichiers, en développement comme dans l'exécutable (PyInstaller)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    """Vrai quand on tourne depuis l'exécutable construit par PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Dossier des fichiers embarqués (web/) : décompressés par PyInstaller, ou racine du dépôt."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return REPO_ROOT


def data_dir() -> Path:
    """Dossier des données utilisateur (config, enregistrements) : à côté de l'exe, ou data/ du dépôt."""
    if is_frozen():
        return Path(sys.executable).resolve().parent / "data"
    return REPO_ROOT / "data"
