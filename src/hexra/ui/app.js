"use strict";
const TOKEN = document.querySelector('meta[name="hexra-token"]').content;
const $ = (s, r = document) => r.querySelector(s);
const main = $("#main"), nav = $("#nav"), saveBtn = $("#save"), toastEl = $("#toast");
const camCard = $("#cam-card"), camView = camCard.querySelector(".cam-view"), sideSlot = $("#cam-slot-side");
let camWhere = "side";
const ICONS = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  cursor: "M5 3l14 7-6 2-2 6z",
  click: "M9 3v10l3-2 3 6 2-1-3-6h4zM4 4l2 2M3 9h3",
  window: "M3 5h18v14H3zM3 9h18M7 7h.01",
  hand: "M8 13V5a1.5 1.5 0 013 0v6M11 11V3.5a1.5 1.5 0 013 0V11M14 11V5a1.5 1.5 0 013 0v8a7 7 0 01-7 7h-1a6 6 0 01-5-3l-2-4a1.5 1.5 0 012.4-1.6L8 14",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 100 6 3 3 0 000-6z",
  camera: "M3 8h4l2-3h6l2 3h4v11H3zM12 11a3.5 3.5 0 100 7 3.5 3.5 0 000-7z",
  pulse: "M3 12h4l3-8 4 16 3-8h4",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z", scale: "M12 3v18M5 7h14M5 7l-3 7a3 3 0 006 0zM19 7l-3 7a3 3 0 006 0z", anchor: "M12 4v16M8 8h8M4 14a8 8 0 0016 0M12 4a1.5 1.5 0 100 .01", screen: "M3 4h18v12H3zM8 20h8M12 16v4"
};
const state = { cams: null, camsBusy: false, eng: { running: false }, schema: null, saved: {}, draft: {}, defaults: {}, info: {}, page: "overview", q: "", advanced: false, errors: {}, running: false };

try { state.advanced = localStorage.getItem("hexra-advanced") === "1"; } catch (e) {}

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") throw new Error("no raw html");
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
function icon(name) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", ICONS[name] || ICONS.home); s.append(p); return s;
}
async function api(path, body) {
  const r = await fetch(path, { method: body === undefined ? "GET" : "POST", headers: { "X-Hexra-Token": TOKEN, "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => ({ error: "unreadable reply" }));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
let toastTimer;
function toast(msg, bad) {
  toastEl.textContent = msg; toastEl.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => toastEl.className = "toast", bad ? 6000 : 2600);
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const allSettings = () => state.schema.groups.flatMap(g => g.settings);
const byId = id => allSettings().find(s => s.id === id);
const changedIds = () => Object.keys(state.draft).filter(k => !same(state.draft[k], state.saved[k]));
const fmtNum = (s, v) => v == null ? "" : (s.precision != null ? Number(v).toFixed(s.precision) : String(v));
const ms = x => x < 1000 ? `${Math.round(x)} ms` : `${(x / 1000).toFixed(x % 1000 ? 1 : 0)} s`;

// ---------------------------------------------------------------- controls
function setValue(id, v) {
  state.draft[id] = v; delete state.errors[id];
  if (id === "camera.use" && v.length > 1 && state.draft["attention.enabled"]) state.draft["attention.enabled"] = false;   // the server does the same
  render(true);
}

function numberControl(s) {
  const v = state.draft[s.id];
  if (v == null) {
    return h("div", { class: "ctrl" }, h("span", { class: "val muted" }, "Preset in use"), h("button", { class: "btn", onclick: () => setValue(s.id, Math.round((s.min + (s.max - s.min) / 4) / s.step) * s.step) }, "Set a custom value"));
  }
  const range = h("input", { type: "range", min: s.min, max: s.max, step: s.step, value: v, "aria-label": s.label });
  const box = h("input", { type: "number", class: "num", min: s.min, max: s.max, step: s.step, value: fmtNum(s, v), "aria-label": s.label + " value" });
  range.addEventListener("input", () => { state.draft[s.id] = Number(range.value); box.value = fmtNum(s, range.value); refreshCard(s); });
  range.addEventListener("change", () => render(true));
  box.addEventListener("change", () => { const n = Number(box.value); if (box.value !== "" && !isNaN(n)) setValue(s.id, Math.min(s.max, Math.max(s.min, n))); });
  return h("div", { class: "ctrl" }, range, box, h("span", { class: "muted" }, s.unit), s.default == null ? h("button", { class: "btn link", onclick: () => setValue(s.id, null) }, "Use preset") : null);
}
function enumControl(s) {
  const v = state.draft[s.id];
  return h("div", { class: "seg", role: "group", "aria-label": s.label }, s.options.map(o =>
    h("button", { "aria-pressed": same(o.value, v) ? "true" : "false", onclick: () => setValue(s.id, o.value) }, o.label)));
}
function boolControl(s) {
  const on = state.draft[s.id];
  return h("div", { class: "ctrl" }, h("button", { class: "toggle", role: "switch", "aria-checked": on ? "true" : "false", "aria-label": s.label, onclick: () => setValue(s.id, !on) }), h("span", { class: "val" }, on ? "On" : "Off"));
}
function actionControl(s) {
  const sel = h("select", { "aria-label": s.label }, state.schema.actions.map(a => h("option", { value: a.value, selected: a.value === state.draft[s.id] }, a.label)));
  sel.addEventListener("change", () => setValue(s.id, sel.value));
  return sel;
}
function regionControl(s) {
  const v = state.draft[s.id], labels = ["Left", "Top", "Right", "Bottom"];
  const preview = h("div", { class: "region" }, h("div", { style: `left:${v[0] * 100}%;top:${v[1] * 100}%;width:${(v[2] - v[0]) * 100}%;height:${(v[3] - v[1]) * 100}%` }));
  const boxes = labels.map((l, i) => {
    const inp = h("input", { type: "number", class: "num", min: 0, max: 1, step: 0.05, value: v[i], "aria-label": "Active box " + l.toLowerCase() });
    inp.addEventListener("change", () => { const n = Number(inp.value); if (isNaN(n)) return; const nv = v.slice(); nv[i] = Math.min(1, Math.max(0, n)); setValue(s.id, nv); });
    return h("label", { class: "small muted" }, l, h("br"), inp);
  });
  return h("div", { class: "ctrl" }, preview, h("div", { class: "ctrl" }, boxes), h("span", { class: "muted small" }, "0 = left / top of the camera picture, 1 = right / bottom"));
}
function cameraControl(s) {
  const use = state.draft[s.id] || [0], found = state.cams;
  const toggle = (i) => {
    let next = use.includes(i) ? use.filter(x => x !== i) : [...use, i].slice(-2);
    if (!next.length) return toast("Keep at least one camera selected.", true);
    setValue(s.id, next.sort());
  };
  const detect = async () => {
    state.camsBusy = true; render(true);
    try { state.cams = (await api("/api/cameras")).cameras; if (!state.cams.length) toast("No cameras found.", true); }
    catch (e) { toast(e.message, true); }
    state.camsBusy = false; render(true);
  };
  const tiles = found ? found.map(c => h("label", { class: "camtile" + (use.includes(c.index) ? " on" : "") },
    c.thumb ? h("img", { src: c.thumb, alt: `Camera ${c.index + 1} preview` }) : h("div", { class: "camnone" }, "no picture"),
    h("span", {}, h("input", { type: "checkbox", checked: use.includes(c.index), onchange: () => toggle(c.index) }), ` Camera ${c.index + 1}`, h("small", { class: "muted" }, c.width ? `  ${c.width}×${c.height}` : "")))) : null;
  return h("div", {},
    h("div", { class: "ctrl" },
      h("button", { class: "btn", disabled: state.camsBusy || state.eng.running, onclick: detect }, state.camsBusy ? "Looking…" : "Detect cameras"),
      h("span", { class: "muted" }, "Using: " + use.map(i => `Camera ${i + 1}`).join(" + ") + (use.length > 1 ? " (fused)" : "")),
      state.eng.running ? h("span", { class: "muted small" }, "Stop Hexra to detect cameras.") : null),
    tiles ? h("div", { class: "camgrid" }, tiles) : null,
    use.length > 1 ? h("p", { class: "desc", style: "margin:10px 0 0" }, "Both cameras track your hand together. Raise your hand where both can see it and move it around for a few seconds: Hexra learns how the two views line up by itself, and the sidebar then says “fused”.") : null);
}
function control(s) {
  return { number: numberControl, enum: enumControl, bool: boolControl, action: actionControl, region: regionControl, cameras: cameraControl }[s.type](s);
}

function card(s) {
  const v = state.draft[s.id], changed = !same(v, state.saved[s.id]);
  const twoCams = (state.draft["camera.use"] || [0]).length > 1 && s.id.startsWith("attention.");
  const locked = (s.requires === "face_models" && !state.info.face_models) || twoCams;
  const reset = !same(v, s.default) && s.type !== "action" ? h("button", { class: "btn link", onclick: () => setValue(s.id, s.default) }, "Reset") : null;
  const el = h("div", { class: "setting" + (changed ? " changed" : "") + (locked ? " lock" : ""), "data-id": s.id },
    h("div", { class: "row" }, h("div", {}, h("div", { class: "name" }, s.label), h("div", { class: "desc" }, s.desc)),
      h("div", { class: "def" }, s.type === "number" || s.type === "bool" ? `Default: ${s.default == null ? "preset" : s.type === "bool" ? (s.default ? "On" : "Off") : fmtNum(s, s.default) + (s.unit ? " " + s.unit : "")}` : "", reset)),
    locked ? h("div", { class: "err" }, twoCams ? "Switched off while two cameras are used: the face-direction check needs one camera that faces you." : "The face-recognition model is not installed, so this cannot be switched on. It is not part of the standard installer.") : control(s),
    s.type === "enum" ? h("div", { class: "desc", style: "margin:8px 0 0" }, (s.options.find(o => o.value === v) || s.options[0]).desc) : null,
    state.errors[s.id] ? h("div", { class: "err", role: "alert" }, state.errors[s.id]) : null);
  return el;
}
function refreshCard(s) {
  const el = main.querySelector(`[data-id="${CSS.escape(s.id)}"]`); if (!el) return;
  updateSave();
}

// ---------------------------------------------------------------- pages
function header(title, sub) { return [h("h1", {}, title), h("p", { class: "sub" }, sub)]; }
function matches(s, q) { return (s.label + " " + s.desc + " " + s.id).toLowerCase().includes(q); }

function startupCard() {
  const a = state.info.autostart || {};
  return h("div", { class: "card" }, h("div", { class: "row" }, h("div", {}, h("h2", {}, "Start with Windows"),
      h("p", { class: "muted", style: "margin:2px 0 0" }, a.available ? "Hexra starts quietly in the system tray when you log in, with no window. Open it from the tray icon. Turn on Start hand control automatically (Startup page) to also switch the camera on." : "Only available in the installed Hexra.")),
    h("div", { class: "ctrl" }, h("button", { class: "toggle", role: "switch", "aria-checked": a.enabled ? "true" : "false", "aria-label": "Start with Windows", disabled: !a.available,
      onclick: async () => { try { const r = await api("/api/autostart", { enabled: !a.enabled }); state.info.autostart.enabled = r.enabled; render(true); toast(r.enabled ? "Hexra will start with Windows." : "Hexra will no longer start with Windows."); } catch (e) { toast(e.message, true); } } }),
      h("span", { class: "val" }, a.enabled ? "On" : "Off"))));
}
function overview() {
  const d = state.draft;
  const presets = state.schema.presets.map(p => {
    const on = Object.entries(p.values).every(([k, v]) => same(d[k], v));
    return h("button", { class: "preset", "aria-pressed": on ? "true" : "false", onclick: () => { Object.assign(state.draft, p.values); render(true); toast(`${p.label} preset applied. Save to keep it.`); } },
      h("b", { style: "display:flex;gap:8px;align-items:center" }, icon(p.icon), p.label), h("span", {}, p.desc));
  });
  return [...header("Make Hexra yours.", "Every setting in one place, explained in plain words."),
    h("div", { class: "card" }, h("div", { class: "row" }, h("div", {}, h("h2", {}, state.eng.running ? "Hexra is running" : "Hexra is not running"), h("p", { class: "muted", style: "margin:2px 0 0" }, state.eng.running ? "Saving a change restarts Hexra for a moment so it takes effect at once." : "Press Start Hexra under the camera in the sidebar.")))),
    h("div", { class: "card" }, h("h2", {}, "Start from a preset"), h("p", { class: "muted", style: "margin:0 0 12px" }, "A preset only changes a few settings. You can fine-tune everything afterwards."), h("div", { class: "grid g4" }, presets)),
    startupCard(),
    h("div", { class: "card" }, h("h2", {}, "Housekeeping"), h("div", { class: "tools", style: "margin-top:10px" },
      h("button", { class: "btn", onclick: resetAll }, "Reset everything to defaults"),
      h("button", { class: "btn", onclick: restoreBackup }, "Go back to the previous saved version"),
      h("span", { class: "muted small" }, "Settings file: " + (state.info.paths || {}).config)))];
}
function groupPage(g) {
  const list = g.settings.filter(s => state.advanced || !s.advanced || changedIds().includes(s.id));
  const hidden = g.settings.length - list.length;
  return [...header(g.label, g.desc),
    h("div", { class: "card" }, g.id === "gestures" ? gesturesList(list) : list.map(card),
      hidden ? h("p", { class: "muted small", style: "margin:14px 0 0" }, `${hidden} more advanced setting${hidden > 1 ? "s" : ""} hidden. `, h("button", { class: "btn link", onclick: () => { state.advanced = true; persistAdv(); render(true); } }, "Show advanced")) : null)];
}
function gesturesList(list) {
  return [h("p", { class: "muted small", style: "margin:0 0 6px" }, "Move your hand to steer the cursor with the open palm. The cursor always follows the hand; these assign what each pose does. Window commands use the hold times on the Windows page."),
    ...list.map(s => {
      const pose = state.schema.poses.find(p => p.id === s.pose), v = state.draft[s.id];
      return h("div", { class: "pose", "data-id": s.id }, h("div", {}, h("div", { class: "t" }, s.label), h("div", { class: "h" }, pose.how)), actionControl(s));
    })];
}
function searchPage() {
  const q = state.q.toLowerCase();
  const hits = allSettings().filter(s => matches(s, q));
  return [...header("Search results", hits.length ? `${hits.length} setting${hits.length > 1 ? "s" : ""} match “${state.q}”.` : `Nothing matches “${state.q}”.`),
    hits.length ? h("div", { class: "card" }, hits.map(s => h("div", {}, h("div", { class: "def", style: "margin-top:6px" }, state.schema.groups.find(g => g.settings.includes(s)).label), card(s)))) : null];
}
let logTimer;
function activityPage() {
  const run = h("pre", { class: "log" }, "Loading…"), err = h("pre", { class: "log", style: "margin-top:10px", hidden: true });
  const load = async () => { try { const j = await api("/api/log"); run.textContent = j.run || "No run log yet. Start Hexra once and it will appear here."; err.hidden = !j.error; err.textContent = j.error; } catch (e) { run.textContent = "Could not read the log: " + e.message; } };
  load(); clearInterval(logTimer); logTimer = setInterval(() => { if (state.page !== "activity") clearInterval(logTimer); else load(); }, 3000);
  const rows = [["Settings file", state.info.paths.config], ["Run log", state.info.paths.log], ["Version", state.info.version || "development build"], ["Latest save backup", state.info.paths.config + ".bak"]];
  return [...header("Activity", "What Hexra did the last time it ran, and where things live."),
    h("div", { class: "card" }, h("h2", {}, "Last run"), h("p", { class: "muted small" }, "Updates every few seconds. Poses and events only; no pictures are ever stored."), run, err),
    h("div", { class: "card" }, h("h2", {}, "Files"), h("table", { class: "table" }, rows.map(([a, b]) => h("tr", {}, h("th", {}, a), h("td", {}, b)))))];
}

function wantCam() { return "side"; }          // the camera always lives at the bottom of the sidebar
function placeCamera(before) {
  const want = wantCam(), slot = want === "main" ? $("#cam-slot-main") : sideSlot;
  if (slot && camCard.parentElement !== slot) slot.append(camCard);
  camCard.classList.toggle("big", want === "main");
  if (!before || want === camWhere) { camWhere = want; return; }
  camWhere = want;
  const after = camView.getBoundingClientRect();
  if (!after.width || !before.width || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  // FLIP: the picture starts exactly where it was (same position and size) and glides to its new place
  camView.style.transformOrigin = "0 0";
  camView.animate([{ transform: `translate(${before.left - after.left}px, ${before.top - after.top}px) scale(${before.width / after.width}, ${before.height / after.height})` }, { transform: "none" }],
    { duration: 480, easing: "cubic-bezier(.2,.8,.2,1)" });
  camCard.querySelectorAll(".cam-status,.cam-note,.cam-btns,.cam-try").forEach(el => el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 380, delay: 120, easing: "ease-out", fill: "backwards" }));
}
function render(keepScroll) {
  const top = main.scrollTop;
  const before = camView.getBoundingClientRect();
  if (camCard.parentElement !== sideSlot) sideSlot.append(camCard);        // keep the camera alive while the page is rebuilt
  const page = state.q ? searchPage() : state.page === "overview" ? overview() : state.page === "activity" ? activityPage() : groupPage(state.schema.groups.find(g => g.id === state.page));
  const tools = state.page !== "activity" || state.q ? h("div", { class: "tools" },
    h("input", { class: "search", type: "search", placeholder: "Search every setting…", value: state.q, "aria-label": "Search settings", id: "q" }),
    h("label", { class: "switch-row" }, h("button", { class: "toggle", role: "switch", "aria-checked": state.advanced ? "true" : "false", "aria-label": "Show advanced settings", onclick: () => { state.advanced = !state.advanced; persistAdv(); render(true); } }), "Advanced")) : null;
  main.replaceChildren(h("div", { class: "page" }, page[0], page[1], tools, ...page.slice(2)));
  const q = $("#q");
  if (q) { const wasFocus = state.focusQ; q.addEventListener("input", () => { state.q = q.value.trim(); state.focusQ = true; render(true); }); if (wasFocus) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }
  state.focusQ = false;
  if (keepScroll) main.scrollTop = top;
  placeCamera(before);
  renderNav(); updateSave();
}
function persistAdv() { try { localStorage.setItem("hexra-advanced", state.advanced ? "1" : "0"); } catch (e) {} }

function renderNav() {
  const ch = changedIds();
  const items = [["overview", "Overview", "home"], ...state.schema.groups.map(g => [g.id, g.label, g.icon]), ["activity", "Activity", "pulse"]];
  nav.replaceChildren(...items.map(([id, label, ic]) => {
    const n = id === "overview" || id === "activity" ? 0 : state.schema.groups.find(g => g.id === id).settings.filter(s => ch.includes(s.id)).length;
    return h("button", { "aria-current": state.page === id && !state.q ? "page" : "false", onclick: () => { state.page = id; state.q = ""; render(false); main.scrollTop = 0; main.focus(); } }, icon(ic), label, n ? h("span", { class: "badge-n" }, n) : null);
  }));
}
function updateSave() {
  const n = changedIds().length;
  saveBtn.disabled = n === 0;
  saveBtn.textContent = n ? `Save changes (${n})` : "Save changes";
}

// ---------------------------------------------------------------- actions
async function save() {
  const ids = changedIds(); if (!ids.length) return true;
  const values = Object.fromEntries(ids.map(k => [k, state.draft[k]]));
  try {
    const r = await api("/api/save", { values });
    state.saved = r.values; state.draft = JSON.parse(JSON.stringify(r.values)); state.errors = {};
    render(true);
    if (state.eng.running) { toast("Saved. Restarting Hexra with your settings…"); await engineStart(state.eng.dry, true); }
    else toast(`Saved ${ids.length} change${ids.length > 1 ? "s" : ""}.`);
    return true;
  } catch (e) { toast(e.message, true); return false; }
}
async function engineStart(dry, restart) {
  try { await api("/api/engine/start", { dry, restart }); await pollStatus(); }
  catch (e) { toast(e.message, true); }
}
async function onStartStop() {
  if (state.eng.running) { try { await api("/api/engine/stop", {}); } catch (e) { toast(e.message, true); } await pollStatus(); return; }
  if (!await save()) return;
  if (!state.eng.running) await engineStart($("#cam-dry").checked, false);
}
async function pollStatus() {
  try { state.eng = await api("/api/status"); } catch (e) { state.eng = { running: false, error: "Lost contact with the Hexra window. Close it and open Hexra again." }; }
  updateCam();
}
let camOn = false;
function updateCam() {
  const e = state.eng, img = $("#cam"), chip = $("#cam-chip"), text = $("#cam-text"), note = $("#cam-note");
  if (e.running && !camOn) { img.src = `/preview.mjpg?t=${encodeURIComponent(TOKEN)}&n=${Date.now()}`; camOn = true; }
  if (!e.running && camOn) { img.removeAttribute("src"); camOn = false; }
  img.hidden = !e.running; $("#cam-off").hidden = !!e.running;
  $("#cam-dry").disabled = !!e.running;
  $("#cam-start").textContent = e.running ? "Stop" : "Start Hexra";
  $("#cam-start").className = e.running ? "btn" : "btn primary";
  const tg = $("#cam-toggle"); tg.hidden = !e.running || e.dry || e.starting; tg.textContent = e.engaged ? "Pause" : "Resume";
  let label = "Off", t = "neutral", more = "";
  if (e.running) {
    if (e.starting) { label = "Starting…"; }
    else if (e.dry) { label = "Try-it mode"; }
    else if (e.engaged) { label = "Controlling"; t = "good"; }
    else { label = "Paused"; t = "warn"; }
    if (!e.starting) more = `${e.pose || "no hand"} · ${e.fps || 0} fps` + (e.cams ? ` · ${e.cams}` : "");
  } else if (e.exit_code) { label = "Stopped"; t = "warn"; }
  chip.className = "chip " + t; chip.textContent = label; text.textContent = more;
  $("#cam-status").hidden = !e.running && !e.exit_code;      // when it is off the picture area already says so
  let msg = "";
  if (e.running && e.away) msg = "Looking away: gestures paused.";
  else if (e.running && e.asleep) msg = "Asleep. Raise an open palm in the air to wake.";
  else if (e.running && e.note) msg = e.note;
  else if (!e.running && e.error) msg = e.error;
  else if (!e.running && e.exit_code) msg = "Hexra stopped unexpectedly. See Activity for details.";
  note.hidden = !msg; note.textContent = msg;
  if (state.page === "overview" && !state.q && state.lastRunning !== !!e.running) { state.lastRunning = !!e.running; render(true); }
}

function resetAll() {
  if (!confirm("Put every setting back to its default? Nothing is saved until you press Save changes.")) return;
  state.draft = JSON.parse(JSON.stringify(state.defaults)); state.draft["face_lock.enabled"] = state.saved["face_lock.enabled"] && state.info.face_models ? state.draft["face_lock.enabled"] : false; render(true); toast("Defaults loaded. Press Save changes to keep them.");
}
async function restoreBackup() {
  if (!confirm("Go back to the version of your settings from before your last save?")) return;
  try { const r = await api("/api/restore-backup", {}); state.saved = r.values; state.draft = JSON.parse(JSON.stringify(r.values)); render(true); toast("Previous version restored."); } catch (e) { toast(e.message, true); }
}

saveBtn.addEventListener("click", save);
document.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); } });
window.addEventListener("beforeunload", e => { if (changedIds().length) { e.preventDefault(); e.returnValue = ""; } });
setInterval(() => api("/api/ping", {}).catch(() => {}), 8000);
setInterval(pollStatus, 1000);
$("#cam-start").addEventListener("click", onStartStop);
$("#cam-toggle").addEventListener("click", async () => { try { await api("/api/engine/toggle", {}); } catch (e) { toast(e.message, true); } });
window.addEventListener("pagehide", () => { try { navigator.sendBeacon("/api/closing?t=" + encodeURIComponent(TOKEN), "{}"); } catch (e) {} });

(async function start() {
  try {
    const s = await api("/api/state");
    state.schema = s.schema; state.saved = s.values; state.draft = JSON.parse(JSON.stringify(s.values)); state.defaults = s.defaults; state.info = s; state.eng = s.engine;
    const want = decodeURIComponent(location.hash.slice(1));
    if (want === "activity" || state.schema.groups.some(g => g.id === want)) state.page = want;
    render(false);
  } catch (e) { main.replaceChildren(h("div", { class: "page" }, h("h1", {}, "Settings could not load"), h("p", { class: "sub" }, e.message))); }
})();
