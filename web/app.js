// Connexion au serveur local et rendu des widgets.
const params = new URLSearchParams(location.search);
if (params.get("mode") === "overlay") document.body.classList.add("overlay");

const $ = (id) => document.getElementById(id);

function fmtLap(s) {
  if (s == null) return "–";
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(3).padStart(6, "0")}`;
}

function render(d) {
  $("status").textContent = d.connected ? `connecté (${d.source})` : "jeu non détecté";
  $("status").classList.toggle("on", d.connected);
  $("session").textContent = [d.session, d.track, d.car].filter(Boolean).join(" · ");
  $("lap").textContent = d.lap ? `${d.lap}  (P${d.position})` : "–";
  $("current").textContent = fmtLap(d.current_lap_s);
  $("last").textContent = fmtLap(d.last_lap_s);
  $("best").textContent = fmtLap(d.best_lap_s);
  $("fuel").textContent = `${d.fuel_l.toFixed(1)} L`;
  $("fuel-bar").style.width = d.fuel_capacity_l ? `${(100 * d.fuel_l) / d.fuel_capacity_l}%` : "0";
  $("speed").textContent = `${Math.round(d.speed_kmh)} km/h`;
  $("gear").textContent = d.gear === 0 ? "N" : d.gear < 0 ? "R" : d.gear;
  $("rpm").textContent = Math.round(d.rpm);
  $("tyres").innerHTML = d.wheels.map((w) => `<div>${Math.round(w.temp_c[1])}</div>`).join("");
}

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "snapshot") render(msg.data);
  };
  ws.onclose = () => {
    $("status").textContent = "déconnecté";
    $("status").classList.remove("on");
    setTimeout(connect, 2000);
  };
}
connect();
