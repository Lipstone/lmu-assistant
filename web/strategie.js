// Planificateur de stratégie (F24) : simulation côté serveur (backend/lmu_assistant/strategy.py).
const $ = (id) => document.getElementById(id);
const NUMS = ["race_laps", "deg_s_per_lap", "fuel_per_lap", "tank_l", "start_fuel_l", "energy_per_lap", "margin_laps",
  "pit_lane_s", "refuel_l_per_s", "energy_pct_per_s", "tyre_change_s", "tyre_life_laps", "saving_pct", "saving_cost_s"];
let result = null;
let selected = null;

function fmtLap(s) {
  if (s == null) return "–";
  const ms = Math.round(s * 1000); // arrondi d'abord : 59,9996 s donne 1:00.000, pas 0:60.000
  const m = Math.floor(ms / 60000);
  return `${m}:${((ms - m * 60000) / 1000).toFixed(3).padStart(6, "0")}`;
}
const fmtDur = (s) => {
  if (s == null) return "–";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
};
function parseLap(t) {
  const m = String(t).trim().match(/^(?:(\d+):)?(\d+(?:[.,]\d+)?)$/);
  return m ? (+m[1] || 0) * 60 + parseFloat(m[2].replace(",", ".")) : NaN;
}
function parseDuration(t) {
  const m = String(t).trim().match(/^(\d+)(?::(\d{1,2}))?$/);
  return m ? (+m[1]) * 3600 + (+m[2] || 0) * 60 : NaN;
}

function fill(v) {
  for (const k of NUMS) $(k).value = v[k] ?? "";
  $("lap_time").value = v.lap_time_s ? fmtLap(v.lap_time_s) : "";
  const laps = v.race_laps != null;
  document.querySelector(`input[name=kind][value=${laps ? "laps" : "time"}]`).checked = true;
  if (v.race_duration_s) $("duration").value = `${Math.floor(v.race_duration_s / 3600)}:${String(Math.round((v.race_duration_s % 3600) / 60)).padStart(2, "0")}`;
}

function collect() {
  const p = {};
  for (const k of NUMS) {
    const x = parseFloat($(k).value);
    if (Number.isFinite(x)) p[k] = k === "race_laps" || k === "tyre_life_laps" ? Math.round(x) : x;
  }
  const laps = document.querySelector("input[name=kind]:checked").value === "laps";
  if (laps) delete p.race_duration_s;
  else { delete p.race_laps; p.race_duration_s = parseDuration($("duration").value); }
  p.lap_time_s = parseLap($("lap_time").value);
  return p;
}

async function compute(e) {
  e?.preventDefault();
  const r = await fetch("/api/strategy", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(collect()) });
  const body = await r.json();
  if (!r.ok) {
    $("msg").textContent = "Refusé : " + (Array.isArray(body.detail) ? body.detail.map((d) => `${d.loc.slice(1).join(".") || "paramètres"} : ${d.msg}`).join(" ; ") : body.detail);
    $("msg").className = "error";
    return;
  }
  $("msg").textContent = "";
  result = body;
  if (!selected || !result.scenarios.some((s) => s.key === selected)) selected = (result.scenarios.find((s) => s.best) || result.scenarios[0]).key;
  render();
}

const sign = (v) => (v > 0 ? "+" : v < 0 ? "−" : "±");

function render() {
  const laps = document.querySelector("input[name=kind]:checked").value === "laps";
  $("scenarios").innerHTML = result.scenarios.map((s) => {
    if (s.error) return `<div class="scenario"><h3>${s.name}</h3><p class="error">${s.error}</p></div>`;
    const vs = s.key === "base" ? "" : laps
      ? `${sign(s.vs_base_s)}${fmtDur(Math.abs(s.vs_base_s))} vs base`
      : `${sign(s.vs_base_laps)}${Math.abs(s.vs_base_laps)} tour${Math.abs(s.vs_base_laps) > 1 ? "s" : ""} · ${sign(Math.round(s.vs_base_s))}${Math.abs(s.vs_base_s).toFixed(0)} s vs base`;
    return `<button type="button" class="scenario ${s.key === selected ? "selected" : ""}" data-key="${s.key}">` +
      `<h3>${s.name}${s.best ? ' <span class="badge">meilleur</span>' : ""}</h3><p class="hint">${s.detail}</p>` +
      `<div class="big">${s.stops} arrêt${s.stops > 1 ? "s" : ""}</div>` +
      `<dl><dt>Tours</dt><dd>${s.laps}</dd><dt>Temps total</dt><dd>${fmtDur(s.total_time_s)}</dd>` +
      `<dt>Au stand</dt><dd>${fmtDur(s.pit_time_s)}</dd><dt>Pneus changés</dt><dd>${s.tyre_changes}×</dd>` +
      `<dt>Écart</dt><dd>${vs || "référence"}</dd></dl></button>`;
  }).join("");
  document.querySelectorAll(".scenario[data-key]").forEach((b) => b.addEventListener("click", () => { selected = b.dataset.key; render(); }));
  const s = result.scenarios.find((x) => x.key === selected);
  $("plan-title").textContent = `Plan des relais · ${s?.name || ""}`;
  if (!s || s.error) { $("plan").innerHTML = ""; return; }
  const energy = s.stints.some((x) => x.energy_added != null);
  $("plan").innerHTML = `<tr><th>Relais</th><th>Tours</th><th>Nombre</th><th>Arrêt avant</th><th>Carburant remis</th>${energy ? "<th>Énergie remise</th>" : ""}<th>Pneus</th><th>Temps moyen</th></tr>` +
    s.stints.map((x) => `<tr><td>${x.number}</td><td>T${x.start_lap}–T${x.end_lap}</td><td>${x.laps}</td>` +
      `<td>${x.number === 1 ? "départ" : x.stop_s.toFixed(1) + " s"}</td><td>${x.fuel_added == null ? "–" : x.fuel_added.toFixed(1) + " L"}</td>` +
      `${energy ? `<td>${x.energy_added == null ? "–" : x.energy_added.toFixed(1) + " %"}</td>` : ""}` +
      `<td>${x.number === 1 ? "" : x.tyres ? "neufs" : "gardés"}</td><td>${fmtLap(x.lap_time_avg_s)}</td></tr>`).join("");
}

async function loadDefaults() {
  const d = await (await fetch("/api/strategy/defaults")).json();
  fill(d.values);
  $("msg").className = "hint";
  $("msg").textContent = d.measured.length ? `Mesuré sur la session en cours : ${d.measured.join(", ")}` : "Valeurs par défaut (aucune session en cours)";
  compute();
}

$("form").addEventListener("submit", compute);
$("form").addEventListener("change", () => compute());
$("reload").addEventListener("click", loadDefaults);
loadDefaults();
