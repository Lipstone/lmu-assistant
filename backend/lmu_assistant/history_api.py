"""API de l'historique (F20) : sessions, tours et relais (F21, F22) enregistrés, lus par la page Analyse (web/analyse.html)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from . import analysis
from .history import HistoryStore


def make_history_router(store: HistoryStore) -> APIRouter:
    router = APIRouter(prefix="/api/history")

    def _session(session_id: int) -> dict:
        s = store.session(session_id)
        if s is None:
            raise HTTPException(404, "session inconnue")
        return s

    @router.get("/sessions")
    def sessions() -> list[dict]:
        return store.sessions()

    @router.get("/sessions/{session_id}")
    def session(session_id: int) -> dict:
        laps = store.laps(session_id)
        return {"session": _session(session_id), "laps": laps, "stints": analysis.stints(laps)}

    @router.delete("/sessions/{session_id}")
    def delete_session(session_id: int) -> dict:
        if not store.delete_session(session_id):
            raise HTTPException(404, "session inconnue")
        return {"deleted": session_id}

    @router.get("/laps/{lap_id}")
    def lap(lap_id: int) -> dict:
        lap = store.lap(lap_id)
        if lap is None:
            raise HTTPException(404, "tour inconnu")
        return lap

    return router
