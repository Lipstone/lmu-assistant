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

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

async function loadSessions(keep) {
  const list = await getJSON("/api/history/sessions");
  const sel = $("sessions");
  const prev = keep ?? sel.value;
  sel.innerHTML = list.length
    ? list.map((s) => `<option value="${s.id}">${esc(fmtDate(s.started_at))} · ${esc(s.session)} · ${esc(s.track)} · ${esc(s.car)} · ${s.laps} tours${s.best_s ? " · " + fmtLap(s.best_s) : ""}</option>`).join("")
    : `<option value="">Aucune session enregistrée</option>`;
  if (prev && list.some((s) => String(s.id) === String(prev))) sel.value = prev;
  $("delete").disabled = !list.length;
  return list;
}

async function loadSession() {
  const id = $("sessions").value;
  if (!id) {
    current = null;
    $("session-info").textContent = "Les tours sont enregistrés automatiquement pendant que l'on roule (lecture du jeu).";
    renderAll();
    return;
  }
  current = await getJSON(`/api/history/sessions/${id}`);
  const s = current.session;
  $("session-info").textContent = `${s.driver || "?"} · ${s.car_class || ""} · du ${fmtDate(s.started_at)} au ${fmtDate(s.ended_at)} · source ${s.source}`;
  renderAll();
}

// Sections de la page : chaque fonctionnalité ajoute la sienne.
const sections = [];

function renderAll() {
  for (const render of sections) render(current);
}

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
function lineChart(el, series, { xFmt = (x) => x, yFmt = (y) => y, xLabel = "", height = 220 } = {}) {
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
  for (const v of niceTicks(x0, x1, 6).filter((v) => Number.isInteger(v))) {
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

$("sessions").addEventListener("change", loadSession);
$("delete").addEventListener("click", async () => {
  const id = $("sessions").value;
  if (!id || !confirm("Supprimer définitivement cette session et ses tours de l'historique ?")) return;
  await fetch(`/api/history/sessions/${id}`, { method: "DELETE" });
  await loadSessions("");
  await loadSession();
});

// Suit la session en cours : nouvelles sessions et nouveaux tours apparaissent d'eux-mêmes.
async function refresh() {
  try {
    const before = $("sessions").value;
    const list = await loadSessions();
    const latest = list[0];
    const sel = $("sessions").value;
    const n = current?.laps?.length ?? -1;
    if (sel !== before || (latest && String(latest.id) === sel && latest.laps !== n)) await loadSession();
  } catch (e) {
    $("session-info").textContent = `Serveur injoignable : ${e}`;
  }
}

loadSessions().then(loadSession).catch((e) => ($("session-info").textContent = `Serveur injoignable : ${e}`));
setInterval(refresh, 10000);
