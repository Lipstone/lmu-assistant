// Page de réglages de l'overlay (T06) : lit GET /api/config, enregistre via PUT.
const $ = (id) => document.getElementById(id);
const NAMES = { lap: "Tour", fuel: "Carburant", car: "Voiture", tyres: "Pneus" };
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
        <td><input type="number" data-k="x" min="0" value="${w.x}"></td>
        <td><input type="number" data-k="y" min="0" value="${w.y}"></td>
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
  $("win-x").value = cfg.window.x;
  $("win-y").value = cfg.window.y;
  $("win-width").value = cfg.window.width;
  $("win-height").value = cfg.window.height;
  $("click-through").checked = cfg.window.click_through;
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
    window: {
      x: Math.round(num($("win-x"), config.window.x)),
      y: Math.round(num($("win-y"), config.window.y)),
      width: Math.round(num($("win-width"), config.window.width)),
      height: Math.round(num($("win-height"), config.window.height)),
      click_through: $("click-through").checked,
    },
  };
}

function sizePreview() {
  $("preview").width = num($("win-width"), 400);
  $("preview").height = num($("win-height"), 420);
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
$("win-width").addEventListener("input", sizePreview);
$("win-height").addEventListener("input", sizePreview);

fetch("/api/config")
  .then((r) => r.json())
  .then(fill)
  .catch((e) => message(`Serveur injoignable : ${e}`, true));
