"""API de configuration : GET/PUT /api/config."""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter

from .config import AppConfig, ConfigStore


def make_config_router(
    store: ConfigStore, on_change: Callable[[AppConfig], Awaitable[None]] | None = None
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/config")
    async def get_config() -> AppConfig:
        return store.config

    @router.put("/config")
    async def put_config(config: AppConfig) -> AppConfig:
        # Pydantic valide le corps (422 si invalide) ; on enregistre puis on prévient les clients.
        store.save(config)
        if on_change is not None:
            await on_change(config)
        return config

    return router
