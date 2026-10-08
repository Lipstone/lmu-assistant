// Page de réglages de l'overlay (T06) : lit GET /api/config, enregistre via PUT.
const $ = (id) => document.getElementById(id);
const NAMES = { lap: "Temps au tour", delta: "Delta", fuel: "Carburant / énergie", car: "Voiture", tyres: "Pneus", brakes: "Freins", relative: "Relative", standings: "Classement", pit: "Fenêtre de stand", session: "Session et piste" };
let config = null;

function num(input, fallback) {
  const v = parseFloat(input.value);
  return Number.isFinite(v) ? v : fallback;
}

// Champ vide = null (valeur globale).
function optNum(input) {
  const v = parseFloat(input.value);
  return Number.isFinite(v) ? v : null;
}

function fill(cfg) {
  config = cfg;
  $("widgets").innerHTML = cfg.widgets
    .map(
      (w) => `<tr data-id="${w.id}">
        <td>${NAMES[w.id] || w.id}</td>
        <td><input type="checkbox" data-k="visible" ${w.visible ? "checked" : ""}></td>
        <td><input type="number" data-k="x" value="${w.x}"></td>
        <td><input type="number" data-k="y" value="${w.y}"></td>
        <td><input type="number" data-k="scale" min="0.25" max="4" step="0.05" value="${w.scale}"></td>
        <td><input type="number" data-k="opacity" min="0.1" max="1" step="0.05" placeholder="globale" value="${w.opacity ?? ""}"></td>
        <td><input type="number" data-k="background_opacity" min="0" max="1" step="0.05" placeholder="globale" value="${w.background_opacity ?? ""}"></td>
      </tr>`
    )
    .join("");
  $("opacity").value = cfg.opacity;
  $("opacity-val").textContent = cfg.opacity;
  $("background-opacity").value = cfg.background_opacity;
  $("background-opacity-val").textContent = cfg.background_opacity;
  $("hotkey").value = cfg.hotkey;
  $("click-through").checked = cfg.window.click_through;
  $("placement").checked = cfg.placement;
  $("fuel-mode").value = cfg.fuel_mode;
  $("delta-reference").value = cfg.delta_reference;
  $("laptime-avg-laps").value = cfg.laptime_avg_laps;
  $("tyre-temp-min").value = cfg.tyre_temp_min_c;
  $("tyre-temp-max").value = cfg.tyre_temp_max_c;
  $("pressure-unit").value = cfg.pressure_unit;
  $("brake-overheat").value = cfg.brake_overheat_c;
  $("pit-loss").value = cfg.pit_loss_s;
  $("placement-hotkey").value = cfg.placement_hotkey;
  sizePreview();
}

function collect() {
  const widgets = [...$("widgets").querySelectorAll("tr")].map((tr) => {
    const old = config.widgets.find((w) => w.id === tr.dataset.id);
    const get = (k) => tr.querySelector(`[data-k="${k}"]`);
    return {
      id: tr.dataset.id,
      visible: get("visible").checked,
      x: Math.round(num(get("x"), old.x)),
      y: Math.round(num(get("y"), old.y)),
      scale: num(get("scale"), old.scale),
      opacity: optNum(get("opacity")),
      background_opacity: optNum(get("background_opacity")),
    };
  });
  return {
    widgets,
    opacity: num($("opacity"), config.opacity),
    background_opacity: num($("background-opacity"), config.background_opacity),
    hotkey: $("hotkey").value.trim() || config.hotkey,
    placement: $("placement").checked,
    fuel_mode: $("fuel-mode").value,
    delta_reference: $("delta-reference").value,
    tyre_temp_min_c: num($("tyre-temp-min"), config.tyre_temp_min_c),
    tyre_temp_max_c: num($("tyre-temp-max"), config.tyre_temp_max_c),
    pressure_unit: $("pressure-unit").value,
    brake_overheat_c: num($("brake-overheat"), config.brake_overheat_c),
    pit_loss_s: num($("pit-loss"), config.pit_loss_s),
    laptime_avg_laps: Math.round(num($("laptime-avg-laps"), config.laptime_avg_laps)),
    placement_hotkey: $("placement-hotkey").value.trim() || config.placement_hotkey,
    window: {
      click_through: $("click-through").checked,
    },
  };
}

// Aperçu : l'écran entier en mode overlay, réduit à la largeur de la page.
function sizePreview() {
  const w = num($("screen-w"), 1920);
  const h = num($("screen-h"), 1080);
  const k = Math.min(1, ($("preview-box").parentElement.clientWidth - 28) / w);
  $("preview").width = w;
  $("preview").height = h;
  $("preview").style.transform = `scale(${k})`;
  $("preview-box").style.width = `${w * k}px`;
  $("preview-box").style.height = `${h * k}px`;
}

function message(text, error = false) {
  $("msg").textContent = text;
  $("msg").className = error ? "error" : "";
}

async function save() {
  try {
    const r = await fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collect()),
    });
    const body = await r.json();
    if (!r.ok) {
      const details = Array.isArray(body.detail)
        ? body.detail.map((d) => `${d.loc.slice(1).join(".")} : ${d.msg}`).join(" ; ")
        : body.detail;
      message(`Refusé : ${details || r.status}`, true);
      return;
    }
    fill(body);
    message("Enregistré.");
  } catch (e) {
    message(`Erreur : ${e}`, true);
  }
}

$("save").addEventListener("click", save);
$("opacity").addEventListener("input", () => ($("opacity-val").textContent = $("opacity").value));
$("background-opacity").addEventListener("input", () => ($("background-opacity-val").textContent = $("background-opacity").value));
$("screen-w").addEventListener("input", sizePreview);
$("screen-h").addEventListener("input", sizePreview);
window.addEventListener("resize", sizePreview);

fetch("/api/config")
  .then((r) => r.json())
  .then(fill)
  .catch((e) => message(`Serveur injoignable : ${e}`, true));

// Changements faits ailleurs (fenêtres déplacées ou agrandies à la souris, raccourci du mode placement) :
// le formulaire suit, sinon « Enregistrer » remettrait les anciennes valeurs.
function follow() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${scheme}://${location.host}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "config") fill(msg.data);
  };
  ws.onclose = () => setTimeout(follow, 2000);
}
follow();
