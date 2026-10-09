"""Configuration de l'overlay : widgets affichés, positions, taille, transparence (fond et texte), raccourci.

L'overlay ouvre une fenêtre transparente par widget : `x`/`y` d'un widget sont sa position sur l'écran,
la taille de sa fenêtre est `WIDGET_SIZES` × `scale`.

La configuration est un fichier JSON (par défaut `data/config.json` à la racine du dépôt ou à côté de l'exécutable,
modifiable avec `--config`). Un fichier absent ou invalide donne la configuration par défaut.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .paths import data_dir

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = data_dir() / "config.json"

# Identifiants des widgets = attribut `data-widget` de web/index.html, dans l'ordre d'affichage.
WIDGET_IDS = ("lap", "delta", "fuel", "car", "tyres", "brakes", "relative", "standings", "pit", "session", "damage", "inputs", "stint", "weather")

# Position par défaut de chaque fenêtre sur l'écran (pixels, coin haut gauche).
_DEFAULT_POSITIONS = {
    "lap": (20, 20),
    "delta": (860, 20),
    "fuel": (20, 310),
    "car": (260, 20),
    "tyres": (260, 150),
    "brakes": (260, 340),
    "relative": (1500, 600),
    "standings": (1500, 220),
    "pit": (20, 540),
    "session": (1100, 20),
    "damage": (1100, 290),
    "inputs": (760, 860),
    "stint": (290, 540),
    "weather": (1340, 20),
}

# Taille de la fenêtre d'un widget à l'échelle 1 (largeur, hauteur en pixels), contenu compris. L'overlay ajuste
# ensuite chaque fenêtre à la taille réelle du widget (colonnes optionnelles du relative et du classement).
WIDGET_SIZES = {
    "lap": (220, 276),
    "delta": (200, 196),
    "fuel": (200, 210),
    "car": (180, 118),
    "tyres": (250, 178),
    "brakes": (200, 204),
    "relative": (300, 196),
    "standings": (300, 350),
    "pit": (250, 190),
    "session": (230, 252),
    "damage": (230, 300),
    "inputs": (300, 132),
    "stint": (240, 200),
    "weather": (260, 230),
}


def window_size(widget_id: str, scale: float) -> tuple[int, int]:
    w, h = WIDGET_SIZES[widget_id]
    return round(w * scale), round(h * scale)


class WidgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    visible: bool = True
    x: int = Field(0, ge=-10000, le=10000, description="position de la fenêtre du widget sur l'écran (pixels)")
    y: int = Field(0, ge=-10000, le=10000)
    scale: float = Field(1.0, ge=0.25, le=4.0)
    background_opacity: float | None = Field(
        None, ge=0.0, le=1.0, description="opacité du fond du widget en overlay (None = globale)"
    )
    text_opacity: float | None = Field(
        None, ge=0.1, le=1.0, description="opacité du texte et des jauges du widget en overlay (None = globale)"
    )
    show_damage: bool = Field(
        False, description="widgets Relative et Classement : colonne des dégâts globaux de chaque voiture"
    )
    show_remaining: bool = Field(
        False, description="widgets Relative et Classement : colonne du carburant ou de l'énergie restant dans chaque voiture"
    )
    show_consumption: bool = Field(
        False, description="widgets Relative et Classement : colonne de la consommation par tour de chaque voiture"
    )
    show_best_lap: bool = Field(False, description="widgets Relative et Classement : colonne du meilleur tour de chaque voiture")
    show_last_lap: bool = Field(
        False,
        description="widgets Relative et Classement : colonne du dernier tour de chaque voiture "
        "(affichée par défaut dans le Classement, comme avant qu'elle soit réglable)",
    )

    @model_validator(mode="before")
    @classmethod
    def _old_opacity(cls, data):
        data = _migrate_opacity(data, is_global=False)
        # Le Classement affichait toujours le dernier tour : on le garde par défaut
        if isinstance(data, dict) and data.get("id") == "standings" and "show_last_lap" not in data:
            data = {**data, "show_last_lap": True}
        return data

    @field_validator("id")
    @classmethod
    def _known_id(cls, v: str) -> str:
        if v not in WIDGET_IDS:
            raise ValueError(f"widget inconnu : {v!r} (attendus : {', '.join(WIDGET_IDS)})")
        return v


class OverlayWindow(BaseModel):
    """Réglages communs aux fenêtres overlay. Ignore les anciens champs x/y/width/height
    (fenêtre unique d'avant le découpage en une fenêtre par widget)."""

    model_config = ConfigDict(extra="ignore")

    click_through: bool = Field(True, description="les clics traversent l'overlay vers le jeu (Windows)")


OLD_DEFAULT_OPACITY = 0.85  # ancien champ `opacity`, avant la séparation fond / texte


def _migrate_opacity(data, is_global: bool):
    """Ancien champ `opacity` (tout le widget, fond compris) -> `text_opacity`, avec le fond multiplié d'autant
    pour garder le même rendu. Un `opacity` global resté à l'ancien défaut donne les nouveaux défauts."""
    if not isinstance(data, dict) or "opacity" not in data:
        return data
    data = dict(data)
    old = data.pop("opacity")
    if not isinstance(old, (int, float)) or isinstance(old, bool) or (is_global and old == OLD_DEFAULT_OPACITY):
        return data
    data.setdefault("text_opacity", old)
    bg = data.get("background_opacity", 0.75 if is_global else None)
    if isinstance(bg, (int, float)) and not isinstance(bg, bool):
        data["background_opacity"] = round(bg * old, 3)
    return data


def _default_widgets() -> list[WidgetConfig]:
    return [WidgetConfig(id=w, x=_DEFAULT_POSITIONS[w][0], y=_DEFAULT_POSITIONS[w][1]) for w in WIDGET_IDS]


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    widgets: list[WidgetConfig] = Field(default_factory=_default_widgets)
    background_opacity: float = Field(
        0.75, ge=0.0, le=1.0, description="opacité globale du fond des widgets en overlay (0 = texte seul)"
    )
    text_opacity: float = Field(1.0, ge=0.1, le=1.0, description="opacité globale du texte et des jauges en overlay")
    window: OverlayWindow = Field(default_factory=OverlayWindow)
    fuel_mode: Literal["auto", "fuel", "energy"] = Field(
        "auto", description="widget Carburant : litres, % d'énergie virtuelle, ou auto (% EV si la voiture en a)"
    )
    delta_reference: Literal["best", "last", "record"] = Field(
        "best", description="widget Delta : meilleur tour de la session, dernier tour ou record personnel"
    )
    laptime_avg_laps: int = Field(
        5, ge=2, le=20, description="widget Temps au tour : nombre de tours valides pour la moyenne et la régularité"
    )
    tyre_temp_min_c: float = Field(75.0, ge=0, le=200, description="widget Pneus : bas de la plage de température idéale")
    tyre_temp_max_c: float = Field(100.0, ge=0, le=200, description="widget Pneus : haut de la plage de température idéale")
    pressure_unit: Literal["kpa", "psi", "bar"] = Field("kpa", description="widget Pneus : unité des pressions")
    brake_overheat_c: float = Field(800.0, ge=100, le=2000, description="widget Freins : seuil d'alerte surchauffe (°C)")
    pit_loss_s: float = Field(
        60.0, ge=0, le=600, description="widget Stand : temps perdu au stand tant qu'aucun arrêt n'a été mesuré (s)"
    )
    refresh_hz: int = Field(30, ge=5, le=60, description="rafraîchissement des données envoyées aux widgets (par seconde)")
    inputs_trace_s: float = Field(8.0, ge=2, le=30, description="widget Inputs : durée de la trace (s)")
    hotkey: str = Field("ctrl+shift+o", min_length=1, max_length=64)
    placement: bool = Field(
        False, description="mode placement : fenêtres overlay déplaçables et agrandissables à la souris"
    )
    placement_hotkey: str = Field("ctrl+shift+p", min_length=1, max_length=64)
    lan_access: bool = Field(
        False,
        description="page accessible depuis le réseau local (tablette, QR code) ; pris en compte au redémarrage, "
        "Windows demande alors d'autoriser l'appli dans le pare-feu",
    )

    @model_validator(mode="before")
    @classmethod
    def _old_opacity(cls, data):
        return _migrate_opacity(data, is_global=True)

    @field_validator("hotkey", "placement_hotkey")
    @classmethod
    def _clean_hotkey(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("raccourci vide")
        return v

    @model_validator(mode="after")
    def _tyre_range(self) -> AppConfig:
        if self.tyre_temp_min_c >= self.tyre_temp_max_c:
            raise ValueError("plage idéale des pneus : le minimum doit être sous le maximum")
        return self

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
