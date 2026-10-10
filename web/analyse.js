// Page Analyse (hors course) : historique des tours enregistré par le serveur (F20, backend/lmu_assistant/history.py).
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function fmtLap(s) {
  if (s == null) return "–";
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(3).padStart(6, "0")}`;
}
const fmtSec = (s) => (s == null ? "–" : s.toFixed(3));
const fmt = (v, d = 1, unit = "") => (v == null ? "–" : `${v.toFixed(d)}${unit}`);
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "");
const avg = (xs) => (xs && xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

let current = null; // { session, laps, … } de la session affichée
let sessionList = []; // toutes les sessions (la plus récente d'abord)
let shownId = null; // session affichée
const checked = new Set(); // sessions cochées (ids)
let lastClicked = null; // pour Maj + clic (plage)
let compareIds = []; // sessions de la comparaison affichée

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

const sessionLabel = (s) => `${fmtDate(s.started_at)} · ${s.session || "?"} · ${s.track || "?"} · ${s.car || "?"}`;

function visibleSessions() {
  const words = $("session-filter").value.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return sessionList;
  return sessionList.filter((s) => {
    const hay = [fmtDate(s.started_at), s.session, s.track, s.car, s.car_class, s.driver].join(" ").toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

function renderSessionList() {
  const vis = visibleSessions();
  const allChecked = vis.length && vis.every((s) => checked.has(s.id));
  $("sessions").innerHTML = `<thead><tr><th class="check"><input type="checkbox" id="check-all" title="Cocher toutes les sessions affichées" ${allChecked ? "checked" : ""} ${vis.length ? "" : "disabled"}></th>` +
    `<th class="l">Date</th><th class="l">Type</th><th class="l">Circuit</th><th class="l">Voiture</th><th class="l">Pilote</th><th>Tours</th><th>Valides</th><th>Meilleur tour</th></tr></thead><tbody>` +
    (vis.length ? vis.map((s) => `<tr data-id="${s.id}" class="${s.id === shownId ? "shown" : ""} ${checked.has(s.id) ? "checked" : ""}">` +
      `<td class="check"><input type="checkbox" data-check="${s.id}" ${checked.has(s.id) ? "checked" : ""} aria-label="Cocher"></td>` +
      `<td class="l">${esc(fmtDate(s.started_at))}</td><td class="l">${esc(s.session)}</td><td class="l">${esc(s.track)}</td>` +
      `<td class="l">${esc(s.car)}</td><td class="l">${esc(s.driver)}</td><td>${s.laps}</td><td>${s.valid_laps ?? 0}</td><td>${fmtLap(s.best_s)}</td></tr>`).join("")
      : `<tr><td colspan="9" class="muted">${sessionList.length ? "Aucune session ne correspond au filtre." : "Aucune session enregistrée. Les tours sont enregistrés automatiquement pendant que l'on roule (lecture du jeu)."}</td></tr>`) +
    "</tbody>";
  $("session-count").textContent = sessionList.length ? `${vis.length === sessionList.length ? "" : vis.length + " / "}${sessionList.length} session${sessionList.length > 1 ? "s" : ""}` : "";
  renderSelectionBar();
}

function renderSelectionBar() {
  const n = checked.size;
  $("session-bar").hidden = !n;
  $("sel-count").textContent = `${n} session${n > 1 ? "s" : ""} cochée${n > 1 ? "s" : ""}`;
  $("compare-btn").disabled = n < 2 || n > SERIES.length;
  $("compare-btn").title = n > SERIES.length ? `Comparer au plus ${SERIES.length} sessions` : "Comparer les sessions cochées";
  $("delete-btn").textContent = `Supprimer (${n})`;
}

async function loadSessions() {
  sessionList = await getJSON("/api/history/sessions");
  const ids = new Set(sessionList.map((s) => s.id));
  for (const id of [...checked]) if (!ids.has(id)) checked.delete(id);
  if (shownId != null && !ids.has(shownId)) shownId = null;
  if (shownId == null && sessionList.length) shownId = sessionList[0].id;
  renderSessionList();
  return sessionList;
}

async function loadSession() {
  if (shownId == null) {
    current = null;
    $("current-section").hidden = true;
    renderAll();
    return;
  }
  current = await getJSON(`/api/history/sessions/${shownId}`);
  const s = current.session;
  $("current-section").hidden = false;
  $("current-title").textContent = `Session affichée : ${sessionLabel(s)}`;
  $("session-info").textContent = `${s.driver || "?"} · ${s.car_class || ""} · du ${fmtDate(s.started_at)} au ${fmtDate(s.ended_at)} · source ${s.source}`;
  renderAll();
}

$("sessions").addEventListener("click", (e) => {
  if (e.target.id === "check-all") {
    const vis = visibleSessions();
    for (const s of vis) e.target.checked ? checked.add(s.id) : checked.delete(s.id);
    renderSessionList();
    return;
  }
  const row = e.target.closest("tr[data-id]");
  if (!row) return;
  const id = Number(row.dataset.id);
  if (e.target.dataset.check != null) {
    // Maj + clic : applique l'état de la case à toute la plage depuis le dernier clic
    const vis = visibleSessions().map((s) => s.id);
    const on = e.target.checked;
    const i = vis.indexOf(id), j = vis.indexOf(lastClicked);
    const range = e.shiftKey && j >= 0 ? vis.slice(Math.min(i, j), Math.max(i, j) + 1) : [id];
    for (const x of range) on ? checked.add(x) : checked.delete(x);
    lastClicked = id;
    renderSessionList();
    return;
  }
  if (id !== shownId) {
    shownId = id;
    renderSessionList();
    loadSession();
  }
});
$("session-filter").addEventListener("input", renderSessionList);
$("clear-btn").addEventListener("click", () => { checked.clear(); renderSessionList(); });

async function deleteSessions(ids) {
  const n = ids.length;
  const what = n === 1 ? `la session « ${sessionLabel(sessionList.find((s) => s.id === ids[0]) || {})} »` : `ces ${n} sessions`;
  if (!n || !confirm(`Supprimer définitivement ${what} et leurs tours de l'historique ?`)) return;
  await getJSON("/api/history/sessions/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });
  for (const id of ids) checked.delete(id);
  if (compareIds.some((id) => ids.includes(id))) closeComparison();
  await loadSessions();
  await loadSession();
}
$("delete-btn").addEventListener("click", () => deleteSessions([...checked]));

// Sections de la page : chaque fonctionnalité ajoute la sienne.
const sections = [];

function renderAll() {
  for (const render of sections) render(current);
}

// F27 : liens d'export de la session affichée.
function renderExports(cur) {
  const id = cur?.session?.id;
  $("exports").hidden = !id;
  if (!id) return;
  const q = $("exp-intl").checked ? "?excel=false" : "";
  $("exp-json").href = `/api/history/sessions/${id}/export.json`;
  $("exp-laps").href = `/api/history/sessions/${id}/laps.csv${q}`;
  $("exp-stints").href = `/api/history/sessions/${id}/stints.csv${q}`;
}
sections.push(renderExports);
$("exp-intl").addEventListener("change", () => renderExports(current));

// F25 : rapport de session (calculé par le serveur, analysis.session_report).
function renderReport(cur) {
  const r = cur?.report;
  if (!r || !cur.laps.length) { $("report").innerHTML = '<p class="hint">Pas encore de tour dans cette session.</p>'; return; }
  const p = r.pace, c = r.consistency, i = r.incidents, k = r.consumption, w = r.conditions, pos = r.positions;
  const card = (title, big, rows) => `<div class="report-card"><h3>${title}</h3><div class="big">${big}</div><dl>` +
    rows.filter(Boolean).map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join("") + "</dl></div>";
  const drivers = Object.entries(r.drivers).map(([d, n]) => `${esc(d)} (${n})`).join(", ");
  $("report").innerHTML =
    card("Rythme", fmtLap(p.best_s), [["Moyenne", fmtLap(p.avg_s)], ["Médiane", fmtLap(p.median_s)],
      ["Théorique", fmtLap(p.theoretical_s)], ["Moyenne − meilleur", p.gap_avg_best_s == null ? "–" : "+" + p.gap_avg_best_s.toFixed(3)],
      ["Tours", `${p.laps} (${p.clean_laps} propres)`], ["Temps roulé", fmtDur(p.total_time_s)]]) +
    card("Régularité", c.stdev_s == null ? "–" : `±${c.stdev_s.toFixed(2)} s`, [["À 0,5 s de la médiane", c.within_05_pct == null ? "–" : c.within_05_pct + " %"],
      ["À 1 s de la médiane", c.within_1_pct == null ? "–" : c.within_1_pct + " %"]]) +
    card("Incidents", `${i.invalid_laps + i.impacts}`, [["Tours invalidés", i.invalid_laps], ["Chocs", i.impacts + (i.impact_laps.length ? ` (T${i.impact_laps.join(", T")})` : "")],
      ["Arrêts au stand", i.pit_stops], ["Trains de pneus", i.tyre_changes]]) +
    card("Consommation", k.energy_per_lap != null ? `${k.energy_per_lap.toFixed(2)} %/t` : fmt(k.fuel_per_lap, 2, " L/t"),
      [["Carburant / tour", fmt(k.fuel_per_lap, 2, " L")], ["Carburant total", fmt(k.fuel_used, 1, " L")], k.energy_per_lap != null && ["Énergie / tour", fmt(k.energy_per_lap, 2, " %")]]) +
    card("Conditions", w.track_temp_min == null ? "–" : `${w.track_temp_min.toFixed(0)}–${w.track_temp_max.toFixed(0)} °C`,
      [["Piste", w.track_temp_min == null ? "–" : `${w.track_temp_min.toFixed(1)} → ${w.track_temp_max.toFixed(1)} °C`], ["Tours sous la pluie / mouillés", w.wet_laps]]) +
    card("Course", pos.end ? `P${pos.end}` : "–", [["Départ", pos.start ? "P" + pos.start : "–"], ["Meilleure position", pos.best ? "P" + pos.best : "–"],
      ["Relais", r.stints], ["Pilotes", drivers || "–"]]);
}
sections.push(renderReport);

// F20 : tableau des tours.
function renderLaps(cur) {
  const laps = cur?.laps || [];
  const valid = laps.filter((l) => l.valid && l.time_s != null);
  const best = valid.length ? Math.min(...valid.map((l) => l.time_s)) : null;
  const bestSector = [1, 2, 3].map((k) => {
    const xs = valid.map((l) => l[`s${k}`]).filter((x) => x != null);
    return xs.length ? Math.min(...xs) : null;
  });
  const head = "<tr><th>Tour</th><th>Temps</th><th>Écart</th><th>S1</th><th>S2</th><th>S3</th><th>Carb.</th><th>Énergie</th><th>Usure</th><th>Piste</th><th>Pluie</th><th>Pos.</th><th>Pilote</th><th></th></tr>";
  $("laps").innerHTML = head + laps
    .map((l) => {
      const tags = [l.stop ? "arrêt" : l.pit ? "stand" : "", l.refuel ? "plein" : "", l.tyres_changed ? "pneus" : "",
        l.invalid ? "invalide" : "", !l.valid && !l.pit && !l.invalid ? "partiel" : "", l.impacts ? `choc${l.impacts > 1 ? "s" : ""}` : ""].filter(Boolean);
      const sec = (k) => {
        const v = l[`s${k}`];
        const cls = l.valid && v != null && v === bestSector[k - 1] ? "purple" : "";
        return `<td class="${cls}">${fmtSec(v)}</td>`;
      };
      const wear = avg(l.wear);
      return `<tr class="${l.valid ? "" : "excluded"}"><td>${l.lap}</td>` +
        `<td class="${l.valid && l.time_s === best ? "faster" : ""}">${fmtLap(l.time_s)}</td>` +
        `<td>${l.valid && best != null && l.time_s != null ? (l.time_s === best ? "meilleur" : "+" + (l.time_s - best).toFixed(3)) : ""}</td>` +
        sec(1) + sec(2) + sec(3) +
        `<td>${fmt(l.fuel_used, 2, " L")}</td><td>${fmt(l.energy_used, 2, " %")}</td>` +
        `<td>${wear == null ? "–" : Math.round(wear * 100) + " %"}</td>` +
        `<td>${fmt(l.track_temp, 1, " °C")}</td><td>${l.rain == null ? "–" : Math.round(l.rain * 100) + " %"}</td>` +
        `<td>${l.position ? "P" + l.position : "–"}</td><td>${esc(l.driver)}</td>` +
        `<td class="tags">${tags.map((t) => `<span>${t}</span>`).join("")}</td></tr>`;
    })
    .join("");
  if (!laps.length) $("laps").innerHTML = head + `<tr><td colspan="14" class="muted">Aucun tour.</td></tr>`;
}
sections.push(renderLaps);

// --- Graphiques SVG (lignes, un seul axe des y, survol avec repère et infobulle) -------------------------
// Couleurs catégorielles fixes (palette validée sur le fond sombre), attribuées dans l'ordre, jamais recyclées.
const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
const svgNS = "http://www.w3.org/2000/svg";

function niceTicks(lo, hi, n = 4) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const step0 = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= step0);
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

// series : [{ name, color, points: [[x, y], …], dashed, noHover }]
function lineChart(el, series, { xFmt = (x) => x, yFmt = (y) => y, xLabel = "", height = 220, intX = true, xTicks = null } = {}) {
  el.innerHTML = "";
  const pts = series.flatMap((s) => s.points);
  if (!pts.length) { el.innerHTML = '<p class="hint">Pas assez de tours.</p>'; return; }
  const W = Math.max(320, el.clientWidth || 600), H = height, m = { l: 62, r: 24, t: 10, b: 30 };
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  let [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  if (x0 === x1) x1 = x0 + 1;
  const pad = (Math.max(...ys) - Math.min(...ys)) * 0.08 || 1;
  const yt = niceTicks(Math.min(...ys) - pad, Math.max(...ys) + pad);
  const [y0, y1] = [Math.min(yt[0], Math.min(...ys)), Math.max(yt[yt.length - 1], Math.max(...ys))];
  const X = (x) => m.l + ((x - x0) / (x1 - x0)) * (W - m.l - m.r);
  const Y = (y) => m.t + (1 - (y - y0) / (y1 - y0)) * (H - m.t - m.b);
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  const add = (tag, attrs, parent = svg) => {
    const e = document.createElementNS(svgNS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    parent.appendChild(e);
    return e;
  };
  for (const v of yt) {
    add("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: "grid" });
    add("text", { x: m.l - 6, y: Y(v) + 4, class: "tick", "text-anchor": "end" }).textContent = yFmt(v);
  }
  for (const v of (xTicks ? xTicks(x0, x1) : niceTicks(x0, x1, 6)).filter((v) => !intX || Number.isInteger(v))) {
    add("text", { x: X(v), y: H - m.b + 16, class: "tick", "text-anchor": "middle" }).textContent = xFmt(v);
  }
  if (xLabel) add("text", { x: W - m.r, y: H - 2, class: "tick", "text-anchor": "end" }).textContent = xLabel;
  for (const s of series) {
    if (!s.points.length) continue;
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
    add("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-dasharray": s.dashed ? "5 4" : "none",
      "stroke-linejoin": "round", "stroke-linecap": "round" });
    if (!s.dashed && s.points.length <= 60)
      for (const p of s.points) add("circle", { cx: X(p[0]), cy: Y(p[1]), r: 3, fill: s.color, stroke: "#1a1d24", "stroke-width": 2 });
  }
  // Survol : repère vertical au x le plus proche et valeurs de chaque série
  const cross = add("line", { y1: m.t, y2: H - m.b, class: "cross", visibility: "hidden" });
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.hidden = true;
  el.style.position = "relative";
  el.append(svg, tip);
  const allX = [...new Set(series.filter((s) => !s.noHover).flatMap((s) => s.points.map((p) => p[0])))].sort((a, b) => a - b);
  svg.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    if (!allX.length) return;
    const x = allX.reduce((b, v) => (Math.abs(X(v) - px) < Math.abs(X(b) - px) ? v : b), allX[0]);
    cross.setAttribute("x1", X(x)); cross.setAttribute("x2", X(x)); cross.setAttribute("visibility", "visible");
    const rows = series.filter((s) => !s.noHover).map((s) => [s, s.points.find((p) => p[0] === x)]).filter(([, p]) => p);
    tip.innerHTML = `<b>${esc(xFmt(x))}</b>` + rows.map(([s, p]) => `<div><i style="background:${s.color}"></i>${esc(s.name)} <span>${esc(yFmt(p[1]))}</span></div>`).join("");
    tip.hidden = false;
    const left = (X(x) / W) * r.width;
    tip.style.left = `${Math.min(left + 12, r.width - tip.offsetWidth - 4)}px`;
    tip.style.top = "8px";
  });
  svg.addEventListener("pointerleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
  if (series.filter((s) => !s.dashed).length >= 2) {
    const legend = document.createElement("div");
    legend.className = "legend";
    legend.innerHTML = series.filter((s) => !s.dashed).map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("");
    el.append(legend);
  }
}

// --- F21 : relais ------------------------------------------------------------------------------------------
const WHEEL_NAMES = ["AVG", "AVD", "ARG", "ARD"];
const fmtDur = (s) => {
  if (s == null) return "–";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
};
const fmtDeg = (v) => (v == null ? "–" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)} s/t`);

function renderStints(cur) {
  const st = cur?.stints || [];
  const head = "<tr><th>Relais</th><th>Tours</th><th>Pilote</th><th>Durée</th><th>Moyenne</th><th>Meilleur</th><th>Régularité</th><th>Carb./tour</th><th>Énergie/tour</th><th>Pneus</th><th>Dégradation</th><th>Usure max/tour</th><th>Gomme fin</th></tr>";
  $("stints").innerHTML = head + (st.length ? st.map((s) => {
    const wpl = s.wear_per_lap ? Math.max(...s.wear_per_lap.filter((w) => w != null)) : null;
    const wend = s.wear_end ? Math.min(...s.wear_end) : null;
    const tyres = s.tyres_new || s.tyre_age_start === 0 ? "neufs" : s.tyre_age_start == null ? "?" : `${s.tyre_age_start} t`;
    return `<tr><td><i class="dot" style="background:${SERIES[(s.number - 1) % SERIES.length]}"></i>${s.number}</td>` +
      `<td>${s.laps} (T${s.start_lap}–T${s.end_lap})</td><td>${esc(s.driver)}</td><td>${fmtDur(s.duration_s)}</td>` +
      `<td>${fmtLap(s.avg_s)}</td><td>${fmtLap(s.best_s)}</td><td>${s.stdev_s == null ? "–" : "±" + s.stdev_s.toFixed(2) + " s"}</td>` +
      `<td>${fmt(s.fuel_per_lap, 2, " L")}</td><td>${fmt(s.energy_per_lap, 2, " %")}</td><td>${tyres}</td>` +
      `<td>${fmtDeg(s.deg_s_per_lap)}</td><td>${wpl == null ? "–" : (wpl * 100).toFixed(2) + " %"}</td>` +
      `<td>${wend == null ? "–" : Math.round(wend * 100) + " %"}</td></tr>`;
  }).join("") : `<tr><td colspan="13" class="muted">Aucun relais.</td></tr>`);
}
sections.push(renderStints);

// --- F22 : dégradation des pneus ---------------------------------------------------------------------------
function renderDegradation(cur) {
  const st = cur?.stints || [];
  const sel = $("deg-stint");
  const prev = sel.value;
  sel.innerHTML = `<option value="all">Tous</option>` + st.map((s) => `<option value="${s.number}">Relais ${s.number}</option>`).join("");
  sel.value = [...sel.options].some((o) => o.value === prev) ? prev : st.length ? String(st[st.length - 1].number) : "all";
  const chosen = sel.value === "all" ? st : st.filter((s) => String(s.number) === sel.value);
  const laps = cur?.laps || [];
  const lapsOf = (s) => laps.filter((l) => l.lap >= s.start_lap && l.lap <= s.end_lap);
  const series = [];
  for (const s of chosen) {
    const color = SERIES[(s.number - 1) % SERIES.length];
    const clean = lapsOf(s).filter((l) => l.valid && !l.pit && l.time_s != null);
    const points = clean.map((l) => [l.lap - s.start_lap + 1, l.time_s]);
    series.push({ name: `Relais ${s.number}`, color, points });
    if (s.deg_s_per_lap != null && points.length >= 2) {
      // tendance : droite de régression (pente = dégradation), sur l'étendue des tours propres
      const n = points.length, mx = points.reduce((a, p) => a + p[0], 0) / n, my = points.reduce((a, p) => a + p[1], 0) / n;
      const b = my - s.deg_s_per_lap * mx;
      const xa = points[0][0], xb = points[n - 1][0];
      series.push({ name: `tendance ${s.number}`, color, dashed: true, noHover: true, points: [[xa, b + s.deg_s_per_lap * xa], [xb, b + s.deg_s_per_lap * xb]] });
    }
  }
  lineChart($("deg-times"), series, { xFmt: (x) => `${x}`, yFmt: (y) => fmtLap(y).slice(0, -1), xLabel: "tour du relais" });
  // Usure : un relais (le choisi, ou le dernier si « Tous »)
  const one = sel.value === "all" ? st[st.length - 1] : chosen[0];
  const wl = one ? lapsOf(one).filter((l) => l.wear) : [];
  lineChart($("deg-wear"), WHEEL_NAMES.map((w, i) => ({ name: w, color: SERIES[i], points: wl.map((l) => [l.lap - one.start_lap + 1, l.wear[i] * 100]) })),
    { yFmt: (y) => `${Math.round(y)} %`, xLabel: one ? `tour du relais ${one.number}` : "" });
  $("deg-summary").textContent = one
    ? `Relais ${one.number} : ${fmtDeg(one.deg_s_per_lap)} sur ${one.clean_laps} tours propres` +
      (one.first_3_avg_s && one.last_3_avg_s ? ` (3 premiers ${fmtLap(one.first_3_avg_s)}, 3 derniers ${fmtLap(one.last_3_avg_s)})` : "") +
      (one.wear_per_lap ? ` · usure par tour ${one.wear_per_lap.map((w, i) => `${WHEEL_NAMES[i]} ${w == null ? "–" : (w * 100).toFixed(2) + " %"}`).join(", ")}` : "") +
      (one.laps_to_wear_limit != null ? ` · ${Math.round(one.laps_to_wear_limit)} tours avant 30 % de gomme` : "")
    : "";
}
sections.push(renderDegradation);
$("deg-stint").addEventListener("change", () => renderDegradation(current));

// --- F23 : comparaison de tours ----------------------------------------------------------------------------
const fmtDiff = (v, d = 3) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(d)}`);
const diffClass = (v) => (v == null || v === 0 ? "" : v < 0 ? "faster" : "slower");

function renderCompare(cur) {
  const laps = (cur?.laps || []).filter((l) => l.time_s != null);
  const opts = laps.map((l) => `<option value="${l.id}">T${l.lap} · ${fmtLap(l.time_s)}${l.valid ? "" : " (exclu)"}</option>`).join("");
  const valid = laps.filter((l) => l.valid);
  const best = valid.length ? valid.reduce((a, b) => (b.time_s < a.time_s ? b : a)) : laps[0];
  const lastOther = [...valid].reverse().find((l) => l !== best) || laps[laps.length - 1];
  for (const [id, def] of [["cmp-a", best], ["cmp-b", lastOther]]) {
    const sel = $(id);
    const prev = sel.value;
    sel.innerHTML = opts;
    sel.value = [...sel.options].some((o) => o.value === prev) ? prev : def ? String(def.id) : "";
  }
  const th = cur?.theoretical;
  $("cmp-theory").innerHTML = !th ? "" :
    "<tr><th></th><th>Temps</th><th>Tour</th></tr>" +
    th.sectors.map((s, i) => `<tr><td>S${i + 1}</td><td class="purple">${fmtSec(s.time_s)}</td><td>${s.lap ? "T" + s.lap : "–"}</td></tr>`).join("") +
    `<tr><td>Théorique</td><td>${fmtLap(th.time_s)}</td><td></td></tr>` +
    `<tr><td>Meilleur tour</td><td class="faster">${fmtLap(th.best_lap_s)}</td><td>${th.best_lap ? "T" + th.best_lap : "–"}</td></tr>` +
    `<tr><td>À gagner</td><td>${th.gain_s == null ? "–" : th.gain_s.toFixed(3) + " s"}</td><td></td></tr>`;
  loadCompare();
}
sections.push(renderCompare);

async function loadCompare() {
  const a = $("cmp-a").value, b = $("cmp-b").value;
  if (!a || !b) {
    $("cmp-sectors").innerHTML = "";
    lineChart($("cmp-delta"), []);
    lineChart($("cmp-speed"), []);
    return;
  }
  const c = await getJSON(`/api/history/compare?a=${a}&b=${b}`);
  const la = $("cmp-a").selectedOptions[0]?.textContent.split(" · ")[0], lb = $("cmp-b").selectedOptions[0]?.textContent.split(" · ")[0];
  $("cmp-sectors").innerHTML = `<tr><th></th><th>A (${esc(la)})</th><th>B (${esc(lb)})</th><th>B − A</th></tr>` +
    c.sectors.map((s, i) => `<tr><td>${i < 3 ? "S" + (i + 1) : "Tour"}</td><td>${i < 3 ? fmtSec(s.a) : fmtLap(s.a)}</td>` +
      `<td>${i < 3 ? fmtSec(s.b) : fmtLap(s.b)}</td><td class="${diffClass(s.diff)}">${fmtDiff(s.diff)}</td></tr>`).join("");
  lineChart($("cmp-delta"), c.delta ? [{ name: "B − A", color: SERIES[1], points: c.delta }] : [],
    { xFmt: (x) => `${Math.round(x)} %`, yFmt: (y) => fmtDiff(y, 2), xLabel: "avancement dans le tour" });
  lineChart($("cmp-speed"), [
    { name: `A (${la})`, color: SERIES[0], points: c.speed_a || [] },
    { name: `B (${lb})`, color: SERIES[1], points: c.speed_b || [] },
  ], { xFmt: (x) => `${Math.round(x)} %`, yFmt: (y) => `${Math.round(y)}`, xLabel: "avancement dans le tour" });
}
$("cmp-a").addEventListener("change", loadCompare);
$("cmp-b").addEventListener("change", loadCompare);

// --- Comparaison de sessions (cochées dans la liste) ------------------------------------------------------
function closeComparison() {
  compareIds = [];
  $("sessions-compare-section").hidden = true;
}
$("compare-close").addEventListener("click", closeComparison);
$("compare-btn").addEventListener("click", async () => {
  // ordre chronologique : la plus ancienne à gauche
  compareIds = [...checked].sort((a, b) => a - b);
  await renderSessionCompare();
  $("sessions-compare-section").scrollIntoView({ behavior: "smooth", block: "start" });
});

async function renderSessionCompare() {
  if (compareIds.length < 2) return closeComparison();
  const sec = $("sessions-compare-section");
  sec.hidden = false;
  let data;
  try {
    data = await getJSON(`/api/history/compare-sessions?ids=${compareIds.join(",")}`);
  } catch (e) {
    $("scmp-table").innerHTML = `<tr><td class="muted">Comparaison impossible : ${esc(e)}</td></tr>`;
    return;
  }
  const ss = data.sessions;
  const color = (i) => SERIES[i % SERIES.length];
  const head = `<tr><th></th>` + ss.map((s, i) => `<th><i class="dot" style="background:${color(i)}"></i>` +
    `${s.session.id === data.reference ? '<span class="ref" title="Référence : meilleur tour le plus rapide">★</span> ' : ""}` +
    `${esc(fmtDate(s.session.started_at))}<br>${esc(s.session.session || "")} · ${esc(s.session.track || "")}<br>${esc(s.session.car || "")}</th>`).join("") + "</tr>";
  // [libellé, valeur(s), format, sens du meilleur : -1 plus petit, 1 plus grand, 0 aucun]
  const rows = [
    ["Meilleur tour", (s) => s.report.pace.best_s, fmtLap, -1],
    ["Écart à la référence", (s) => s.best_vs_ref?.sectors[3].diff, (v) => fmtDiff(v), -1],
    ...[0, 1, 2].map((k) => [`S${k + 1} du meilleur tour`, (s) => s.best_vs_ref?.sectors[k].b, fmtSec, -1]),
    ["Théorique", (s) => s.report.pace.theoretical_s, fmtLap, -1],
    ["Moyenne", (s) => s.report.pace.avg_s, fmtLap, -1],
    ["Médiane", (s) => s.report.pace.median_s, fmtLap, -1],
    ["Régularité (écart-type)", (s) => s.report.consistency.stdev_s, (v) => (v == null ? "–" : `±${v.toFixed(2)} s`), -1],
    ["Tours à 1 s de la médiane", (s) => s.report.consistency.within_1_pct, (v) => (v == null ? "–" : `${v} %`), 1],
    ["Tours (propres)", (s) => s.report.pace.laps, (v, s) => `${v} (${s.report.pace.clean_laps})`, 0],
    ["Temps roulé", (s) => s.report.pace.total_time_s, fmtDur, 0],
    ["Relais", (s) => s.stints, (v) => v, 0],
    ["Dégradation moyenne", (s) => s.deg_s_per_lap, fmtDeg, -1],
    ["Carburant / tour", (s) => s.report.consumption.fuel_per_lap, (v) => fmt(v, 2, " L"), -1],
    ["Énergie / tour", (s) => s.report.consumption.energy_per_lap, (v) => fmt(v, 2, " %"), -1],
    ["Incidents (invalidés + chocs)", (s) => s.report.incidents.invalid_laps + s.report.incidents.impacts, (v) => v, -1],
    ["Piste", (s) => s.report.conditions.track_temp_min, (v, s) => (v == null ? "–" : `${v.toFixed(0)}–${s.report.conditions.track_temp_max.toFixed(0)} °C`), 0],
    ["Tours mouillés", (s) => s.report.conditions.wet_laps, (v) => v, 0],
  ];
  $("scmp-table").innerHTML = head + rows.map(([label, get, f, dir]) => {
    const vals = ss.map((s) => { try { return get(s); } catch { return null; } });
    const nums = vals.filter((v) => typeof v === "number");
    const best = dir && nums.length > 1 ? (dir < 0 ? Math.min(...nums) : Math.max(...nums)) : null;
    if (!vals.some((v) => v != null)) return "";
    return `<tr><td>${label}</td>` + vals.map((v, i) => `<td class="${best != null && v === best && new Set(nums).size > 1 ? "faster" : ""}">${v == null ? "–" : esc(f(v, ss[i]))}</td>`).join("") + "</tr>";
  }).join("");
  const name = (s) => `${fmtDate(s.session.started_at)} · ${s.session.session || "?"} · ${s.session.track || "?"}`;
  lineChart($("scmp-laps"), ss.map((s, i) => ({ name: name(s), color: color(i), points: s.laps })),
    { xFmt: (x) => `T${x}`, yFmt: (y) => fmtLap(y).slice(0, -1), xLabel: "tour" });
  const deltas = ss.filter((s) => s.best_vs_ref?.delta?.length && s.session.id !== data.reference)
    .map((s) => ({ name: name(s), color: color(ss.indexOf(s)), points: s.best_vs_ref.delta }));
  if (deltas.length) lineChart($("scmp-delta"), deltas, { xFmt: (x) => `${Math.round(x)} %`, yFmt: (y) => fmtDiff(y, 2), xLabel: "avancement dans le tour", intX: false });
  else $("scmp-delta").innerHTML = '<p class="hint">Pas de trace comparable (circuits différents, ou meilleurs tours enregistrés sans trace).</p>';
}

// --- F28 : évolution des conditions (un relevé toutes les 30 s de session) --------------------------------
const GRIP = ["vert", "faible", "moyen", "élevé", "saturé"];
const fmtSessionTime = (s) => { s = Math.round(s); return `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`; };

function renderConditions(cur) {
  const c = cur?.conditions || [];
  const pts = (key, k = 1) => c.filter((r) => r[key] != null).map((r) => [r.session_time_s, r[key] * k]);
  // graduations du temps de session à 5, 10, 15, 30 min, 1 h ou 2 h
  const timeTicks = (a, b) => {
    const step = [300, 600, 900, 1800, 3600, 7200, 14400].find((st) => (b - a) / st <= 7) || 14400;
    const out = [];
    for (let v = Math.ceil(a / step) * step; v <= b; v += step) out.push(v);
    return out;
  };
  const opts = { xFmt: fmtSessionTime, xLabel: "temps de session", intX: false, xTicks: timeTicks };
  lineChart($("cond-temps"), [
    { name: "Piste", color: SERIES[1], points: pts("track_temp") },
    { name: "Air", color: SERIES[0], points: pts("air_temp") },
  ], { ...opts, yFmt: (y) => `${y.toFixed(0)} °C` });
  lineChart($("cond-wet"), [
    { name: "Pluie", color: SERIES[0], points: pts("rain", 100) },
    { name: "Piste mouillée", color: SERIES[2], points: pts("wetness", 100) },
  ], { ...opts, yFmt: (y) => `${Math.round(y)} %` });
  // Changements de grip (gomme sur la piste) : texte, ce n'est pas une grandeur continue
  const changes = [];
  c.forEach((r, i) => { if (r.grip != null && (i === 0 || r.grip !== c[i - 1].grip)) changes.push(`${fmtSessionTime(r.session_time_s)} ${GRIP[r.grip] ?? r.grip}`); });
  const tt = c.filter((r) => r.track_temp != null);
  $("cond-summary").textContent = !c.length ? "Aucun relevé (enregistré pendant que l'on roule)." :
    (tt.length ? `Piste de ${Math.min(...tt.map((r) => r.track_temp)).toFixed(1)} à ${Math.max(...tt.map((r) => r.track_temp)).toFixed(1)} °C. ` : "") +
    (changes.length ? `Grip : ${changes.join(" → ")}.` : "");
}
sections.push(renderConditions);

// --- F26 : notes de setup (voiture + piste de la session affichée) ---------------------------------------
let notesKey = "";

async function renderNotes(cur) {
  const s = cur?.session;
  $("notes-section").hidden = !s;
  if (!s) return;
  $("notes-scope").textContent = `Notes pour ${s.car || "?"} sur ${s.track || "?"} (toutes les sessions). Les notes liées à cette session sont marquées.`;
  const notes = await getJSON(`/api/notes?car=${encodeURIComponent(s.car || "")}&track=${encodeURIComponent(s.track || "")}`);
  $("notes").innerHTML = notes.length ? notes.map((n) => `<article class="note ${n.session_id === s.id ? "this" : ""}" data-id="${n.id}">` +
    `<header><strong>${esc(n.title || "(sans titre)")}</strong> <span class="hint">${esc(fmtDate(n.updated_at))}${n.session_id === s.id ? " · cette session" : n.session_id ? " · autre session" : ""}</span>` +
    `<span class="note-actions"><button type="button" class="secondary" data-edit="${n.id}">Modifier</button> <button type="button" class="secondary" data-del="${n.id}">Supprimer</button></span></header>` +
    `<p>${esc(n.text).replace(/\n/g, "<br>")}</p></article>`).join("") : '<p class="hint">Aucune note pour cette voiture sur cette piste.</p>';
  $("notes").querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
    const n = notes.find((x) => String(x.id) === b.dataset.edit);
    $("note-id").value = n.id; $("note-title").value = n.title; $("note-text").value = n.text;
    $("note-session").checked = n.session_id === s.id;
    $("note-save").textContent = "Enregistrer"; $("note-cancel").hidden = false;
    $("note-title").focus();
  }));
  $("notes").querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("Supprimer cette note ?")) return;
    await fetch(`/api/notes/${b.dataset.del}`, { method: "DELETE" });
    renderNotes(current);
  }));
  const key = `${s.id}`;
  if (key !== notesKey) { notesKey = key; resetNoteForm(); }
}
sections.push(renderNotes);

function resetNoteForm() {
  $("note-id").value = ""; $("note-title").value = ""; $("note-text").value = "";
  $("note-save").textContent = "Ajouter la note"; $("note-cancel").hidden = true;
}

$("note-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const s = current?.session;
  if (!s || (!$("note-title").value.trim() && !$("note-text").value.trim())) return;
  const body = { car: s.car || "", track: s.track || "", session_id: $("note-session").checked ? s.id : null,
    title: $("note-title").value.trim(), text: $("note-text").value };
  const id = $("note-id").value;
  await fetch(id ? `/api/notes/${id}` : "/api/notes", { method: id ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  resetNoteForm();
  renderNotes(current);
});
$("note-cancel").addEventListener("click", resetNoteForm);

$("delete").addEventListener("click", () => shownId != null && deleteSessions([shownId]));

// Suit la session en cours : nouvelles sessions et nouveaux tours apparaissent d'eux-mêmes.
async function refresh() {
  try {
    const before = sessionList[0]?.id;
    const list = await loadSessions();
    const latest = list[0];
    // une nouvelle session commence : on l'affiche si l'on regardait la précédente plus récente
    if (latest && before != null && latest.id !== before && shownId === before) { shownId = latest.id; renderSessionList(); }
    const n = current?.laps?.length ?? -1;
    const shown = list.find((s) => s.id === shownId);
    if ((current?.session?.id ?? null) !== shownId || (shown && shown.laps !== n)) await loadSession();
  } catch (e) {
    $("session-info").textContent = `Serveur injoignable : ${e}`;
  }
}

loadSessions().then(loadSession).catch((e) => ($("session-count").textContent = `Serveur injoignable : ${e}`));
setInterval(refresh, 10000);
