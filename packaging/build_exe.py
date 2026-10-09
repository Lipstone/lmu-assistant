"""Construit l'exécutable LMU-Assistant avec PyInstaller.

    pip install -e ".[overlay,build]"
    python packaging/build_exe.py

Résultat : dist/LMU-Assistant.exe (Windows) ou dist/LMU-Assistant (autres OS, pour les tests).

    python packaging/build_exe.py --onedir

Résultat : dossier dist/LMU-Assistant/ (exe + bibliothèques), utilisé par l'installateur
(packaging/installer.iss) : démarrage plus rapide, rien à décompresser à chaque lancement.
"""

import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    onedir = "--onedir" in sys.argv[1:]
    work = ROOT / ("build-onedir" if onedir else "build")
    args = [
        str(ROOT / "packaging" / "launch.py"),
        "--name", "LMU-Assistant",
        "--onedir" if onedir else "--onefile",
        "--windowed",  # pas de console : messages dans data/lmu-assistant.log ; fermer l'interface = quitter
        "--noconfirm",
        "--clean",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(work),
        "--specpath", str(work),
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
