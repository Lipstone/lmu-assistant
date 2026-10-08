"""Construit l'exécutable LMU-Assistant avec PyInstaller.

    pip install -e ".[overlay,build]"
    python packaging/build_exe.py

Résultat : dist/LMU-Assistant.exe (Windows) ou dist/LMU-Assistant (autres OS, pour les tests).
"""

import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    args = [
        str(ROOT / "packaging" / "launch.py"),
        "--name", "LMU-Assistant",
        "--onefile",
        "--console",  # la console affiche les adresses (réseau local, QR code) ; fermer = quitter
        "--noconfirm",
        "--clean",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        "--paths", str(ROOT / "backend"),
        "--add-data", f"{ROOT / 'web'}{os.pathsep}web",
        "--collect-submodules", "lmu_assistant",
        "--collect-submodules", "uvicorn",
        "--copy-metadata", "lmu-assistant",
    ]
    if sys.platform == "win32":
        args += ["--hidden-import", "keyboard"]
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
