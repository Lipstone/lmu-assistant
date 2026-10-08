"""Configuration de l'overlay : widgets affichés, positions, taille, opacité, raccourci.

La configuration est un fichier JSON (par défaut `data/config.json` à la racine du dépôt,
modifiable avec `--config`). Un fichier absent ou invalide donne la configuration par défaut.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config.json"

# Identifiants des widgets = attribut `data-widget` de web/index.html, dans l'ordre d'affichage.
WIDGET_IDS = ("lap", "fuel", "car", "tyres")

_DEFAULT_POSITIONS = {"lap": (8, 8), "fuel": (196, 8), "car": (8, 170), "tyres": (196, 170)}


class WidgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    visible: bool = True
    x: int = Field(0, ge=0, le=10000, description="position en pixels dans la fenêtre overlay")
    y: int = Field(0, ge=0, le=10000)
    scale: float = Field(1.0, ge=0.25, le=4.0)

    @field_validator("id")
    @classmethod
    def _known_id(cls, v: str) -> str:
        if v not in WIDGET_IDS:
            raise ValueError(f"widget inconnu : {v!r} (attendus : {', '.join(WIDGET_IDS)})")
        return v


class OverlayWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(20, ge=-10000, le=10000)
    y: int = Field(20, ge=-10000, le=10000)
    width: int = Field(400, ge=50, le=10000)
    height: int = Field(420, ge=50, le=10000)
    click_through: bool = Field(True, description="les clics traversent l'overlay vers le jeu (Windows)")


def _default_widgets() -> list[WidgetConfig]:
    return [WidgetConfig(id=w, x=_DEFAULT_POSITIONS[w][0], y=_DEFAULT_POSITIONS[w][1]) for w in WIDGET_IDS]


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    widgets: list[WidgetConfig] = Field(default_factory=_default_widgets)
    opacity: float = Field(0.85, ge=0.1, le=1.0, description="opacité globale des widgets en overlay")
    window: OverlayWindow = Field(default_factory=OverlayWindow)
    hotkey: str = Field("ctrl+shift+o", min_length=1, max_length=64)

    @field_validator("hotkey")
    @classmethod
    def _clean_hotkey(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("raccourci vide")
        return v

    @field_validator("widgets")
    @classmethod
    def _complete_widgets(cls, widgets: list[WidgetConfig]) -> list[WidgetConfig]:
        """Refuse les doublons et ajoute (avec les valeurs par défaut) les widgets absents."""
        seen = [w.id for w in widgets]
        dup = {i for i in seen if seen.count(i) > 1}
        if dup:
            raise ValueError(f"widget en double : {', '.join(sorted(dup))}")
        missing = [w for w in _default_widgets() if w.id not in seen]
        return list(widgets) + missing


class ConfigStore:
    """Lit et écrit la configuration dans un fichier JSON."""

    def __init__(self, path: str | os.PathLike | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_CONFIG_PATH
        self.config = self.load()

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            return AppConfig.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, ValidationError) as exc:
            log.warning("Config %s illisible, valeurs par défaut utilisées : %s", self.path, exc)
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        """Écrit de façon atomique (fichier temporaire puis remplacement)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".config-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self.config = config
