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
