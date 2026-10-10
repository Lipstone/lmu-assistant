// Page de réglages de l'overlay (T06) : lit GET /api/config, enregistre via PUT.
const $ = (id) => document.getElementById(id);
const NAMES = { lap: "Temps au tour", delta: "Delta", fuel: "Carburant / énergie", car: "Voiture", tyres: "Pneus", brakes: "Freins", relative: "Relative", standings: "Classement", pit: "Fenêtre de stand", session: "Session et piste", damage: "Dégâts", inputs: "Inputs", stint: "Relais", weather: "Météo", shift: "Shift light" };
let config = null;
// Colonnes optionnelles des classements (dégâts, carburant, consommation, tours), désactivées par défaut sauf le
// dernier tour du Classement.
const COLUMN_WIDGETS = ["relative", "standings"];
const COLUMNS = [["show_headers", "Titres"], ["show_damage", "Dégâts"], ["show_remaining", "Restant"], ["show_consumption", "Conso"],
  ["show_penalties", "Pénalités"], ["show_compound", "Gomme"], ["show_tyre_stints", "Relais pneus"], ["show_best_lap", "Meilleur tour"], ["show_last_lap", "Dernier tour"]];

// Plage idéale de température de chaque gomme (widget Pneus), même ordre que TyreRanges (config.py).
const COMPOUNDS = [["soft", "Tendre (soft)"], ["medium", "Medium"], ["hard", "Dure (hard)"], ["inter", "Intermédiaire"], ["wet", "Pluie"]];

function buildTyreRanges() {
  $("tyre-ranges").innerHTML = COMPOUNDS.map(([k, label]) =>
    `<tr><td>${label}</td><td><input type="number" id="tyre-${k}-min" min="0" max="200"> à ` +
    `<input type="number" id="tyre-${k}-max" min="0" max="200"> °C</td></tr>`).join("");
}

function tyreRanges() {
  const old = config.tyre_ranges || {};
  return Object.fromEntries(COMPOUNDS.map(([k]) => [k,
    [num($(`tyre-${k}-min`), (old[k] || [])[0]), num($(`tyre-${k}-max`), (old[k] || [])[1])]]));
}

// Ordre des colonnes après le pilote (▲ ▼) : clé de colonne (config.COLUMN_KEYS) de chaque case, « gap » = écart
// (relative) ou intervalle (classement), toujours affiché. Même ordre par défaut que web/app.js.
const COL_OF = { show_damage: "damage", show_remaining: "remaining", show_consumption: "consumption",
  show_penalties: "penalties", show_compound: "compound", show_tyre_stints: "tyres", show_best_lap: "best", show_last_lap: "last" };
const OPT_ORDER = Object.values(COL_OF);
const DEFAULT_ORDER = { relative: [...OPT_ORDER, "gap"], standings: ["gap", ...OPT_ORDER] };
const GAP_LABEL = { relative: "Écart", standings: "Intervalle" };

function fullOrder(id, saved) {
  const order = (saved || []).filter((k) => DEFAULT_ORDER[id].includes(k));
  DEFAULT_ORDER[id].forEach((k, i) => {
    if (order.includes(k)) return;
    const prev = DEFAULT_ORDER[id].slice(0, i).reverse().find((p) => order.includes(p));
    order.splice(prev ? order.indexOf(prev) + 1 : 0, 0, k);
  });
  return order;
}

function columnsCell(id) {
  const item = (col, inner) => `<div class="col-item" data-col="${col}">${inner}` +
    `<button type="button" class="move" data-move="-1" title="Monter (plus à gauche)">▲</button>` +
    `<button type="button" class="move" data-move="1" title="Descendre (plus à droite)">▼</button></div>`;
  const items = COLUMNS.filter(([k]) => COL_OF[k]).map(([k, label]) =>
    item(COL_OF[k], `<label><input type="checkbox" data-k="${k}"> ${label}</label>`));
  items.push(item("gap", `<label class="fixed">${GAP_LABEL[id]}</label>`));
  return `<label><input type="checkbox" data-k="show_headers"> Titres</label><div class="col-order">${items.join("")}</div>`;
}

function num(input, fallback) {
  const v = parseFloat(input.value);
  return Number.isFinite(v) ? v : fallback;
}

const pct = (v) => `${Math.round(v * 100)} %`;
// Opacités par widget : null = valeur globale (curseur grisé qui suit la valeur globale).
const OPACITIES = [
  { k: "background_opacity", global: "background-opacity", min: 0 },
  { k: "text_opacity", global: "text-opacity", min: 0.1 },
];
// Valeur par widget en cours d'édition (null = globale), par id de widget puis par champ.
let own = {};

function opacityCell(o) {
  return `<td class="opa" data-opa="${o.k}">
    <input type="range" min="${o.min}" max="1" step="0.05" title="Glisser pour régler ce widget seul">
    <span class="pct"></span><button type="button" class="reset" title="Revenir à la valeur globale">↺</button></td>`;
}

// Affiche les curseurs d'opacité des widgets (valeur propre, ou globale en grisé).
function showOpacities() {
  for (const tr of $("widgets").querySelectorAll("tr")) {
    for (const o of OPACITIES) {
      const td = tr.querySelector(`[data-opa="${o.k}"]`);
      const v = own[tr.dataset.id][o.k];
      const shown = v ?? parseFloat($(o.global).value);
      td.classList.toggle("inherit", v === null);
      const range = td.querySelector("input");
      if (document.activeElement !== range) range.value = shown;
      td.querySelector(".pct").textContent = v === null ? "globale" : pct(shown);
    }
  }
  for (const o of OPACITIES) $(`${o.global}-val`).textContent = pct(parseFloat($(o.global).value));
}

// Remplit une valeur sans écraser le champ en cours d'édition (changement venu d'ailleurs pendant la saisie).
function setValue(input, value) {
  if (document.activeElement === input) return;
  if (input.type === "checkbox") input.checked = value;
  else input.value = value;
}

function fill(cfg) {
  config = cfg;
  const rows = [...$("widgets").querySelectorAll("tr")].map((tr) => tr.dataset.id);
  if (rows.join() !== cfg.widgets.map((w) => w.id).join()) {
    $("widgets").innerHTML = cfg.widgets
      .map(
        (w) => `<tr data-id="${w.id}">
          <td>${NAMES[w.id] || w.id}</td>
          <td><input type="checkbox" data-k="visible"></td>
          <td><input type="number" data-k="x"></td>
          <td><input type="number" data-k="y"></td>
          <td><input type="number" data-k="scale" min="0.25" max="4" step="0.05"></td>
          ${OPACITIES.map(opacityCell).join("")}
          <td class="cols">${COLUMN_WIDGETS.includes(w.id) ? columnsCell(w.id) : ""}</td>
        </tr>`
      )
      .join("");
  }
  for (const w of cfg.widgets) {
    const tr = $("widgets").querySelector(`tr[data-id="${w.id}"]`);
    for (const k of ["visible", "x", "y", "scale"]) setValue(tr.querySelector(`[data-k="${k}"]`), w[k]);
    for (const [k] of COLUMNS) {
      const box = tr.querySelector(`[data-k="${k}"]`);
      if (box) setValue(box, !!w[k]);
    }
    const list = tr.querySelector(".col-order");
    if (list) for (const col of fullOrder(w.id, w.column_order)) list.append(list.querySelector(`[data-col="${col}"]`));
    // Transparence en cours d'envoi : la config reçue entre-temps ne doit pas défaire le réglage en cours.
    if (!livePending) own[w.id] = { background_opacity: w.background_opacity, text_opacity: w.text_opacity };
  }
  if (!livePending) {
    setValue($("background-opacity"), cfg.background_opacity);
    setValue($("text-opacity"), cfg.text_opacity);
  }
  showOpacities();
  setValue($("hotkey"), cfg.hotkey);
  setValue($("click-through"), cfg.window.click_through);
  setValue($("placement"), cfg.placement);
  setValue($("lan-access"), cfg.lan_access);
  setValue($("fuel-mode"), cfg.fuel_mode);
  setValue($("delta-reference"), cfg.delta_reference);
  setValue($("laptime-avg-laps"), cfg.laptime_avg_laps);
  setValue($("tyre-temp-min"), cfg.tyre_temp_min_c);
  setValue($("tyre-temp-max"), cfg.tyre_temp_max_c);
  for (const [k] of COMPOUNDS) {
    const r = (cfg.tyre_ranges || {})[k] || [];
    setValue($(`tyre-${k}-min`), r[0]);
    setValue($(`tyre-${k}-max`), r[1]);
  }
  setValue($("pressure-unit"), cfg.pressure_unit);
  setValue($("tyres-show-brakes"), !!cfg.tyres_show_brakes);
  setValue($("brake-overheat"), cfg.brake_overheat_c);
  setValue($("pit-loss"), cfg.pit_loss_s);
  setValue($("shift-use-table"), cfg.shift_use_table);
  setValue($("shift-rpm-pct"), cfg.shift_rpm_pct);
  setValue($("shift-lead"), cfg.shift_lead_ms);
  setValue($("inputs-trace"), cfg.inputs_trace_s);
  setValue($("refresh-hz"), cfg.refresh_hz);
  setValue($("placement-hotkey"), cfg.placement_hotkey);
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
      ...opacities(tr.dataset.id),
      ...Object.fromEntries(COLUMNS.map(([k]) => [k, get(k) ? get(k).checked : !!old[k]])),
      column_order: tr.querySelector(".col-order")
        ? [...tr.querySelectorAll(".col-item")].map((d) => d.dataset.col) : old.column_order || [],
    };
  });
  return {
    widgets,
    ...globalOpacities(),
    hotkey: $("hotkey").value.trim() || config.hotkey,
    placement: $("placement").checked,
    lan_access: $("lan-access").checked,
    fuel_mode: $("fuel-mode").value,
    delta_reference: $("delta-reference").value,
    tyre_temp_min_c: num($("tyre-temp-min"), config.tyre_temp_min_c),
    tyre_temp_max_c: num($("tyre-temp-max"), config.tyre_temp_max_c),
    tyre_ranges: tyreRanges(),
    pressure_unit: $("pressure-unit").value,
    tyres_show_brakes: $("tyres-show-brakes").checked,
    brake_overheat_c: num($("brake-overheat"), config.brake_overheat_c),
    pit_loss_s: num($("pit-loss"), config.pit_loss_s),
    shift_use_table: $("shift-use-table").checked,
    shift_rpm_pct: num($("shift-rpm-pct"), config.shift_rpm_pct),
    shift_lead_ms: num($("shift-lead"), config.shift_lead_ms),
    inputs_trace_s: num($("inputs-trace"), config.inputs_trace_s),
    refresh_hz: Math.round(num($("refresh-hz"), config.refresh_hz)),
    laptime_avg_laps: Math.round(num($("laptime-avg-laps"), config.laptime_avg_laps)),
    placement_hotkey: $("placement-hotkey").value.trim() || config.placement_hotkey,
    window: {
      click_through: $("click-through").checked,
    },
  };
}

const opacities = (id) => ({ ...own[id] });
const globalOpacities = () => ({
  background_opacity: num($("background-opacity"), config.background_opacity),
  text_opacity: num($("text-opacity"), config.text_opacity),
});

// Transparence appliquée en direct : seuls les champs d'opacité partent, sur la dernière config enregistrée
// (les autres modifications du formulaire attendent « Enregistrer »).
let liveTimer = null;
let livePending = false;
let liveSeq = 0;
function liveOpacity() {
  showOpacities();
  livePending = true;
  const seq = ++liveSeq;
  clearTimeout(liveTimer);
  liveTimer = setTimeout(async () => {
    const body = {
      ...config,
      ...globalOpacities(),
      widgets: config.widgets.map((w) => ({ ...w, ...opacities(w.id) })),
    };
    try {
      const r = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) config = await r.json();
      else message("Transparence refusée par le serveur", true);
    } catch (e) {
      message(`Erreur : ${e}`, true);
    }
    if (seq === liveSeq) livePending = false; // pas d'autre réglage depuis
  }, 120);
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
$("background-opacity").addEventListener("input", liveOpacity);
$("text-opacity").addEventListener("input", liveOpacity);
$("widgets").addEventListener("input", (e) => {
  const td = e.target.closest("td.opa");
  if (!td) return;
  own[td.closest("tr").dataset.id][td.dataset.opa] = parseFloat(e.target.value);
  liveOpacity();
});
$("widgets").addEventListener("click", (e) => {
  if (e.target.classList.contains("move")) {
    const item = e.target.closest(".col-item");
    const to = e.target.dataset.move === "-1" ? item.previousElementSibling : item.nextElementSibling?.nextElementSibling;
    if (e.target.dataset.move === "-1" ? to : item.nextElementSibling) item.parentNode.insertBefore(item, to);
    return;
  }
  if (!e.target.classList.contains("reset")) return;
  const td = e.target.closest("td.opa");
  own[td.closest("tr").dataset.id][td.dataset.opa] = null;
  liveOpacity();
});
$("screen-w").addEventListener("input", sizePreview);
$("screen-h").addEventListener("input", sizePreview);
window.addEventListener("resize", sizePreview);

buildTyreRanges();
fetch("/api/config")
  .then((r) => r.json())
  .then(fill)
  .catch((e) => message(`Serveur injoignable : ${e}`, true));

// Changements faits ailleurs (fenêtres déplacées ou agrandies à la souris, raccourci du mode placement) :
// le formulaire suit, sinon « Enregistrer » remettrait les anciennes valeurs.
function follow() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  // réglages seulement : pas besoin des images de la course
  const ws = new WebSocket(`${scheme}://${location.host}/ws?snapshots=0`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "config") fill(msg.data);
  };
  ws.onclose = () => setTimeout(follow, 2000);
}
follow();
