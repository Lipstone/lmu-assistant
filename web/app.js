// Connexion au serveur local et rendu des widgets.
const params = new URLSearchParams(location.search);
const OVERLAY = params.get("mode") === "overlay";
// Overlay : une fenêtre par widget, qui ouvre /?mode=overlay&widget=<id> et n'affiche que ce widget.
// Sans `widget`, le mode overlay montre tous les widgets à leur position écran (aperçu des réglages).
const ONLY = OVERLAY ? params.get("widget") : null;
if (OVERLAY) document.body.classList.add("overlay");
if (ONLY) {
  document.body.classList.add("single");
  document.querySelectorAll("[data-widget]").forEach((el) => (el.hidden = el.dataset.widget !== ONLY));
}

const $ = (id) => document.getElementById(id);

function fmtLap(s) {
  if (s == null) return "–";
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(3).padStart(6, "0")}`;
}

// Au-delà de 100, pas de décimale (garde le widget overlay étroit, ex. carburant à ajouter sur 24 h).
const fmt = (v, digits, unit = "") => (v == null ? "–" : `${v.toFixed(Math.abs(v) >= 100 ? 0 : digits)}${unit}`);

// F01 / F02 : carburant (litres) ou énergie virtuelle (%) ; calculs côté serveur (backend/lmu_assistant/fuel.py).
// Mode « auto » : % d'énergie virtuelle si la voiture en a, sinon litres.
let fuelMode = "auto";

function renderFuel(d) {
  const hasEnergy = d.virtual_energy_pct != null;
  const energy = fuelMode === "energy" || (fuelMode === "auto" && hasEnergy);
  const f = (energy ? d.energy : d.fuel) || {};
  const unit = energy ? "%" : " L";
  const level = energy ? d.virtual_energy_pct : d.fuel_l;
  $("fuel-title").textContent = energy ? "Énergie virtuelle" : "Carburant";
  $("fuel").textContent = fmt(level, 1, unit);
  const pct = energy ? level : d.fuel_capacity_l ? (100 * d.fuel_l) / d.fuel_capacity_l : 0;
  $("fuel-bar").style.width = `${Math.min(100, Math.max(0, pct || 0))}%`;
  $("fuel-last").textContent = fmt(f.last_lap, 2, unit);
  $("fuel-avg").textContent = f.avg_lap == null ? "–" : `${f.avg_lap.toFixed(2)}${unit} (${f.valid_laps})`;
  $("fuel-laps").textContent = fmt(f.laps_left, 1);
  $("fuel-finish").textContent = fmt(f.laps_to_finish, 1);
  $("fuel-add").textContent = f.to_add == null ? "–" : f.to_add > 0 ? `+${fmt(f.to_add, 1, unit)}` : "assez";
  const low = f.laps_left != null && f.laps_left < 2;
  $("fuel-laps").classList.toggle("alert", low);
  $("fuel-bar").classList.toggle("alert", low);
  $("fuel-add").classList.toggle("good", f.to_add === 0);
  // L'autre grandeur en une ligne : litres en mode énergie, énergie en mode litres (si la voiture en a).
  const other = energy ? true : hasEnergy;
  $("fuel-other-label").hidden = $("fuel-other").hidden = !other;
  $("fuel-other-label").textContent = energy ? "Carburant" : "Énergie";
  $("fuel-other").textContent = energy ? fmt(d.fuel_l, 1, " L") : fmt(d.virtual_energy_pct, 1, "%");
}

// F03 : delta en direct ; traces de référence et calculs côté serveur (backend/lmu_assistant/delta.py).
let deltaRef = "best";
const DELTA_REFS = { best: "meilleur", last: "dernier", record: "record" };
const DELTA_BAR_S = 2; // la barre est pleine à ±2 s

const fmtDelta = (v) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(2)}`);

function setSign(el, v) {
  el.classList.toggle("faster", v != null && v < 0);
  el.classList.toggle("slower", v != null && v > 0);
}

function renderDelta(d) {
  const info = d.delta || {};
  const v = info[`vs_${deltaRef}`];
  const ref = info[`${deltaRef}_s`];
  $("delta-title").textContent = `Delta · ${DELTA_REFS[deltaRef]}`;
  $("delta").textContent = fmtDelta(v);
  setSign($("delta"), v);
  // Barre centrée : vers la gauche (vert) quand on gagne du temps, vers la droite (rouge) quand on en perd.
  const k = v == null ? 0 : Math.min(1, Math.abs(v) / DELTA_BAR_S) * 50;
  const bar = $("delta-bar");
  bar.style.width = `${k}%`;
  bar.style.left = v != null && v < 0 ? `${50 - k}%` : "50%";
  setSign(bar, v);
  $("delta-predicted").textContent = v == null || ref == null ? "–" : fmtLap(ref + v);
  $("delta-ref-label").textContent = deltaRef === "record" ? "Record" : deltaRef === "last" ? "Dernier" : "Meilleur";
  $("delta-ref").textContent = fmtLap(ref);
  for (const r of Object.keys(DELTA_REFS)) {
    const el = $(`delta-vs-${r}`);
    el.textContent = fmtDelta(info[`vs_${r}`]);
    setSign(el, info[`vs_${r}`]);
  }
}

// F04 : temps au tour ; historique, moyenne et régularité côté serveur (backend/lmu_assistant/laptimes.py).
// Régularité = écart-type des N derniers tours valides : vert sous 0,3 s, orange au-delà d'une seconde.
function renderLaps(d) {
  const info = d.laps || {};
  $("lap").textContent = d.lap ? `${d.lap}  (P${d.position})` : "–";
  $("current").textContent = fmtLap(d.current_lap_s);
  $("current").classList.toggle("slower", !!d.lap_invalid);
  $("current").title = d.lap_invalid ? "tour invalidé" : "";
  $("last").textContent = fmtLap(d.last_lap_s);
  $("last").classList.toggle("faster", d.last_lap_s != null && d.last_lap_s === d.best_lap_s);
  $("best").textContent = fmtLap(d.best_lap_s);
  $("lap-avg-label").textContent = `Moyenne (${info.avg_count || 0})`;
  $("lap-avg").textContent = fmtLap(info.avg_s);
  const sd = info.stdev_s;
  $("lap-stdev").textContent = sd == null ? "–" : `±${sd.toFixed(2)} s`;
  $("lap-stdev").classList.toggle("good", sd != null && sd < 0.3);
  $("lap-stdev").classList.toggle("alert", sd != null && sd > 1);
  $("laps").innerHTML = (info.recent || [])
    .map((l) => {
      const tag = l.pit ? "stand" : l.invalid ? "invalide" : !l.valid ? "partiel" : "";
      const gap = l.vs_best == null ? "" : l.vs_best === 0 ? "meilleur" : `+${l.vs_best.toFixed(2)}`;
      return `<tr class="${l.valid ? "" : "excluded"}"><td>T${l.lap}</td><td>${fmtLap(l.time_s)}</td>` +
        `<td class="${l.vs_best === 0 ? "faster" : ""}">${tag || gap}</td></tr>`;
    })
    .join("");
}

// F05 : pneus. Par roue : températures ext / milieu / int dessinées côté extérieur de la voiture
// (roues gauches : ext à gauche ; roues droites : ext à droite), pression et usure (% de gomme restante).
// Couleur des températures : bleu sous la plage idéale, vert dedans, orange puis rouge au-dessus.
let tyreRange = [75, 100];
let pressureUnit = "kpa";
const WHEELS = ["AVG", "AVD", "ARG", "ARD"];
const PRESSURE = { kpa: [1, 0, " kPa"], psi: [0.1450377, 1, " psi"], bar: [0.01, 2, " bar"] };
const HOT_RED_C = 15; // rouge à 15 °C au-dessus de la plage idéale

function tempClass(t) {
  const [lo, hi] = tyreRange;
  if (t < lo) return "cold";
  if (t <= hi) return "ideal";
  return t < hi + HOT_RED_C ? "warm" : "hot";
}

function renderTyres(d) {
  const [k, digits, unit] = PRESSURE[pressureUnit] || PRESSURE.kpa;
  $("tyres").innerHTML = d.wheels
    .map((w, i) => {
      const [inner, mid, outer] = w.temp_c;
      const left = i % 2 === 0;
      const temps = left ? [outer, mid, inner] : [inner, mid, outer];
      const wear = Math.round(w.wear * 100);
      return `<div class="tyre ${left ? "left" : "right"}"><span class="wheel-name">${WHEELS[i]}</span>` +
        `<div class="temps">${temps.map((t) => `<span class="${tempClass(t)}">${Math.round(t)}</span>`).join("")}</div>` +
        `<div class="tyre-info"><span>${(w.pressure_kpa * k).toFixed(digits)}${unit}</span>` +
        `<span class="${wear < 30 ? "alert" : ""}">${wear}%</span></div></div>`;
    })
    .join("");
}

// F06 : freins ; pics par tour et alerte surchauffe (avec hystérésis) côté serveur (backend/lmu_assistant/brakes.py).
// Couleur : bleu sous 200 °C (freins froids), vert, orange à moins de 100 °C du seuil, rouge en surchauffe.
const BRAKES_COLD_C = 200;
const BRAKES_WARN_C = 100;

function brakeClass(t, threshold, overheat) {
  if (overheat || t > threshold) return "hot";
  if (t > threshold - BRAKES_WARN_C) return "warm";
  return t < BRAKES_COLD_C ? "cold" : "ideal";
}

function renderBrakes(d) {
  const b = d.brakes || {};
  const thr = b.threshold_c ?? 800;
  const over = b.overheat || [];
  const peaks = b.peak_last_lap_c || b.peak_lap_c || [];
  $("brakes").innerHTML = d.wheels
    .map((w, i) => {
      const t = w.brake_temp_c;
      return `<div class="brake ${i % 2 ? "right" : "left"}"><span class="wheel-name">${WHEELS[i]}</span>` +
        `<span class="brake-temp ${brakeClass(t, thr, over[i])}">${Math.round(t)}</span>` +
        `<span class="brake-peak" title="${b.peak_last_lap_c ? "pic du tour précédent" : "pic du tour en cours"}">` +
        `pic ${peaks[i] == null ? "–" : Math.round(peaks[i])}</span></div>`;
    })
    .join("");
  const hot = WHEELS.filter((_, i) => over[i]);
  $("brake-alert").hidden = !hot.length;
  $("brake-alert").textContent = hot.length ? `Surchauffe ${hot.join(" ")}` : "";
  $("brake-alert").title = `au-delà de ${Math.round(thr)} °C`;
}

// F07 / F08 : couleur de chaque classe (repère visuel, comme dans le jeu).
function classColor(name) {
  const n = (name || "").toLowerCase();
  if (n.includes("hyper")) return "#e53935";
  if (n.includes("lmp2")) return "#1e88e5";
  if (n.includes("lmp3")) return "#8e24aa";
  if (n.includes("gt")) return "#43a047";
  return "#757575";
}

const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// Colonnes optionnelles du relative et du classement (Réglages overlay, par widget, désactivées par défaut) :
// dégâts globaux et consommation par tour de chaque voiture (backend/lmu_assistant/opponents.py).
const columns = { relative: { damage: false, consumption: false }, standings: { damage: false, consumption: false } };

function damageCell(e) {
  if (e.damage_pct == null) return '<td class="opt dmg" title="dégâts non transmis par le jeu">–</td>';
  const p = Math.round(e.damage_pct);
  const notes = [`carrosserie ${p} %`];
  if (e.wheels_off) notes.push(`${e.wheels_off} roue${e.wheels_off > 1 ? "s" : ""} crevée(s) ou arrachée(s)`);
  if (e.parts_detached) notes.push("pièces arrachées");
  const cls = e.wheels_off || p < 75 ? "bad" : p < 100 || e.parts_detached ? "warn" : "intact";
  return `<td class="opt dmg ${cls}" title="${notes.join(" · ")}">${p}${e.wheels_off ? "!" : ""}</td>`;
}

// Énergie virtuelle (%) si la voiture en a, sauf si le widget Carburant est réglé en litres.
function consumptionCell(e) {
  const energy = e.energy_per_lap != null && fuelMode !== "fuel";
  const perLap = energy ? e.energy_per_lap : e.fuel_per_lap;
  const left = energy ? e.energy_pct : e.fuel_l;
  if (perLap == null) {
    const why = left == null ? "carburant non transmis par le jeu" : "en attente d'un tour complet sans arrêt";
    return `<td class="opt fuel" title="${why}">–</td>`;
  }
  const unit = energy ? "%" : "L";
  const laps = left != null && perLap > 0 ? left / perLap : null;
  const title = `consommation estimée par tour · reste ${left == null ? "–" : left.toFixed(1) + " " + unit}` +
    (laps == null ? "" : ` (~${laps.toFixed(1)} tours)`);
  return `<td class="opt fuel ${laps != null && laps < 2 ? "warn" : ""}" title="${title}">${perLap.toFixed(1)}${unit}</td>`;
}

const optCells = (id, e) =>
  (columns[id].damage ? damageCell(e) : "") + (columns[id].consumption ? consumptionCell(e) : "");
const optCount = (id) => +columns[id].damage + +columns[id].consumption;

// F07 : relative ; voitures proches sur la piste et écarts calculés côté serveur (backend/lmu_assistant/relative.py).
// Orange : la voiture a un ou plusieurs tours d'avance sur nous ; bleu : tours de retard ; grisé : autre classe.
function renderRelative(d) {
  $("relative").innerHTML = (d.relative || [])
    .map((r) => {
      const cls = [r.is_player ? "me" : "", r.laps_diff > 0 ? "lap-up" : r.laps_diff < 0 ? "lap-down" : "",
        r.same_class ? "" : "other-class"].join(" ");
      const laps = r.laps_diff ? `${r.laps_diff > 0 ? "+" : "−"}${Math.abs(r.laps_diff)}T` : "";
      const gap = r.is_player ? "" : r.gap_s == null ? "–" : Math.abs(r.gap_s).toFixed(1);
      return `<tr class="${cls}"><td><span class="class-pos" style="background:${classColor(r.car_class)}" ` +
        `title="${esc(r.car_class)} · P${r.position} au général">P${r.class_position}</span></td>` +
        `<td class="num">${r.number ? "#" + esc(r.number) : ""}</td>` +
        `<td class="driver">${esc(r.driver)}${r.in_pits ? ' <span class="pit">STAND</span>' : ""}</td>` +
        `<td class="laps-diff">${laps}</td>${optCells("relative", r)}<td class="gap">${gap}</td></tr>`;
    })
    .join("");
}

// F08 : classement par classe ; sélection des lignes et écarts côté serveur (backend/lmu_assistant/standings.py).
// Écart au leader de la classe (en tours s'il y a au moins un tour), écart à la voiture devant au survol.
const fmtGap = (s, laps) => (laps ? `+${laps}T` : s == null ? "–" : `+${s.toFixed(1)}`);
const fmtShortLap = (s) => (s == null ? "–" : fmtLap(s).slice(0, -2)); // 3:45.6

function renderStandings(d) {
  const span = 5 + optCount("standings");
  $("standings").innerHTML = (d.standings || [])
    .map((c) => {
      const head = `<tr class="class-head"><td colspan="${span}"><span class="class-dot" style="background:${classColor(c.car_class)}"></span>` +
        `${esc(c.car_class || "?")} <span class="muted">(${c.cars})</span></td></tr>`;
      return head + c.entries
        .map((e) => {
          const sep = e.skipped_before ? `<tr class="skip"><td colspan="${span}">⋯</td></tr>` : "";
          const leader = e.class_position === 1;
          return sep + `<tr class="${e.is_player ? "me" : ""}"><td class="cpos">P${e.class_position}</td>` +
            `<td class="num">${e.number ? "#" + esc(e.number) : ""}</td>` +
            `<td class="driver">${esc(e.driver)}${e.in_pits ? ' <span class="pit">STAND</span>' : ""}</td>` +
            `<td class="gap" title="${leader ? "" : "à la voiture devant : " + fmtGap(e.interval_s, e.laps_interval)}">` +
            `${leader ? "Leader" : fmtGap(e.gap_leader_s, e.laps_leader)}</td>${optCells("standings", e)}` +
            `<td class="last" title="dernier tour">${fmtShortLap(e.last_lap_s)}</td></tr>`;
        })
        .join("");
    })
    .join("");
}

// F09 : fenêtre de stand ; calculs côté serveur (backend/lmu_assistant/pitstop.py) à partir des moyennes de
// consommation (F01, F02) et des temps au tour (F04). Orange à moins de 2 tours de l'arrêt obligatoire.
function renderPit(d) {
  const p = d.pit || {};
  const urgent = p.laps_left != null && p.laps_left < 2;
  $("pit-laps").textContent = p.laps_left == null ? "–" : `${p.laps_left.toFixed(1)} tours`;
  $("pit-laps").classList.toggle("alert", urgent);
  $("pit-limit").textContent = p.limited_by ? `avant l'arrêt obligatoire (${p.limited_by})` : "en attente d'un tour complet";
  $("pit-last").textContent = p.last_lap == null ? "–" : p.last_lap <= d.lap ? `ce tour` : `fin T${p.last_lap}`;
  $("pit-last").classList.toggle("alert", urgent);
  let win = "–";
  if (p.stops_left === 0) win = "aucun arrêt";
  else if (p.window_open_lap != null && p.last_lap != null)
    win = p.window_open_lap <= d.lap ? `ouverte → T${p.last_lap}` : `T${p.window_open_lap} → T${p.last_lap}`;
  $("pit-window").textContent = win;
  $("pit-window").classList.toggle("good", p.window_open_lap != null && p.window_open_lap <= d.lap);
  $("pit-stops").textContent = p.stops_left == null ? "–" : `${p.stops_left}` + (p.laps_per_stint ? ` · ${p.laps_per_stint.toFixed(1)} t/plein` : "");
  $("pit-loss").textContent = p.loss_s == null ? "–" : `${p.loss_s.toFixed(1)} s ${p.loss_measured ? "mesuré" : "défaut"}`;
  $("pit-loss").title = p.loss_measured ? `moyenne des derniers arrêts (${p.loss_samples} mesuré${p.loss_samples > 1 ? "s" : ""})` : "valeur des réglages";
  $("pit-rejoin").textContent = p.rejoin_class_position == null ? "–" : `P${p.rejoin_class_position} classe`;
}

// F10 : session et piste ; drapeau, tendance de la piste et libellés côté serveur (backend/lmu_assistant/session.py).
const fmtClock = (s) => {
  if (s == null) return "–";
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
};

function renderSession(d) {
  const s = d.session_info || {};
  $("sess-left").textContent = s.laps_left != null ? `${s.laps_left} tour${s.laps_left > 1 ? "s" : ""}` : fmtClock(s.time_left_s);
  $("sess-bar").style.width = `${Math.round(100 * (s.progress || 0))}%`;
  const flag = $("sess-flag");
  flag.hidden = !s.flag_label;
  flag.textContent = s.flag_label || "";
  flag.className = `flag ${s.flag || "none"}`;
  $("sess-temps").textContent = s.air_temp_c == null ? "–" : `${Math.round(s.air_temp_c)} / ${Math.round(s.track_temp_c ?? 0)} °C`;
  const tr = s.track_temp_trend_c;
  $("sess-trend").textContent = tr == null ? "–" : `${tr > 0 ? "+" : tr < 0 ? "−" : "±"}${Math.abs(tr).toFixed(1)} °C`;
  $("sess-trend").title = "évolution de la température piste sur les 10 dernières minutes";
  $("sess-rain").textContent = s.rain_pct == null ? "–" : s.rain_pct ? `${s.rain_pct} %` : "non";
  $("sess-rain").classList.toggle("alert", !!s.rain_pct);
  $("sess-wet").textContent = s.wetness_pct == null ? "–" : `${s.wetness_pct} %`;
  $("sess-wet").classList.toggle("alert", (s.wetness_pct || 0) >= 10);
  $("sess-grip").textContent = s.grip || "–";
  $("sess-sky").textContent = s.sky || "–";
  $("sess-tod").textContent = s.time_of_day_s == null ? "–" : fmtClock(s.time_of_day_s).slice(0, -3);
}

// F11 : dégâts ; calculs côté serveur (backend/lmu_assistant/damage.py). Voiture vue de dessus en SVG
// (web/index.html) : 8 zones de carrosserie colorées sur leur bord (orange = léger, rouge = lourd), état global au centre,
// roues (crevée, arrachée), suspensions (triangles, par roue), lame avant et aileron (aéro) ; aéro, suspension et réparation
// viennent de l'API REST du jeu (« – » si elle ne répond pas).
const fmtPctState = (p) => (p == null ? "–" : `${Math.round(p)} %`);
const level = (p, warn = 90, bad = 70) => (p == null || p >= warn ? "" : p >= bad ? "s1" : "s2");

function renderDamage(d) {
  const g = d.damage || {};
  const body = g.body || [];
  const car = $("dmg-car");
  car.querySelectorAll("[data-zone]").forEach((z) => z.setAttribute("class", `edge z${body[z.dataset.zone] || 0}`));
  const susp = g.suspension_pct;
  // Roue : état du pneu / de la roue seulement ; suspension (triangles) : état donné par l'API du jeu
  car.querySelectorAll("[data-wheel]").forEach((w) => {
    const state = (g.wheels || [])[w.dataset.wheel];
    w.setAttribute("class", `wheel ${state === "arrachée" ? "off" : state ? "s1" : ""}`);
  });
  car.querySelectorAll("[data-susp]").forEach((a) => a.setAttribute("class", `susp ${level(susp && susp[a.dataset.susp])}`));
  car.querySelectorAll(".aero").forEach((a) => a.setAttribute("class", `aero ${level(g.aero_pct)}`));
  const pct = Math.round(g.body_pct ?? 100);
  $("dmg-pct").textContent = `${pct}%`;
  $("dmg-pct").setAttribute("class", `pct ${pct < 75 ? "heavy" : pct < 100 ? "hit" : ""}`);
  const alerts = [];
  (g.wheels || []).forEach((w, i) => w && alerts.push(`${WHEELS[i]} ${w}`));
  if (g.parts_detached) alerts.push("pièces arrachées");
  if (g.engine_overheating) alerts.push("moteur en surchauffe");
  $("dmg-alert").hidden = !alerts.length;
  $("dmg-alert").textContent = alerts.join(" · ");
  $("dmg-aero").textContent = fmtPctState(g.aero_pct);
  $("dmg-aero").classList.toggle("alert", g.aero_pct != null && g.aero_pct < 90);
  const worst = susp ? susp.reduce((m, p, i) => (p != null && p < susp[m] ? i : m), 0) : null;
  $("dmg-susp").textContent = !susp ? "–" : susp[worst] >= 100 ? "OK" : `${WHEELS[worst]} ${Math.round(susp[worst])} %`;
  $("dmg-susp").title = susp ? susp.map((p, i) => `${WHEELS[i]} ${fmtPctState(p)}`).join(" · ") : "";
  $("dmg-susp").classList.toggle("alert", !!susp && susp[worst] < 90);
  $("dmg-repair").textContent = g.repair_s == null ? "–" : g.repair_s ? `${Math.round(g.repair_s)} s` : "aucune";
  $("dmg-impact").textContent = g.last_impact_ago_s == null ? "aucun" : `il y a ${fmtClock(g.last_impact_ago_s).replace(/^0:0?/, "")}`;
  $("dmg-impact").title = g.last_impact_magnitude == null ? "" : `force ${Math.round(g.last_impact_magnitude)} · ${g.impacts} choc(s) dans la session`;
  $("dmg-engine").textContent = g.water_temp_c == null ? "–" : `${Math.round(g.water_temp_c)} / ${Math.round(g.oil_temp_c ?? 0)} °C`;
  $("dmg-engine").classList.toggle("alert", !!g.engine_overheating);
}

// F12 : inputs. Valeurs brutes du pilote ; la trace (accélérateur vert, frein rouge) est gardée par la page,
// à partir des images reçues (10 par seconde), sur la durée réglée dans Réglages overlay.
let traceS = 8;
const trace = [];

function drawTrace() {
  const c = $("inp-trace");
  const ctx = c.getContext("2d");
  const w = c.width, h = c.height, pad = 4;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  for (const y of [0.25, 0.5, 0.75]) {
    ctx.beginPath(); ctx.moveTo(0, pad + (h - 2 * pad) * y); ctx.lineTo(w, pad + (h - 2 * pad) * y); ctx.stroke();
  }
  if (trace.length < 2) return;
  const t1 = trace[trace.length - 1].t;
  const line = (key, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    trace.forEach((p, i) => {
      const x = w - ((t1 - p.t) / (traceS * 1000)) * w;
      const y = pad + (h - 2 * pad) * (1 - p[key]);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
  };
  line("thr", "#66bb6a");
  line("brk", "#ef5350");
}

function renderInputs(d) {
  const now = performance.now();
  trace.push({ t: now, thr: d.throttle || 0, brk: d.brake || 0 });
  while (trace.length && now - trace[0].t > traceS * 1000) trace.shift();
  drawTrace();
  for (const [id, v] of [["thr", d.throttle], ["brk", d.brake], ["clu", d.clutch]]) {
    $(`inp-${id}`).style.height = `${Math.round(100 * (v || 0))}%`;
    $(`inp-${id}-v`).textContent = Math.round(100 * (v || 0));
  }
  const st = d.steering || 0;
  const bar = $("inp-steer");
  bar.style.width = `${Math.abs(st) * 50}%`;
  bar.style.left = st < 0 ? `${50 + st * 50}%` : "50%";
  const deg = d.steering_range_deg ? Math.round((st * d.steering_range_deg) / 2) : null;
  $("inp-steer-v").textContent = deg == null ? `${Math.round(st * 100)}%` : `${deg}°`;
  $("inp-abs").classList.toggle("on", !!d.abs_active);
  $("inp-tc").classList.toggle("on", !!d.tc_active);
}

// F21 / F22 : relais en cours ; découpage et dégradation côté serveur (backend/lmu_assistant/analysis.py).
// Dégradation = temps perdu par tour sur les tours propres du relais (orange au-delà de 0,15 s/tour).
function renderStint(d) {
  const s = d.stint || {};
  $("stint-title").textContent = s.number ? `Relais ${s.number}` : "Relais";
  $("stint-laps").textContent = s.number ? `${s.laps} tour${s.laps > 1 ? "s" : ""}` : "–";
  $("stint-time").textContent = s.time_s == null ? "–" : fmtClock(s.time_s);
  $("stint-avg").textContent = s.avg_s == null ? "–" : fmtLap(s.avg_s) + (s.stdev_s != null ? ` ±${s.stdev_s.toFixed(2)}` : "");
  const deg = s.deg_s_per_lap;
  $("stint-deg").textContent = deg == null ? "–" : `${deg >= 0 ? "+" : "−"}${Math.abs(deg).toFixed(2)} s/tour`;
  $("stint-deg").classList.toggle("alert", deg != null && deg > 0.15);
  $("stint-fuel").textContent = s.energy_per_lap != null ? `${s.energy_per_lap.toFixed(2)} %/tour` : s.fuel_per_lap != null ? `${s.fuel_per_lap.toFixed(2)} L/tour` : "–";
  $("stint-tyres").textContent = s.tyre_age_laps == null ? "?" : `${s.tyre_age_laps} tour${s.tyre_age_laps > 1 ? "s" : ""}`;
  $("stint-wear-label").textContent = s.worst_wheel ? `Usure ${s.worst_wheel}` : "Usure";
  $("stint-wear").textContent = s.wear_left_pct == null ? "–" :
    `${Math.round(s.wear_left_pct)} %` + (s.wear_per_lap_pct ? ` · −${s.wear_per_lap_pct.toFixed(1)} %/t` : "");
  $("stint-wear").title = s.laps_to_wear_limit == null ? "" : `${s.laps_to_wear_limit.toFixed(0)} tours avant 30 % de gomme`;
  $("stint-wear").classList.toggle("alert", s.laps_to_wear_limit != null && s.laps_to_wear_limit < 3);
}

// Fenêtre d'un seul widget : seul son rendu est utile (les autres sont masqués).
const RENDERERS = {
  lap: renderLaps, delta: renderDelta, fuel: renderFuel, car: renderCar, tyres: renderTyres, brakes: renderBrakes,
  relative: renderRelative, standings: renderStandings, pit: renderPit, session: renderSession, damage: renderDamage,
  inputs: renderInputs, stint: renderStint,
};

function renderCar(d) {
  $("speed").textContent = `${Math.round(d.speed_kmh)} km/h`;
  $("gear").textContent = d.gear === 0 ? "N" : d.gear < 0 ? "R" : d.gear;
  $("rpm").textContent = Math.round(d.rpm);
}

function render(d) {
  if (ONLY && RENDERERS[ONLY]) {
    RENDERERS[ONLY](d);
    return;
  }
  $("status").textContent = d.connected ? `connecté (${d.source})` : "jeu non détecté";
  $("status").classList.toggle("on", d.connected);
  $("session").textContent = [d.session, d.track, d.car].filter(Boolean).join(" · ");
  renderLaps(d);
  renderDelta(d);
  renderFuel(d);
  renderCar(d);
  renderTyres(d);
  renderBrakes(d);
  renderRelative(d);
  renderStandings(d);
  renderPit(d);
  renderSession(d);
  renderDamage(d);
  renderInputs(d);
  renderStint(d);
}

// Configuration (T06) : visibilité partout ; position (écran), taille, opacité du fond et du texte en mode overlay.
// Fenêtre d'un seul widget : il est en haut à gauche, la fenêtre elle-même est placée par l'overlay.
// Opacités du fond et du texte : valeur du widget si définie, sinon valeur globale.
function applyConfig(cfg) {
  setPlacement(!!cfg.placement);
  fuelMode = cfg.fuel_mode || "auto";
  deltaRef = cfg.delta_reference || "best";
  tyreRange = [cfg.tyre_temp_min_c ?? 75, cfg.tyre_temp_max_c ?? 100];
  pressureUnit = cfg.pressure_unit || "kpa";
  traceS = cfg.inputs_trace_s || 8;
  for (const w of cfg.widgets || []) {
    const el = document.querySelector(`[data-widget="${w.id}"]`);
    if (!el) continue;
    if (columns[w.id]) {
      columns[w.id] = { damage: !!w.show_damage, consumption: !!w.show_consumption };
      el.classList.toggle("col-dmg", columns[w.id].damage); // fenêtre overlay plus large (style.css)
      el.classList.toggle("col-fuel", columns[w.id].consumption);
    }
    el.hidden = ONLY ? w.id !== ONLY : !w.visible;
    if (OVERLAY) {
      el.style.left = ONLY ? "0" : `${w.x}px`;
      el.style.top = ONLY ? "0" : `${w.y}px`;
      const gripActive = w.id === ONLY && resizing; // la poignée est en cours d'utilisation
      if (!gripActive) el.style.transform = `scale(${w.scale})`;
      if (w.id === ONLY && !gripActive) scale = w.scale;
      el.style.setProperty("--bg-alpha", w.background_opacity ?? cfg.background_opacity ?? 0.75);
      el.style.setProperty("--text-alpha", w.text_opacity ?? cfg.text_opacity ?? 1);
    }
  }
}

// Pont vers la fenêtre de l'overlay (Qt, objet window.lmuOverlay injecté par l'overlay) ; absent dans un navigateur.
const overlayApi = () => window.lmuOverlay;

// Mode placement (fenêtre d'un seul widget dans l'overlay) : la fenêtre se déplace en faisant glisser
// le widget et s'agrandit par la poignée en bas à droite.
let scale = 1;
let resizing = false;
let placing = false;

function setPlacement(on) {
  if (!ONLY) return;
  placing = on;
  document.body.classList.toggle("placing", on);
}

if (ONLY) {
  document.addEventListener("mousedown", (e) => {
    if (placing && e.button === 0 && !e.target.closest(".grip")) {
      e.preventDefault();
      overlayApi()?.start_move(); // déplacement natif de la fenêtre
    }
  });
}

function setupGrip() {
  if (!ONLY) return;
  const el = document.querySelector(`[data-widget="${ONLY}"]`);
  const grip = document.createElement("div");
  grip.className = "grip";
  grip.title = "Glisser pour agrandir / réduire";
  el.appendChild(grip);
  let start = null;
  let pending = null;
  const send = (s, final) => overlayApi()?.set_scale(s, final);
  grip.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation(); // sinon la fenêtre se déplacerait
    grip.setPointerCapture(e.pointerId);
    start = { x: e.screenX, y: e.screenY, scale, w: el.offsetWidth * scale, h: el.offsetHeight * scale };
    resizing = true;
  });
  grip.addEventListener("mousedown", (e) => e.stopPropagation());
  grip.addEventListener("pointermove", (e) => {
    if (!start) return;
    // Le plus grand des deux agrandissements (largeur ou hauteur), par pas de 0,05.
    const k = Math.max((start.w + e.screenX - start.x) / start.w, (start.h + e.screenY - start.y) / start.h);
    const s = +Math.min(4, Math.max(0.25, Math.round((start.scale * k) / 0.05) * 0.05)).toFixed(2);
    if (s === scale) return;
    scale = s;
    el.style.transform = `scale(${s})`;
    if (!pending) pending = requestAnimationFrame(() => ((pending = null), send(scale, false)));
  });
  const end = () => {
    if (!start) return;
    start = null;
    resizing = false;
    send(scale, true);
  };
  grip.addEventListener("pointerup", end);
  grip.addEventListener("pointercancel", end);
}
setupGrip();

// Fenêtre d'un seul widget : elle prend exactement la taille du widget (aucune zone vide sous le widget).
// Taille à l'échelle 1 (offsetWidth/Height ignorent le zoom) ; l'overlay multiplie par l'échelle.
function setupFit() {
  if (!ONLY) return;
  const el = document.querySelector(`[data-widget="${ONLY}"]`);
  let last = "";
  const send = () => {
    const size = [el.offsetWidth, el.offsetHeight];
    if (!size[1] || size.join() === last || !overlayApi()) return;
    last = size.join();
    overlayApi().fit(...size);
  };
  new ResizeObserver(send).observe(el);
  window.addEventListener("lmuoverlayready", () => ((last = ""), send()));
}
setupFit();

function loadConfig() {
  fetch("/api/config")
    .then((r) => (r.ok ? r.json() : null))
    .then((cfg) => cfg && applyConfig(cfg))
    .catch(() => {});
}

function connect() {
  // location.host = adresse utilisée par le navigateur (localhost ou IP du PC depuis une tablette).
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${scheme}://${location.host}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "snapshot") render(msg.data);
    else if (msg.type === "config") applyConfig(msg.data);
  };
  ws.onopen = loadConfig; // (re)charge la config à chaque (re)connexion
  ws.onclose = () => {
    $("status").textContent = "déconnecté";
    $("status").classList.remove("on");
    setTimeout(connect, 2000);
  };
}
connect();
