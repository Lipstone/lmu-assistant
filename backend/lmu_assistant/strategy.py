"""Planificateur de stratégie (F24) : nombre d'arrêts, carburant / énergie par relais, pneus, scénarios.

La course est simulée tour par tour avec les paramètres donnés (durée ou nombre de tours, temps au tour,
consommation, réservoir, temps perdu au stand…) :

- on rentre à la fin du tour où il ne resterait plus assez de carburant (ou d'énergie virtuelle) pour boucler
  le tour suivant avec la marge demandée ;
- à chaque arrêt on remet ce qu'il faut pour finir (au plus un plein) : le dernier plein est un « splash » ;
- temps d'arrêt = traversée des stands + ravitaillement (débit du jeu) + changement de pneus (à la suite) ;
- pneus changés quand ils atteignent leur durée de vie (ou à chaque arrêt selon le scénario) ; le temps au tour
  augmente avec l'âge des pneus (dégradation en s par tour).

Course chronométrée : à la fin du temps on termine le tour en cours (comme le leader).

Scénarios comparés : **base**, **économie** (consommation réduite d'un pourcentage contre un peu de temps au
tour) et **pneus à chaque arrêt**. Pour chacun : tours, arrêts, temps passé au stand, temps total et le détail
de chaque relais (tours, quantité à remettre, pneus).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

MAX_LAPS = 2000


class StrategyInput(BaseModel):
    race_duration_s: float | None = Field(None, ge=60, le=48 * 3600, description="course chronométrée")
    race_laps: int | None = Field(None, ge=1, le=MAX_LAPS, description="course au nombre de tours")
    lap_time_s: float = Field(..., ge=20, le=1200, description="temps au tour moyen, pneus neufs")
    fuel_per_lap: float = Field(..., gt=0, le=50, description="carburant par tour (L)")
    tank_l: float = Field(..., gt=0, le=200, description="capacité du réservoir (L)")
    start_fuel_l: float | None = Field(None, ge=0, le=200, description="carburant au départ (défaut : plein)")
    energy_per_lap: float | None = Field(None, gt=0, le=100, description="énergie virtuelle par tour (%)")
    start_energy_pct: float = Field(100.0, ge=0, le=100)
    pit_lane_s: float = Field(30.0, ge=0, le=300, description="temps perdu à traverser les stands (s)")
    refuel_l_per_s: float = Field(4.0, gt=0, le=50, description="débit du ravitaillement (L/s)")
    energy_pct_per_s: float = Field(4.0, gt=0, le=100, description="recharge d'énergie virtuelle (%/s)")
    tyre_change_s: float = Field(25.0, ge=0, le=120, description="changement des 4 pneus (s)")
    tyre_life_laps: int = Field(40, ge=1, le=500, description="tours au plus par train de pneus")
    deg_s_per_lap: float = Field(0.0, ge=-1, le=5, description="temps perdu par tour d'âge des pneus (s)")
    margin_laps: float = Field(0.0, ge=0, le=5, description="marge de sécurité en tours de carburant / énergie")
    saving_pct: float = Field(3.0, ge=0, le=30, description="scénario économie : consommation réduite de x %")
    saving_cost_s: float = Field(0.3, ge=0, le=10, description="scénario économie : temps perdu par tour (s)")

    @model_validator(mode="after")
    def _one_length(self) -> StrategyInput:
        if (self.race_duration_s is None) == (self.race_laps is None):
            raise ValueError("donner soit la durée de la course, soit le nombre de tours")
        if self.start_fuel_l is not None and self.start_fuel_l > self.tank_l:
            raise ValueError("carburant au départ supérieur au réservoir")
        return self


def _laps_left_estimate(p: StrategyInput, t: float, lap: int, lap_s: float) -> float:
    """Tours restant à faire après `lap` tours bouclés à l'instant `t` (sans compter les arrêts à venir)."""
    if p.race_laps is not None:
        return p.race_laps - lap
    left = p.race_duration_s - t
    return math.floor(left / lap_s) + 1 if left > 0 else 0


def simulate(p: StrategyInput, *, fuel_factor: float = 1.0, extra_lap_s: float = 0.0,
             tyres_every_stop: bool = False) -> dict:
    fuel_lap = p.fuel_per_lap * fuel_factor
    energy_lap = p.energy_per_lap * fuel_factor if p.energy_per_lap else None
    fuel = p.tank_l if p.start_fuel_l is None else p.start_fuel_l
    energy = p.start_energy_pct if energy_lap else None
    t = 0.0
    lap = 0
    age = 0
    stints = [{"number": 1, "start_lap": 1, "laps": 0, "fuel_added": None, "energy_added": None, "tyres": True,
               "stop_s": 0.0, "lap_time_avg_s": None, "_time": 0.0}]
    pit_total = 0.0
    margin = p.margin_laps

    def enough(f: float, e: float | None) -> bool:
        ok = f >= fuel_lap * (1 + margin) - 1e-9
        if energy_lap:
            ok = ok and e >= energy_lap * (1 + margin) - 1e-9
        return ok

    while lap < MAX_LAPS:
        if p.race_laps is not None and lap >= p.race_laps:
            break
        if p.race_duration_s is not None and lap > 0 and t >= p.race_duration_s:
            break  # drapeau à damier au passage de ligne après la fin du temps
        if not enough(fuel, energy):
            if lap == 0:
                return {"error": "pas assez de carburant ou d'énergie pour le premier tour"}
            # arrêt à la fin du tour `lap`
            base_lap = p.lap_time_s + extra_lap_s
            remaining = _laps_left_estimate(p, t, lap, base_lap)
            need_fuel = min(p.tank_l, fuel_lap * (remaining + margin)) - fuel
            add_fuel = max(0.0, min(p.tank_l - fuel, need_fuel))
            add_energy = 0.0
            if energy_lap:
                add_energy = max(0.0, min(100.0 - energy, energy_lap * (remaining + margin) - energy))
            tyres = tyres_every_stop or age + min(remaining, p.tank_l / fuel_lap) > p.tyre_life_laps
            refuel_s = max(add_fuel / p.refuel_l_per_s, add_energy / p.energy_pct_per_s if energy_lap else 0.0)
            stop_s = p.pit_lane_s + refuel_s + (p.tyre_change_s if tyres else 0.0)
            if add_fuel < fuel_lap * 0.5 and add_energy < (energy_lap or 0) * 0.5:
                return {"error": "réservoir trop petit pour un tour avec la marge demandée"}
            fuel += add_fuel
            if energy_lap:
                energy += add_energy
            if tyres:
                age = 0
            t += stop_s
            pit_total += stop_s
            stints.append({"number": len(stints) + 1, "start_lap": lap + 1, "laps": 0,
                           "fuel_added": round(add_fuel, 1), "energy_added": round(add_energy, 1) if energy_lap else None,
                           "tyres": tyres, "stop_s": round(stop_s, 1), "lap_time_avg_s": None, "_time": 0.0})
        lap_s = p.lap_time_s + extra_lap_s + p.deg_s_per_lap * age
        t += lap_s
        lap += 1
        age += 1
        fuel -= fuel_lap
        if energy_lap:
            energy -= energy_lap
        cur = stints[-1]
        cur["laps"] += 1
        cur["_time"] += lap_s
    for s in stints:
        s["lap_time_avg_s"] = round(s.pop("_time") / s["laps"], 3) if s["laps"] else None
        s["end_lap"] = s["start_lap"] + s["laps"] - 1
    stints = [s for s in stints if s["laps"]]
    return {
        "laps": lap,
        "stops": len(stints) - 1,
        "tyre_changes": sum(1 for s in stints[1:] if s["tyres"]),
        "pit_time_s": round(pit_total, 1),
        "total_time_s": round(t, 1),
        "fuel_left_l": round(fuel, 1),
        "energy_left_pct": round(energy, 1) if energy_lap else None,
        "stints": stints,
    }


def plan(p: StrategyInput) -> dict:
    scenarios = [
        ("base", "Base", "pleins complets, pneus changés quand ils arrivent en fin de vie", {}),
        ("saving", f"Économie −{p.saving_pct:g} %",
         f"consommation réduite de {p.saving_pct:g} % contre {p.saving_cost_s:g} s par tour",
         {"fuel_factor": 1 - p.saving_pct / 100, "extra_lap_s": p.saving_cost_s}),
        ("tyres", "Pneus à chaque arrêt", "pneus neufs à chaque arrêt (moins de dégradation, arrêts plus longs)",
         {"tyres_every_stop": True}),
    ]
    out = []
    for key, name, detail, kw in scenarios:
        r = simulate(p, **kw)
        r.update(key=key, name=name, detail=detail)
        out.append(r)
    base = out[0]
    for r in out:
        if "error" in r or "error" in base:
            continue
        # comparaison : en course au temps, tours en plus ; au nombre de tours, temps gagné
        r["vs_base_laps"] = r["laps"] - base["laps"]
        r["vs_base_s"] = round(r["total_time_s"] - base["total_time_s"], 1)
    valid = [r for r in out if "error" not in r]
    if valid:
        if p.race_laps is not None:
            best = min(valid, key=lambda r: r["total_time_s"])
        else:  # plus de tours, puis arrivée la plus tôt
            best = max(valid, key=lambda r: (r["laps"], -r["total_time_s"]))
        best["best"] = True
    return {"scenarios": out}


def defaults_from_snapshot(d: dict) -> dict:
    """Valeurs de départ du formulaire à partir du dernier Snapshot (dict) : mesures de la session en cours."""
    if not d or not d.get("connected"):
        return {}
    out: dict = {}
    if d.get("max_laps"):
        out["race_laps"] = d["max_laps"]
    elif d.get("session_length_s"):
        out["race_duration_s"] = round(d["session_length_s"])
    lap = (d.get("laps") or {}).get("avg_s") or d.get("best_lap_s")
    if lap:
        out["lap_time_s"] = round(lap, 3)
    fuel = (d.get("fuel") or {}).get("avg_lap")
    if fuel:
        out["fuel_per_lap"] = round(fuel, 3)
    if d.get("fuel_capacity_l"):
        out["tank_l"] = d["fuel_capacity_l"]
    energy = (d.get("energy") or {}).get("avg_lap")
    if d.get("virtual_energy_pct") is not None and energy:
        out["energy_per_lap"] = round(energy, 3)
    # Le temps perdu mesuré par F09 comprend déjà l'arrêt (ravitaillement, pneus) : il ne sert pas de
    # « traversée des stands », qui reste à régler à la main.
    stint = d.get("stint") or {}
    if stint.get("deg_s_per_lap") is not None and stint["deg_s_per_lap"] > 0:
        out["deg_s_per_lap"] = stint["deg_s_per_lap"]
    return out
