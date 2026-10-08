"""API de l'historique (F20) : sessions, tours et relais (F21, F22) enregistrés, lus par la page Analyse (web/analyse.html)."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from . import analysis
from .history import HistoryStore


# Colonnes des exports CSV (F27) : (en-tête, clé ou fonction)
WHEELS = ("avg", "avd", "arg", "ard")
LAP_CSV = [("tour", "lap"), ("temps_s", "time_s"), ("s1", "s1"), ("s2", "s2"), ("s3", "s3"), ("valide", "valid"),
           ("stand", "pit"), ("invalide", "invalid"), ("arret", "stop"), ("plein", "refuel"),
           ("pneus_changes", "tyres_changed"), ("carburant_debut_l", "fuel_start"), ("carburant_fin_l", "fuel_end"),
           ("carburant_tour_l", "fuel_used"), ("energie_debut_pct", "energy_start"), ("energie_fin_pct", "energy_end"),
           ("energie_tour_pct", "energy_used")] \
    + [(f"usure_{w}", (lambda i: lambda r: (r.get("wear") or [None] * 4)[i])(i)) for i, w in enumerate(WHEELS)] \
    + [(f"temp_pneu_{w}", (lambda i: lambda r: (r.get("tyre_temp") or [None] * 4)[i])(i)) for i, w in enumerate(WHEELS)] \
    + [(f"pression_{w}_kpa", (lambda i: lambda r: (r.get("pressure") or [None] * 4)[i])(i)) for i, w in enumerate(WHEELS)] \
    + [("air_c", "air_temp"), ("piste_c", "track_temp"), ("pluie", "rain"), ("piste_mouillee", "wetness"),
       ("grip", "grip"), ("position", "position"), ("pilote", "driver"), ("chocs", "impacts"),
       ("temps_session_s", "session_time_s"), ("enregistre_le", "recorded_at")]
STINT_CSV = [("relais", "number"), ("premier_tour", "start_lap"), ("dernier_tour", "end_lap"), ("tours", "laps"),
             ("tours_propres", "clean_laps"), ("pilote", "driver"), ("duree_s", "duration_s"), ("moyenne_s", "avg_s"),
             ("meilleur_s", "best_s"), ("regularite_s", "stdev_s"), ("carburant_tour_l", "fuel_per_lap"),
             ("carburant_total_l", "fuel_used"), ("energie_tour_pct", "energy_per_lap"), ("pneus_neufs", "tyres_new"),
             ("age_pneus_debut", "tyre_age_start"), ("degradation_s_tour", "deg_s_per_lap"),
             ("tours_avant_30pct", "laps_to_wear_limit")]


def to_csv(rows: list[dict], columns: list, excel: bool) -> str:
    """CSV ; `excel` (défaut) : séparateur « ; » et virgule décimale pour Excel en français, sinon « , » et point."""
    out = io.StringIO()
    w = csv.writer(out, delimiter=";" if excel else ",", lineterminator="\r\n")
    w.writerow([c[0] for c in columns])
    for r in rows:
        line = []
        for _, key in columns:
            v = key(r) if callable(key) else r.get(key)
            if isinstance(v, bool):
                v = int(v)
            if isinstance(v, float) and excel:
                v = repr(v).replace(".", ",")
            line.append("" if v is None else v)
        w.writerow(line)
    return ("\ufeff" if excel else "") + out.getvalue()


def make_history_router(store: HistoryStore, notes=None) -> APIRouter:
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
        return _full(session_id)

    def _full(session_id: int) -> dict:
        session = _session(session_id)
        laps = store.laps(session_id)
        stints = analysis.stints(laps)
        conditions = store.conditions(session_id)
        return {"session": session, "laps": laps, "stints": stints,
                "theoretical": analysis.theoretical_best(laps), "conditions": conditions,
                "report": analysis.session_report(laps, stints, conditions)}

    def _filename(session_id: int, ext: str) -> str:
        s = _session(session_id)
        day = (s.get("started_at") or "")[:10]
        name = "_".join(x for x in (day, s.get("session"), s.get("track"), s.get("car")) if x)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:120] or f"session_{session_id}"
        return f"{safe}.{ext}"

    def _download(content: str, media: str, filename: str) -> Response:
        return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @router.get("/sessions/{session_id}/export.json")
    def export_json(session_id: int) -> Response:
        """Export complet (F27) : session, tours (avec traces), relais, rapport, conditions, notes."""
        data = _full(session_id)
        data["laps"] = store.laps(session_id, with_trace=True)
        if notes is not None:
            data["notes"] = notes.list(session_id=session_id)
        body = json.dumps(data, ensure_ascii=False, indent=1)
        return _download(body, "application/json", _filename(session_id, "json"))

    @router.get("/sessions/{session_id}/laps.csv")
    def export_laps(session_id: int, excel: bool = True) -> Response:
        _session(session_id)
        body = to_csv(store.laps(session_id), LAP_CSV, excel)
        return _download(body, "text/csv; charset=utf-8", _filename(session_id, "tours.csv"))

    @router.get("/sessions/{session_id}/stints.csv")
    def export_stints(session_id: int, excel: bool = True) -> Response:
        _session(session_id)
        body = to_csv(analysis.stints(store.laps(session_id)), STINT_CSV, excel)
        return _download(body, "text/csv; charset=utf-8", _filename(session_id, "relais.csv"))

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

    @router.get("/compare")
    def compare(a: int, b: int) -> dict:
        """Comparaison de deux tours (F23) : tour B par rapport au tour A."""
        la, lb = store.lap(a), store.lap(b)
        if la is None or lb is None:
            raise HTTPException(404, "tour inconnu")
        return analysis.compare_laps(la, lb)

    return router
