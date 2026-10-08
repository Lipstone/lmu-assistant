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

function render(d) {
  $("status").textContent = d.connected ? `connecté (${d.source})` : "jeu non détecté";
  $("status").classList.toggle("on", d.connected);
  $("session").textContent = [d.session, d.track, d.car].filter(Boolean).join(" · ");
  renderLaps(d);
  renderDelta(d);
  renderFuel(d);
  $("speed").textContent = `${Math.round(d.speed_kmh)} km/h`;
  $("gear").textContent = d.gear === 0 ? "N" : d.gear < 0 ? "R" : d.gear;
  $("rpm").textContent = Math.round(d.rpm);
  $("tyres").innerHTML = d.wheels.map((w) => `<div>${Math.round(w.temp_c[1])}</div>`).join("");
}

// Configuration (T06) : visibilité partout ; position (écran), taille, opacité et fond en mode overlay.
// Fenêtre d'un seul widget : il est en haut à gauche, la fenêtre elle-même est placée par l'overlay.
// Opacité et fond : valeur du widget si définie, sinon valeur globale.
function applyConfig(cfg) {
  setPlacement(!!cfg.placement);
  fuelMode = cfg.fuel_mode || "auto";
  deltaRef = cfg.delta_reference || "best";
  for (const w of cfg.widgets || []) {
    const el = document.querySelector(`[data-widget="${w.id}"]`);
    if (!el) continue;
    el.hidden = ONLY ? w.id !== ONLY : !w.visible;
    if (OVERLAY) {
      el.style.left = ONLY ? "0" : `${w.x}px`;
      el.style.top = ONLY ? "0" : `${w.y}px`;
      const gripActive = w.id === ONLY && resizing; // la poignée est en cours d'utilisation
      if (!gripActive) el.style.transform = `scale(${w.scale})`;
      if (w.id === ONLY && !gripActive) scale = w.scale;
      el.style.opacity = w.opacity ?? cfg.opacity;
      el.style.setProperty("--bg-alpha", w.background_opacity ?? cfg.background_opacity ?? 0.75);
    }
  }
}

// Mode placement (fenêtre d'un seul widget dans l'overlay) : la fenêtre se déplace en faisant glisser
// le widget (classe reconnue par pywebview) et s'agrandit par la poignée en bas à droite.
let scale = 1;
let resizing = false;

function setPlacement(on) {
  if (!ONLY) return;
  const el = document.querySelector(`[data-widget="${ONLY}"]`);
  document.body.classList.toggle("placing", on);
  el.classList.toggle("pywebview-drag-region", on);
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
  const send = (s, final) => window.pywebview?.api?.set_scale(s, final);
  grip.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation(); // sinon pywebview déplacerait la fenêtre
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
