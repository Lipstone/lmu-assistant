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

// F01 : carburant (les calculs viennent du serveur, voir backend/lmu_assistant/fuel.py)
function renderFuel(d) {
  const f = d.fuel || {};
  $("fuel").textContent = `${d.fuel_l.toFixed(1)} L`;
  $("fuel-bar").style.width = d.fuel_capacity_l ? `${(100 * d.fuel_l) / d.fuel_capacity_l}%` : "0";
  $("fuel-last").textContent = fmt(f.last_lap_l, 2, " L");
  $("fuel-avg").textContent = f.avg_lap_l == null ? "–" : `${f.avg_lap_l.toFixed(2)} L (${f.valid_laps})`;
  $("fuel-laps").textContent = fmt(f.laps_left, 1);
  $("fuel-finish").textContent = fmt(f.laps_to_finish, 1);
  $("fuel-add").textContent = f.to_add_l == null ? "–" : f.to_add_l > 0 ? `+${fmt(f.to_add_l, 1, " L")}` : "assez";
  const low = f.laps_left != null && f.laps_left < 2;
  $("fuel-laps").classList.toggle("alert", low);
  $("fuel-bar").classList.toggle("alert", low);
  $("fuel-add").classList.toggle("good", f.to_add_l === 0);
}

function render(d) {
  $("status").textContent = d.connected ? `connecté (${d.source})` : "jeu non détecté";
  $("status").classList.toggle("on", d.connected);
  $("session").textContent = [d.session, d.track, d.car].filter(Boolean).join(" · ");
  $("lap").textContent = d.lap ? `${d.lap}  (P${d.position})` : "–";
  $("current").textContent = fmtLap(d.current_lap_s);
  $("last").textContent = fmtLap(d.last_lap_s);
  $("best").textContent = fmtLap(d.best_lap_s);
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
  for (const w of cfg.widgets || []) {
    const el = document.querySelector(`[data-widget="${w.id}"]`);
    if (!el) continue;
    el.hidden = ONLY ? w.id !== ONLY : !w.visible;
    if (OVERLAY) {
      el.style.left = ONLY ? "0" : `${w.x}px`;
      el.style.top = ONLY ? "0" : `${w.y}px`;
      el.style.transform = `scale(${w.scale})`;
      el.style.opacity = w.opacity ?? cfg.opacity;
      el.style.setProperty("--bg-alpha", w.background_opacity ?? cfg.background_opacity ?? 0.75);
    }
  }
}

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
