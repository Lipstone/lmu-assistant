"""Analyse des tours enregistrés (hors course) : relais (F21) et dégradation des pneus (F22).

Les fonctions prennent la liste des tours d'une session, dans l'ordre, telle que l'historique les enregistre
(`history.py` : dicts avec `lap`, `time_s`, `valid`, `pit`, `stop`, `tyres_changed`, `fuel_used`, `wear`…).

**Relais** : un nouveau relais commence au tour où la voiture s'est arrêtée au stand (immobile ou ravitaillée,
ce tour est le tour de sortie du nouveau relais) ou quand le pilote change. Pour chaque relais : tours, durée,
pilote, rythme (moyenne, meilleur, régularité des tours propres : valides et hors stand), consommation par tour,
pneus neufs ou non et leur âge.

**Dégradation** : pente des temps au tour propres en fonction du tour dans le relais (s perdues par tour,
régression linéaire, au moins `MIN_DEG_LAPS` tours), usure par tour de chaque pneu (pente de la gomme restante),
et tours restants avant que le pneu le plus usé n'atteigne `WEAR_LIMIT`.
"""

from __future__ import annotations

import math

WEAR_LIMIT = 0.3  # gomme restante à ne pas dépasser (même seuil que l'alerte du widget Pneus)
MIN_DEG_LAPS = 3
WHEELS = ("AVG", "AVD", "ARG", "ARD")


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """(pente, ordonnée à l'origine) des moindres carrés, None avec moins de 2 points distincts."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def is_clean(lap: dict) -> bool:
    return bool(lap.get("valid")) and not lap.get("pit") and lap.get("time_s") is not None


def split_stints(laps: list[dict]) -> list[list[dict]]:
    stints: list[list[dict]] = []
    for lap in laps:
        new = not stints or lap.get("stop") or lap.get("refuel")
        if stints and not new and lap.get("driver") and stints[-1][-1].get("driver") \
                and lap["driver"] != stints[-1][-1]["driver"]:
            new = True
        if new:
            stints.append([lap])
        else:
            stints[-1].append(lap)
    return stints


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _r(v: float | None, d: int = 3) -> float | None:
    return None if v is None else round(v, d)


def summarize_stint(number: int, laps: list[dict], tyre_age_start: int | None) -> dict:
    """Résumé d'un relais (F21) et dégradation (F22). `tyre_age_start` : tours déjà faits par ces pneus
    au début du relais (None si inconnu : pneus montés avant le début de l'enregistrement)."""
    clean = [lap for lap in laps if is_clean(lap)]
    times = [lap["time_s"] for lap in clean]
    avg = _mean(times)
    stdev = math.sqrt(sum((t - avg) ** 2 for t in times) / (len(times) - 1)) if len(times) >= 2 else None
    fuel = [lap["fuel_used"] for lap in laps if lap.get("fuel_used") is not None]
    energy = [lap["energy_used"] for lap in laps if lap.get("energy_used") is not None]
    first = laps[0]
    tyres_new = bool(first.get("tyres_changed")) if number > 1 else None
    s = {
        "number": number,
        "start_lap": first["lap"],
        "end_lap": laps[-1]["lap"],
        "laps": len(laps),
        "clean_laps": len(clean),
        "driver": first.get("driver") or "",
        "duration_s": _r(sum(lap["time_s"] for lap in laps if lap.get("time_s") is not None), 1),
        "avg_s": _r(avg),
        "best_s": _r(min(times)) if times else None,
        "stdev_s": _r(stdev),
        "fuel_per_lap": _r(_mean(fuel)),
        "fuel_used": _r(sum(fuel), 2) if fuel else None,
        "energy_per_lap": _r(_mean(energy)),
        "tyres_new": tyres_new,
        "tyre_age_start": 0 if tyres_new else tyre_age_start,
        "first_3_avg_s": _r(_mean(times[:3])) if len(times) >= 3 else None,
        "last_3_avg_s": _r(_mean(times[-3:])) if len(times) >= 3 else None,
        "deg_s_per_lap": None,
        "wear_start": first.get("wear"),
        "wear_end": laps[-1].get("wear"),
        "wear_per_lap": None,
        "laps_to_wear_limit": None,
        "track_temp_avg": _r(_mean([lap["track_temp"] for lap in laps if lap.get("track_temp") is not None]), 1),
    }
    # Dégradation : temps propres en fonction du tour dans le relais
    if len(clean) >= MIN_DEG_LAPS:
        fit = linear_fit([lap["lap"] - first["lap"] for lap in clean], times)
        if fit:
            s["deg_s_per_lap"] = round(fit[0], 3)
    # Usure par tour de chaque pneu (gomme restante en fin de tour)
    wear_laps = [lap for lap in laps if lap.get("wear") and len(lap["wear"]) == 4]
    if len(wear_laps) >= 2:
        per_lap = []
        for i in range(4):
            fit = linear_fit([lap["lap"] for lap in wear_laps], [lap["wear"][i] for lap in wear_laps])
            per_lap.append(round(-fit[0], 5) if fit else None)
        s["wear_per_lap"] = per_lap
        end = wear_laps[-1]["wear"]
        left = [(end[i] - WEAR_LIMIT) / per_lap[i] for i in range(4) if per_lap[i] and per_lap[i] > 0]
        if left:
            s["laps_to_wear_limit"] = round(max(0.0, min(left)), 1)
    return s


def stints(laps: list[dict]) -> list[dict]:
    """Relais d'une session, résumés, avec l'âge des pneus suivi d'un relais à l'autre."""
    result = []
    age: int | None = None
    for n, group in enumerate(split_stints(laps), start=1):
        if (n > 1 and group[0].get("tyres_changed")) or (n == 1 and group[0]["lap"] <= 1):
            age = 0  # pneus changés, ou session suivie depuis le premier tour
        summary = summarize_stint(n, group, age)
        result.append(summary)
        age = None if summary["tyre_age_start"] is None else summary["tyre_age_start"] + len(group)
    return result


# --- Comparaison de tours (F23) -----------------------------------------------------------------------


def theoretical_best(laps: list[dict]) -> dict:
    """Meilleur tour théorique : somme des meilleurs secteurs des tours valides, et tour de chaque secteur."""
    valid = [lap for lap in laps if lap.get("valid") and lap.get("time_s") is not None]
    best_lap = min(valid, key=lambda lap: lap["time_s"]) if valid else None
    sectors = []
    for k in ("s1", "s2", "s3"):
        cands = [lap for lap in valid if lap.get(k) is not None]
        b = min(cands, key=lambda lap: lap[k]) if cands else None
        sectors.append({"time_s": b[k] if b else None, "lap": b["lap"] if b else None, "lap_id": b.get("id") if b else None})
    total = sum(s["time_s"] for s in sectors) if all(s["time_s"] is not None for s in sectors) else None
    return {
        "sectors": sectors,
        "time_s": _r(total),
        "best_lap_s": best_lap["time_s"] if best_lap else None,
        "best_lap": best_lap["lap"] if best_lap else None,
        "gain_s": _r(best_lap["time_s"] - total) if best_lap and total is not None else None,
    }


def _fill(values: list[float | None]) -> list[float | None]:
    """Complète les trous d'une trace par interpolation linéaire (pas d'extrapolation)."""
    out = list(values)
    known = [i for i, v in enumerate(out) if v is not None]
    for a, b in zip(known, known[1:]):
        for i in range(a + 1, b):
            out[i] = out[a] + (out[b] - out[a]) * (i - a) / (b - a)
    return out


def compare_laps(a: dict, b: dict) -> dict:
    """Compare le tour B au tour A : écart par secteur (B − A, positif = B plus lent), écart cumulé le long
    du tour (à chaque point de la trace) et vitesses."""
    out: dict = {"a": a["id"], "b": b["id"], "sectors": [], "delta": None, "speed_a": None, "speed_b": None}
    for k in ("s1", "s2", "s3", "time_s"):
        va, vb = a.get(k), b.get(k)
        out["sectors"].append({"a": va, "b": vb, "diff": _r(vb - va) if va is not None and vb is not None else None})
    ta, tb = (a.get("trace") or {}).get("t"), (b.get("trace") or {}).get("t")
    if ta and tb and len(ta) == len(tb):
        ta, tb = _fill(ta), _fill(tb)
        # Le relevé i est pris dès que l'on entre dans la tranche i : on le rapporte à la position i / N.
        n = len(ta)
        out["delta"] = [[round(100 * i / n, 1), _r(y - x)] for i, (x, y) in enumerate(zip(ta, tb))
                        if x is not None and y is not None]
        out["delta"].append([100.0, _r(b["time_s"] - a["time_s"]) if a.get("time_s") and b.get("time_s") else None])
        out["delta"] = [p for p in out["delta"] if p[1] is not None]
    for key, lap in (("speed_a", a), ("speed_b", b)):
        v = (lap.get("trace") or {}).get("v")
        if v:
            v = _fill(v)
            out[key] = [[round(100 * i / len(v), 1), x] for i, x in enumerate(v) if x is not None]
    return out


# --- Rapport de session (F25) -------------------------------------------------------------------------


def session_report(laps: list[dict], stint_list: list[dict] | None = None, conditions: list[dict] | None = None) -> dict:
    """Résumé d'une session : rythme, régularité, incidents, consommation, conditions."""
    stint_list = stints(laps) if stint_list is None else stint_list
    conditions = conditions or []
    clean = [lap for lap in laps if is_clean(lap)]
    times = sorted(lap["time_s"] for lap in clean)
    median = None
    if times:
        n = len(times)
        median = times[n // 2] if n % 2 else (times[n // 2 - 1] + times[n // 2]) / 2
    avg = _mean(times)
    stdev = math.sqrt(sum((t - avg) ** 2 for t in times) / (len(times) - 1)) if len(times) >= 2 else None
    best = times[0] if times else None
    fuel = [lap["fuel_used"] for lap in laps if lap.get("fuel_used") is not None]
    energy = [lap["energy_used"] for lap in laps if lap.get("energy_used") is not None]
    total_time = sum(lap["time_s"] for lap in laps if lap.get("time_s") is not None)
    th = theoretical_best(laps)
    track = [c["track_temp"] for c in conditions if c.get("track_temp") is not None] or \
            [lap["track_temp"] for lap in laps if lap.get("track_temp") is not None]
    wet_laps = sum(1 for lap in laps if (lap.get("rain") or 0) > 0.05 or (lap.get("wetness") or 0) > 0.1)
    positions = [lap["position"] for lap in laps if lap.get("position")]
    drivers: dict[str, int] = {}
    for lap in laps:
        if lap.get("driver"):
            drivers[lap["driver"]] = drivers.get(lap["driver"], 0) + 1
    return {
        "pace": {
            "laps": len(laps),
            "clean_laps": len(clean),
            "best_s": _r(best),
            "avg_s": _r(avg),
            "median_s": _r(median),
            "theoretical_s": th["time_s"],
            "gap_avg_best_s": _r(avg - best) if avg is not None and best is not None else None,
            "total_time_s": _r(total_time, 1),
        },
        "consistency": {
            "stdev_s": _r(stdev),
            # part des tours propres à moins de 0,5 s / 1 s de la médiane
            "within_05_pct": round(100 * sum(abs(t - median) <= 0.5 for t in times) / len(times)) if times else None,
            "within_1_pct": round(100 * sum(abs(t - median) <= 1.0 for t in times) / len(times)) if times else None,
        },
        "incidents": {
            "invalid_laps": sum(1 for lap in laps if lap.get("invalid")),
            "impacts": sum(lap.get("impacts") or 0 for lap in laps),
            "impact_laps": [lap["lap"] for lap in laps if lap.get("impacts")],
            "pit_stops": max(0, len(stint_list) - 1),
            "tyre_changes": sum(1 for s in stint_list[1:] if s.get("tyres_new")),
        },
        "consumption": {
            "fuel_per_lap": _r(_mean(fuel)),
            "fuel_used": _r(sum(fuel), 1) if fuel else None,
            "energy_per_lap": _r(_mean(energy)),
        },
        "conditions": {
            "track_temp_min": _r(min(track), 1) if track else None,
            "track_temp_max": _r(max(track), 1) if track else None,
            "wet_laps": wet_laps,
        },
        "positions": {"start": positions[0] if positions else None, "end": positions[-1] if positions else None,
                      "best": min(positions) if positions else None},
        "drivers": drivers,
        "stints": len(stint_list),
    }
