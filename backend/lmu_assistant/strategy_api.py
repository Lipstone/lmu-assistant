"""API du planificateur de stratégie (F24)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from .strategy import StrategyInput, defaults_from_snapshot, plan


def make_strategy_router(latest: Callable[[], dict]) -> APIRouter:
    router = APIRouter(prefix="/api/strategy")

    @router.get("/defaults")
    def defaults() -> dict:
        """Paramètres par défaut, complétés par les mesures de la session en cours (si le jeu tourne)."""
        base = StrategyInput.model_construct(**{k: f.default for k, f in StrategyInput.model_fields.items()
                                                if f.default is not None and not f.is_required()})
        values = {k: v for k, v in base.__dict__.items() if v is not None}
        values.update(race_duration_s=6 * 3600, lap_time_s=210.0, fuel_per_lap=3.0, tank_l=90.0)
        measured = defaults_from_snapshot(latest())
        if "race_laps" in measured:
            values.pop("race_duration_s")
        values.update(measured)
        return {"values": values, "measured": sorted(measured)}

    @router.post("")
    def run(params: StrategyInput) -> dict:
        return plan(params)

    return router
