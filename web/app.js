const $ = id => document.getElementById(id);
const chart = QVFrame.mount($("chart"));
const SAMPLE_ROWS = 5;
const MAX_VALUES = 60;
let seq = 0, ctrl = null;
const state = {data: null, auto: null, decide: null, names: null, recipe: null, undo: [], chat: [], opts: [], spec: null, busy: false, drawing: false, view: 1, reached: 1,
  style: "franri", orient: null, keepId: null};
const KEEP_V = 1, KEEP_MS = 7 * 864e5;
const keepBox = {timer: 0, data: null, id: null, off: false};
const LAYOUT = ["legend", "legendPos", "legendDir", "legendSort", "tickAngle", "grid", "valueMin", "valueMax", "valueLog", "xMin", "xMax", "xLog", "ticks",
  "fontSize", "barGap", "lineWidth", "markers", "curve", "titleAlign", "refLine", "refLabel", "trendline", "pointSize", "donutHole", "height",
  "textHalo", "textColor", "background", "border", "padding", "labelMax", "thousands", "decimalMark", "numberStyle", "axisTitles", "opacity",
  "lineStyle", "dashed", "markerShape", "titleSize", "flags", "shade", "fontStyle", "dimSize", "controls", "logo"];
const AXIS_FIELDS = ["valueMin", "valueMax", "valueLog", "xMin", "xMax", "xLog", "refLine", "refLabel"];

const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const clone = o => JSON.parse(JSON.stringify(o));
const KIND_NAMES = {bar: "Bar", line: "Line", stacked_area: "Stacked area", stacked_bar: "Stacked bar", scatter: "Scatter", histogram: "Histogram",
  heatmap: "Heatmap", treemap: "Treemap", donut: "Donut", sankey: "Sankey", bump: "Ranking", dot_range: "Dot range", map: "Map"};

class CapError extends Error {}

async function api(path, {json, body, signal, method = "POST", headers = {}} = {}) {
  const opts = {method, signal, credentials: "same-origin", headers: {...headers}};
  if (json !== undefined) { opts.body = JSON.stringify(json); opts.headers["Content-Type"] = "application/json"; }
  else if (body !== undefined) opts.body = body;
  const r = await fetch(path, opts);
  let j = null;
  try { j = await r.json(); } catch (e) { }
  if (window.QVCredits && method !== "GET") QVCredits.refresh();
  if (r.status === 429 && j && j.detail && j.detail.reason === "rate") throw new Error(j.detail.message);
  if (r.status === 429) { showCap(j && j.detail); throw new CapError("cap"); }
  if (!r.ok) {
    const d = j && j.detail;
    const msg = typeof d === "string" ? d : d && d.message ? d.message : r.status === 413 ? "That is too large for the server." : `Something went wrong (${r.status}).`;
    const e = new Error(msg);
    e.detail = d;
    throw e;
  }
  return j;
}

function setErr(msg) { $("err").textContent = msg || ""; $("err").hidden = !msg; }
function setStatus(msg, busy) {
  $("status").textContent = msg || "";
  document.body.classList.toggle("busy", !!busy);
  $("frame").setAttribute("aria-busy", String(!!busy));
}

const STEP_NAMES = {1: "Upload", 2: "Preview", 3: "Adjust", 4: "Export"};
const VIEWS = {1: ["step-data"], 2: ["step-ask", "stage"], 3: ["stage", "step-chat"], 4: ["stage"]};
const NEXT_HINT = {1: "Load a file or describe a chart to go on.", 2: "Next lights up once the chart is drawn."};

function stepDone(n) {
  if (n === 1) return !!state.data || !!mockShown;
  if (n === 2) return state.auto === "done" && !state.drawing;
  if (n === 3) return !!state.recipe;
  return false;
}

function paintSteps() {
  const b = document.body;
  [1, 2, 3, 4].forEach(n => b.classList.toggle("view-" + n, state.view === n));
  b.classList.toggle("has-data", !!state.data);
  b.classList.toggle("has-chart", !!state.recipe);
  document.querySelectorAll("#stepper .st").forEach(li => {
    const n = +li.dataset.step, btn = li.querySelector("button");
    const cur = n === state.view, done = !cur && n <= state.reached;
    li.classList.toggle("current", cur);
    li.classList.toggle("done", done);
    btn.setAttribute("aria-disabled", String(!done));
    if (cur) btn.setAttribute("aria-current", "step"); else btn.removeAttribute("aria-current");
    btn.setAttribute("aria-label", `Step ${n}, ${STEP_NAMES[n]}${cur ? ", current" : done ? ", done, go back to it" : ", not reached yet"}`);
  });
  document.querySelectorAll("#stepper .chev").forEach((c, i) => c.classList.toggle("lit", i + 2 <= state.reached));
  $("restart").hidden = !state.data;
  $("stage-mock").hidden = !isMock();
  if (!state.data) $("restart-ask").hidden = true;
  const ok = stepDone(state.view);
  $("next-row").hidden = state.view === 4;
  $("next").disabled = !ok;
  $("next").title = ok ? "" : NEXT_HINT[state.view] || "";
  $("next").setAttribute("aria-label", ok ? `Next, step ${state.view + 1}, ${STEP_NAMES[state.view + 1] || ""}` : `Next, not ready. ${NEXT_HINT[state.view] || ""}`);
  keep();
}

const REDUCED = window.matchMedia ? matchMedia("(prefers-reduced-motion: reduce)") : {matches: true};

function go(n, focusId) {
  if (n < 1 || n > state.reached) return;
  const from = state.view, changed = n !== from;
  const swap = morph => {
    state.view = n;
    paintSteps();
    if (n === 2 && state.data && !state.auto) autoChart();
    if (!changed) { fitScreen(); return; }
    drawKinds();
    if (!morph) for (const id of VIEWS[n]) { const el = $(id); el.classList.remove("enter"); void el.offsetWidth; el.classList.add("enter"); }
    const fitH = fitScreen();
    if (state.spec && n > 1) drawChart({still: true, fitH});
    if (focusId) $(focusId).focus();
  };
  if (changed && from > 1 && n > 1 && state.spec && document.startViewTransition && !REDUCED.matches) {
    document.documentElement.classList.add("qv-morph");
    const t = document.startViewTransition(() => { swap(true); return chart.settled(700); });
    t.finished.finally(() => document.documentElement.classList.remove("qv-morph"));
  } else swap(false);
}

const FIT_MQ = window.matchMedia ? matchMedia("(min-width: 901px) and (min-height: 700px)") : {matches: false};
const px = (el, prop) => parseFloat(getComputedStyle(el)[prop]) || 0;

function fitScreen() {
  const on = !!FIT_MQ.matches;
  const css = document.documentElement.style;
  document.body.classList.toggle("fit", on);
  if (!on) { css.removeProperty("--frame-h"); css.removeProperty("--preview-h"); state.fitH = null; return null; }
  const vh = window.innerHeight, layout = document.querySelector(".layout"), next = $("next-row");
  const tail = px(layout, "paddingBottom") + (next.hidden ? 0 : next.offsetHeight + px(next, "marginTop"));
  if (state.view === 1) {
    const wrap = document.querySelector(".preview-wrap"), meta = $("preview-meta");
    if (wrap.offsetParent) css.setProperty("--preview-h", Math.max(140, Math.floor(vh - wrap.getBoundingClientRect().top - window.scrollY - meta.offsetHeight - px(meta, "marginTop") - tail)) + "px");
    return state.fitH;
  }
  const frame = $("frame"), below = document.querySelector(".below");
  const belowH = state.view === 4 ? below.offsetHeight + px(below, "marginTop") : 0;
  const h = Math.max(300, Math.floor(vh - frame.getBoundingClientRect().top - window.scrollY - belowH - tail - 2));
  css.setProperty("--frame-h", h + "px");
  state.fitH = h;
  return h;
}

let fitFrame = 0;
function refit() {
  cancelAnimationFrame(fitFrame);
  fitFrame = requestAnimationFrame(() => {
    const before = state.fitH;
    const h = fitScreen();
    if (state.spec && state.view > 1 && h !== before) drawChart({still: true, fitH: h});
  });
}
window.addEventListener("resize", refit);
if (window.ResizeObserver) {
  const ro = new ResizeObserver(refit);
  [".topbar", "#cap-banner", ".stepbar", ".notice", "#step-ask", ".stage-head", ".data-head", "#col-list", "#data-notes"].forEach(q => { const el = document.querySelector(q); if (el) ro.observe(el); });
}

function reach(n, focusId) { state.reached = Math.max(state.reached, n); go(n, focusId); }

document.querySelectorAll("#stepper .st-btn").forEach(btn => btn.onclick = () => {
  const n = +btn.dataset.step;
  if (n !== state.view && n <= state.reached) go(n);
});

function showCap(detail) {
  const d = detail && typeof detail === "object" ? detail : {};
  $("cap-text").textContent = d.message || "Today's credits are used up. Your chart, undo and the downloads still work.";
  $("cap-signin").hidden = !(d.reason === "credits" && d.sign_in);
  $("cap-banner").dataset.reason = d.reason || "";
  $("cap-banner").hidden = false;
}

const isNum = v => typeof v === "number" && Number.isFinite(v);
const toNum = v => (typeof v === "number" ? v : NaN);
const yearOf = v => { const m = /^-?\d+(\.\d+)?/.exec(String(v).trim()); return m ? parseFloat(m[0]) : NaN; };

const NEED = {
  bar: ["cat", "v"], treemap: ["cat", "v"], donut: ["cat", "v"], map: ["cat", "v"],
  line: ["t", "v", "series?"], stacked_area: ["t", "series", "v"],
  stacked_bar: ["cat", "series", "v"], heatmap: ["cat", "series", "v"], sankey: ["cat", "series", "v"],
  dot_range: ["cat", "series", "v"], scatter: ["v", "v2", "series?", "cat?"], histogram: ["v"], bump: ["t", "cat", "v"],
};

function colByName(name) { return state.data.cols.find(c => c.name === name); }

let ROOM = null;
const distinctOf = c => (ROOM && ROOM.has(c.name) ? ROOM.get(c.name) : c.distinct);
function inRoom(room, fn) { const old = ROOM; ROOM = room; try { return fn(); } finally { ROOM = old; } }
function roomOf(recipe) {
  const room = new Map();
  if (!state.data || !recipe) return room;
  const own = col => (recipe.filters || []).filter(f => !f.auto && f.column === col);
  for (const col of new Set((recipe.filters || []).filter(f => !f.auto).map(f => f.column))) if (colByName(col)) room.set(col, valuesOf(filterRows(state.data.rows, own(col)), col).length);
  const top = recipe.top;
  if (top && top.n && top.column && colByName(top.column)) {
    const vals = valuesOf(filterRows(state.data.rows, own(top.column)), top.column);
    const aggs = vals.filter(v => isAggregate(v)).length;
    room.set(top.column, Math.min(vals.length, top.n + aggs + (top.other ? 1 : 0)));
  }
  return room;
}

function fits(r, c, kind) {
  if (!c) return false;
  if (r === "v" || r === "v2") return c.type === "number";
  if (r === "t") return c.type === "time";
  if (r === "series") { const n = distinctOf(c); return c.type !== "number" && c.distinct >= 2 && (kind === "dot_range" || n <= (kind === "sankey" ? 30 : 24)); }
  if (r === "cat") return c.type !== "number";
  return false;
}

const SUMS_PARTS = new Set(["stacked_bar", "stacked_area", "treemap", "donut", "sankey"]);
const AGG_KEYS = {bar: ["cat"], treemap: ["cat"], donut: ["cat"], map: ["cat"], line: ["t", "series"], stacked_area: ["t", "series"],
  stacked_bar: ["cat", "series"], heatmap: ["cat", "series"], dot_range: ["cat", "series"], sankey: ["cat", "series"], bump: ["t", "cat"],
  scatter: ["cat", "series"], histogram: []};
const aggCache = new WeakMap();
function aggInfo() {
  const d = state.data;
  if (!d) return {names: new Set(), cols: []};
  let a = aggCache.get(d);
  if (!a) {
    const names = new Set((d.aggregates || []).map(String));
    for (const c of d.cols) {
      if (c.type === "number" || isFlagCol(c) || !(c.distinct > 2 && c.distinct <= 60)) continue;
      const vals = valuesOf(d.rows, c.name);
      vals.filter(v => TOTAL_NAME.test(v.trim())).forEach(v => names.add(v));
      const t = totalByRange(vals);
      if (t) names.add(t);
    }
    const isAgg = v => v !== "" && v != null && (names.has(String(v)) || QV.isEU(v));
    const cols = d.cols.filter(c => c.type !== "number" && d.rows.some(r => isAgg(r[c.name]))).map(c => c.name);
    a = {names, cols, isAgg};
    aggCache.set(d, a);
  }
  return a;
}
function isAggregate(v) { const a = aggInfo(); return !!a.isAgg && a.isAgg(v); }
function dropAggregates(kind, rows, map, filters) {
  const a = aggInfo();
  if (!a.cols.length) return rows;
  const kept = new Set((filters || []).flatMap(f => (f.keep || []).map(String)));
  const keys = new Set((AGG_KEYS[kind] || []).map(f => map[f]).filter(Boolean));
  const drop = r => {
    const hits = a.cols.filter(c => a.isAgg(r[c]));
    if (!hits.length || hits.some(c => kept.has(String(r[c])))) return false;
    return SUMS_PARTS.has(kind) || !hits.some(c => keys.has(c));
  };
  const out = rows.filter(r => !drop(r));
  return out.length ? out : rows;
}

const nestCache = new WeakMap();
function splitsCat(kind, cat, series) {
  if (!["stacked_bar", "heatmap", "sankey"].includes(kind) || !cat || !series || !state.data) return true;
  let m = nestCache.get(state.data);
  if (!m) { m = new Map(); nestCache.set(state.data, m); }
  const key = cat + "\u0000" + series;
  if (!m.has(key)) {
    const byCat = new Map(), bySer = new Map();
    for (const r of state.data.rows) {
      const a = r[cat], b = r[series];
      if (a === "" || a == null || b === "" || b == null) continue;
      if (!byCat.has(a)) byCat.set(a, new Set());
      if (!bySer.has(b)) bySer.set(b, new Set());
      byCat.get(a).add(b); bySer.get(b).add(a);
    }
    const multi = [...byCat.values()].filter(x => x.size > 1).length / Math.max(1, byCat.size);
    const oneToOne = [...byCat.values()].every(x => x.size === 1) && [...bySer.values()].every(x => x.size === 1);
    m.set(key, {multi, oneToOne});
  }
  const n = m.get(key);
  return kind === "sankey" ? !n.oneToOne : n.multi >= 0.5;
}

function guess(r, cols, used, kind, cat) {
  const free = cols.filter(c => !used.has(c.name) && !isFlagCol(c) && fits(r, c, kind) && (r !== "series" || splitsCat(kind, cat, c.name)));
  if (!free.length) return null;
  const score = c => {
    if (r === "t") return (c.type === "time" ? 1000 : 0) - c.distinct / 1000;
    if (r === "series") return (kind === "dot_range" ? (c.distinct === 2 ? 100 : 0) : 0) - c.distinct + (c.type === "category" ? 5 : 0);
    if (r === "cat") return (c.type === "category" ? 100 : 0) + Math.min(c.distinct, 50);
    if (r === "v" || r === "v2") return (/^(id|index|#)$|_id$|^id_/i.test(c.name) ? -100 : 0) - cols.indexOf(c) * 0.01;
    return 0;
  };
  return free.sort((a, b) => score(b) - score(a))[0].name;
}

const ID_NAME = /^(id|index|#)$|_id$|^id_/i;
const UNIT_WORD = /(^|[^a-z])(pct|percent|per|rate|ratio|share|index|score|avg|mean|gdp|capita|eur|euro|usd|mn|bn|million|billion|trillion|thousand|k)([^a-z]|$)|[%€$£]/i;

function pairOK(a, b) {
  if (!a || !b || a.name === b.name || a.type !== "number" || b.type !== "number") return false;
  const x = a.name.toLowerCase(), y = b.name.toLowerCase();
  let pre = 0, suf = 0;
  while (pre < x.length && x[pre] === y[pre]) pre++;
  while (suf < x.length && suf < y.length && x[x.length - 1 - suf] === y[y.length - 1 - suf]) suf++;
  return Math.max(pre, suf) >= 4 && !(Math.max(a.min, b.min) > Math.min(a.max, b.max));
}

function dotRangeMap(cols, hints = {}) {
  const byName = Object.fromEntries(cols.map(c => [c.name, c]));
  const cat = hints.cat && fits("cat", byName[hints.cat]) ? hints.cat : guess("cat", cols, new Set(), "dot_range");
  if (!cat) return null;
  const two = c => !!c && c.name !== cat && c.type !== "number" && distinctOf(c) === 2;
  const hs = hints.series && hints.series !== "(columns)" ? byName[hints.series] : null;
  const pair = () => {
    const w = hints.wide;
    if (Array.isArray(w) && w.length === 2 && pairOK(byName[w[0]], byName[w[1]])) return w.slice();
    if (pairOK(byName[hints.v], byName[hints.v2])) return [hints.v, hints.v2];
    const nums = cols.filter(c => c.type === "number" && !ID_NAME.test(c.name));
    for (let i = 0; i < nums.length; i++) for (let j = i + 1; j < nums.length; j++) if (pairOK(nums[i], nums[j])) return [nums[i].name, nums[j].name];
    return null;
  };
  let series = two(hs) ? hs.name : null;
  const wide = series ? null : pair();
  if (wide) return {cat, series: "(columns)", wide, v: "(value)"};
  if (!series) series = cols.filter(two).sort((a, b) => (b.type === "category") - (a.type === "category"))[0]?.name || null;
  if (!series && hs && hs.type === "time" && hs.name !== cat) series = hs.name;
  if (!series) return null;
  const used = new Set([cat, series]);
  const v = hints.v === "(count)" ? "(count)" : hints.v && fits("v", byName[hints.v]) && !used.has(hints.v) ? hints.v : guess("v", cols, used, "dot_range") || "(count)";
  return {cat, series, v};
}

function heuristicMap(kind, cols, hints = {}) {
  if (kind === "dot_range") return dotRangeMap(cols, hints || {});
  const map = {}, used = new Set();
  const need = NEED[kind] || [];
  const byName = Object.fromEntries(cols.map(c => [c.name, c]));
  for (const spec of need) {
    const r = spec.replace("?", ""), opt = spec.endsWith("?");
    if (r === "v" || r === "v2") continue;
    const j = hints[r];
    if (j === null && opt) continue;
    if (j && fits(r, byName[j], kind) && !used.has(j) && (r !== "series" || splitsCat(kind, map.cat, j))) { map[r] = j; used.add(j); continue; }
    if (opt) {
      if (j === undefined && r === "series") { const g = guess(r, cols.filter(c => c.type === "category"), used, kind, map.cat); if (g) { map[r] = g; used.add(g); } }
      continue;
    }
    const g = guess(r, cols, used, kind, map.cat);
    if (g) { map[r] = g; used.add(g); continue; }
    if (r === "series") { map.series = "(columns)"; continue; }
    return null;
  }
  if (need.includes("v")) {
    const j = hints.v;
    if (map.series === "(columns)") {
      const nums = cols.filter(c => c.type === "number" && !used.has(c.name) && !ID_NAME.test(c.name));
      const first = nums.find(c => nums.some(o => pairOK(c, o)));
      const paired = first ? nums.filter(c => c === first || pairOK(first, c)) : [];
      const parts = nums.filter(c => !TOTAL_NAME.test(c.name.trim()));
      const bare = (kind === "stacked_bar" || kind === "stacked_area") && parts.length >= 2 && parts.every(c => !c.unit && !UNIT_WORD.test(c.name));
      const w = (paired.length >= 2 ? paired : bare ? parts : []).slice(0, 8).map(c => c.name);
      if (w.length < 2) return null;
      map.wide = w; map.v = "(value)";
    } else if (j === "(count)") map.v = "(count)";
    else if (j && fits("v", byName[j], kind) && !used.has(j)) { map.v = j; used.add(j); }
    else {
      const g = guess("v", cols, used, kind);
      if (g) { map.v = g; used.add(g); }
      else if (kind === "histogram" || kind === "scatter") return null;
      else map.v = "(count)";
    }
  }
  if (kind === "scatter") {
    const j = hints.v2;
    if (j && fits("v2", byName[j], kind) && j !== map.v) map.v2 = j;
    else { const g = guess("v2", cols, new Set([...used, map.v]), kind); if (!g) return null; map.v2 = g; }
  }
  return map;
}

function hintsFromJev(kind) {
  const cols = state.data.cols, roles = state.decide ? state.decide.columns || {} : {};
  const byRole = r => cols.filter(c => roles[c.name]?.role === r).sort((a, b) => (roles[b.name].confidence ?? 0) - (roles[a.name].confidence ?? 0)).map(c => c.name);
  const names = byRole("name"), values = byRole("value"), times = byRole("time"), groups = byRole("group");
  const h = {v: values[0], v2: values[1], t: times[0]};
  if ((NEED[kind] || []).some(n => n.startsWith("cat"))) h.cat = [...names, ...groups][0];
  h.series = [...groups, ...names, ...times].find(x => x !== h.cat && x !== h.t);
  if (kind === "line" && !h.series && state.decide && state.decide.columns) h.series = null;
  if (kind === "scatter") { h.cat = names[0]; h.series = groups[0] || null; }
  const at = n => cols.findIndex(c => c.name === n);
  if (kind === "sankey" && h.cat && h.series && at(h.series) < at(h.cat)) [h.cat, h.series] = [h.series, h.cat];
  return h;
}

const isFlagCol = c => !!c && c.type !== "number" && /(^|[_ ])flag$/i.test(c.name);
function usableCols() {
  const roles = state.decide ? state.decide.columns || {} : {};
  const kept = state.data.cols.filter(c => roles[c.name]?.role !== "ignore" && !isFlagCol(c));
  return kept.length ? kept : state.data.cols;
}

function rolesFor(kind, hints) {
  const viaJev = {...hintsFromJev(kind), ...(hints || {})};
  return heuristicMap(kind, usableCols(), viaJev) || heuristicMap(kind, state.data.cols, viaJev);
}

function timeSorter(vals) {
  if (vals.every(v => !isNaN(Number(v)))) return (a, b) => Number(a) - Number(b);
  if (vals.every(v => /^\d{4}[- ]?([qQsShHmMwW]\d{1,2}|-\d{2})?$/.test(v))) return (a, b) => a.localeCompare(b, undefined, {numeric: true});
  if (vals.every(v => !isNaN(Date.parse(v)))) return (a, b) => Date.parse(a) - Date.parse(b);
  const order = new Map(vals.map((v, i) => [v, i]));
  return (a, b) => order.get(a) - order.get(b);
}

function filterRows(rows, filters) {
  for (const f of filters || []) {
    const col = colByName(f.column);
    if (!col) continue;
    const keep = f.keep ? new Set(f.keep.map(String)) : null, drop = f.drop ? new Set(f.drop.map(String)) : null;
    rows = rows.filter(r => {
      const v = r[f.column];
      if (keep && !keep.has(String(v))) return false;
      if (drop && drop.has(String(v))) return false;
      if (f.min != null || f.max != null) {
        const n = col.type === "number" ? toNum(v) : yearOf(v);
        if (!Number.isFinite(n)) return false;
        if (f.min != null && n < f.min) return false;
        if (f.max != null && n > f.max) return false;
      }
      return true;
    });
  }
  return rows;
}

function renameRows(rows, rename) {
  const cols = Object.entries(rename || {}).filter(([, m]) => m && Object.keys(m).length);
  if (!cols.length) return rows;
  return rows.map(r => {
    const o = {...r};
    for (const [c, m] of cols) if (Object.prototype.hasOwnProperty.call(m, String(o[c]))) o[c] = m[String(o[c])];
    return o;
  });
}

function combine(vals, how) {
  if (how === "count") return vals.length;
  if (how === "mean") return d3.mean(vals);
  if (how === "median") return d3.median(vals);
  if (how === "min") return d3.min(vals);
  if (how === "max") return d3.max(vals);
  return d3.sum(vals);
}

function wideNames(wide) {
  const nm = state.names && state.names.columns || {};
  const parts = wide.map(w => String(w).split(/[_\s]+/).filter(Boolean));
  let pre = 0;
  while (parts.every(p => p.length > pre + 1 && p[pre].toLowerCase() === parts[0][pre].toLowerCase())) pre++;
  return Object.fromEntries(wide.map((w, i) => {
    if (nm[w]) return [w, nm[w]];
    const s = parts[i].slice(pre).join(" ");
    return [w, s === w ? w : s.charAt(0).toUpperCase() + s.slice(1)];
  }));
}

const blended = {n: 0};
function aggregate(kind, rows, map, agg, unit) {
  if (map.wide) {
    const nm = wideNames(map.wide);
    rows = rows.flatMap(r => map.wide.map(w => ({...r, "(columns)": nm[w], "(value)": r[w]})));
  }
  const counting = map.v === "(count)";
  const how = agg && agg !== "auto" ? agg : counting ? "count" : "one";
  const val = r => (counting ? 1 : toNum(r[map.v]));
  const good = r => counting || isNum(r[map.v]);
  const group = keys => {
    const m = new Map();
    for (const r of rows) {
      if (!good(r)) continue;
      const k = keys.map(f => String(r[map[f]] ?? ""));
      if (k.some(x => x === "")) continue;
      const id = JSON.stringify(k);
      const e = m.get(id) || {k, vals: []};
      e.vals.push(val(r)); m.set(id, e);
    }
    const out = [];
    for (const e of m.values()) {
      const o = {}; keys.forEach((f, i) => o[f] = e.k[i]);
      if (how === "one" && new Set(e.vals).size > 1) { blended.n++; continue; }
      o.v = how === "one" ? e.vals[0] : combine(e.vals, how);
      out.push(o);
    }
    return out;
  };
  const sortT = out => { const s = timeSorter([...new Set(out.map(d => d.t))]); return out.sort((a, b) => s(a.t, b.t)); };
  switch (kind) {
    case "map": case "bar": case "treemap": case "donut": return group(["cat"]);
    case "line": return sortT(map.series ? group(["t", "series"]) : group(["t"]));
    case "stacked_area": return sortT(group(["t", "series"]));
    case "stacked_bar": case "heatmap": return group(["cat", "series"]);
    case "dot_range": {
      const a = group(["cat", "series"]);
      return new Set(a.map(d => d.series)).size <= 2 ? a : [];
    }
    case "sankey": return group(["cat", "series"]).filter(d => d.cat !== d.series && d.v > 0);
    case "scatter":
      return rows.filter(r => isNum(r[map.v]) && isNum(r[map.v2])).slice(0, 5000).map(r => {
        const o = {v: r[map.v], v2: r[map.v2]};
        if (map.series) o.series = String(r[map.series]);
        if (map.cat) o.cat = String(r[map.cat]);
        return o;
      });
    case "histogram": return rows.filter(r => isNum(r[map.v])).slice(0, 50000).map(r => ({v: r[map.v]}));
    case "bump": {
      let a = group(["t", "cat"]);
      if (!/rank|position|place|pos\b/i.test(map.v || "")) {
        a = [...d3.group(a, d => d.t).values()].flatMap(g => g.sort((x, y) => y.v - x.v).map((d, i) => ({...d, v: i + 1})));
      }
      return sortT(a);
    }
  }
  return [];
}

const KEY_FIELD = {bar: "cat", treemap: "cat", donut: "cat", map: "cat", sankey: "cat", stacked_bar: "cat", heatmap: "cat", dot_range: "cat",
  line: "series", stacked_area: "series", bump: "cat", scatter: "cat", histogram: null};

function percentShare(kind, rows, within) {
  if (!within || within === "none" || kind === "histogram" || kind === "scatter" || kind === "bump") return rows;
  const groupField = within === "group" ? ({line: "t", stacked_area: "t", stacked_bar: "cat", heatmap: "cat", dot_range: "series", sankey: "cat"}[kind] || null) : null;
  const tot = new Map();
  rows.forEach(r => { const g = groupField ? r[groupField] : "_"; tot.set(g, (tot.get(g) || 0) + Math.abs(r.v)); });
  if (!groupField && (kind === "line" || kind === "stacked_area")) {
    const byT = new Map();
    rows.forEach(r => byT.set(r.t, (byT.get(r.t) || 0) + Math.abs(r.v)));
    return rows.map(r => ({...r, v: byT.get(r.t) ? r.v / byT.get(r.t) * 100 : 0}));
  }
  return rows.map(r => { const t = tot.get(groupField ? r[groupField] : "_"); return {...r, v: t ? r.v / t * 100 : 0}; });
}

const TIME_KINDS = new Set(["line", "stacked_area", "bump"]);
const RATE_TEXT = /%|pct|percent|(^|[^a-z])(rate|rates|ratio|share|shares|average|avg|mean|median|index|score)([^a-z]|$)|\bper (capita|head|person|inhabitant|employee|\d)/i;
function isRate(recipe) {
  const map = (recipe && recipe.roles) || {};
  if (recipe.percent && recipe.percent !== "none") return true;
  if (map.v === "(count)" || recipe.agg === "count" || recipe.agg === "sum") return false;
  if (recipe.agg === "mean" || recipe.agg === "median") return true;
  const cols = map.wide || [map.v];
  const text = [...cols, ...cols.map(c => (state.data && colByName(c)?.unit) || ""), recipe.unit || "", (state.names && state.names.unit) || ""].join(" ");
  return RATE_TEXT.test(text);
}

const topped = {info: null};
const RATE_OTHER = "Other is left out, because these values are rates and adding them up would mean nothing.";
const TOP_FIELDS = {stacked_bar: ["cat", "series"], heatmap: ["cat", "series"], dot_range: ["cat", "series"], sankey: ["cat", "series"]};
function topField(kind, map, top) {
  const f = KEY_FIELD[kind];
  if (!f || !top || !top.column) return f;
  return (TOP_FIELDS[kind] || [f]).find(k => map[k] === top.column) || null;
}

function topN(kind, rows, top, ctx = {}) {
  topped.info = null;
  const f = ctx.field !== undefined ? ctx.field : KEY_FIELD[kind];
  if (!top || !top.n || !f) return rows;
  const isAgg = ctx.isAgg || (() => false);
  const plain = rows.filter(r => !isAgg(r[f]));
  const ts = [...new Set(plain.map(r => r.t).filter(t => t != null && t !== "").map(String))];
  ts.sort(timeSorter(ts));
  const timed = TIME_KINDS.has(kind) && ts.length > 0;
  let by = kind === "bump" ? "rank" : !timed ? "total" : top.by || "latest";
  if (timed && !["latest", "total", "mean", "rank"].includes(by) && !ts.includes(String(by))) {
    const hit = ts.filter(t => yearOf(t) === yearOf(by));
    by = hit.length ? hit.at(-1) : "latest";
  }
  const at = by === "latest" ? ts.at(-1) : !["total", "mean", "rank"].includes(by) ? String(by) : null;
  const score = new Map(), latest = new Map();
  for (const r of plain) {
    const k = r[f];
    const e = score.get(k) || {sum: 0, abs: 0, n: 0, at: null, min: Infinity};
    const v = r.v ?? 1;
    e.sum += v; e.abs += Math.abs(v); e.n++; e.min = Math.min(e.min, v);
    if (at != null && String(r.t) === at) e.at = (e.at ?? 0) + v;
    score.set(k, e);
    if (timed) { const l = latest.get(k); if (!l || ts.indexOf(String(r.t)) >= ts.indexOf(l.t)) latest.set(k, {t: String(r.t), v}); }
  }
  const val = (k, e) => (by === "rank" ? -e.min : by === "total" ? e.abs : by === "mean" ? e.sum / e.n : e.at ?? -Infinity);
  const order = [...score].map(([k, e]) => [k, val(k, e), latest.get(k)?.v ?? -Infinity])
    .sort((a, b) => (b[1] - a[1]) || (by === "rank" ? 0 : b[2] - a[2]));
  if (order.length <= top.n) return rows;
  const keep = new Set(order.slice(0, top.n).map(e => e[0]));
  const info = {kind, auto: !!top.auto, rate: !!ctx.rate, n: top.n, of: order.length, by, at, year: ctx.year, first: ts[0], last: ts.at(-1), other: null, rest: order.length - top.n,
    items: order.map(e => e[0]), aggs: [...new Set(rows.filter(r => isAgg(r[f])).map(r => r[f]))]};
  topped.info = info;
  const out = rows.filter(r => keep.has(r[f]) || isAgg(r[f]));
  if (!top.other || kind === "scatter" || kind === "bump") return out;
  if (ctx.rate) { info.other = "rate"; return out; }
  info.other = "sum";
  const rest = new Map();
  plain.filter(r => !keep.has(r[f])).forEach(r => {
    const o = {...r, [f]: "Other"};
    const k = JSON.stringify([o.cat, o.series, o.t]);
    const e = rest.get(k);
    if (e) e.v += r.v; else rest.set(k, o);
  });
  return out.concat([...rest.values()]);
}

function topNote(info) {
  if (!info) return "";
  const names = info.items.map(String);
  const share = names.filter(n => QV.countryId(n)).length / Math.max(1, names.length);
  const noun = share >= 0.8 ? "countries" : QV.regionCountry(names) ? "regions" : "items";
  const by = info.by === "rank" ? "by best rank" : info.by === "mean" ? `by average from ${info.first} to ${info.last}`
    : info.by === "total" ? (info.first != null && info.first !== info.last ? `by ${info.rate ? "sum of values" : "total"} from ${info.first} to ${info.last}`
      : !["stacked_bar", "heatmap", "dot_range", "sankey"].includes(info.kind) ? `by ${info.year ? info.year + " " : ""}value`
      : info.rate ? `by the sum of their ${info.year ? info.year + " " : ""}values` : `by ${info.year ? info.year + " " : ""}total`)
    : `by ${info.at} value`;
  const parts = [info.auto ? `Showing the top ${info.n} of ${info.of} ${noun}, to fit the screen.` : `Top ${info.n} of ${info.of} ${noun}, ${by}.`];
  if (info.other === "sum") parts.push(info.rest === 1 ? "The other one is shown as Other." : `The other ${info.rest} are added up as Other.`);
  if (info.other === "rate") parts.push(RATE_OTHER);
  if (info.aggs.length) parts.push(`${info.aggs.length === 1 ? "The total is" : "Totals are"} shown for reference and not counted.`);
  return parts.join(" ");
}

function sortRows(kind, rows, sort) {
  const f = KEY_FIELD[kind];
  if (!f || kind === "scatter" || !sort || sort.by === "none") return rows;
  const keys = [...new Set(rows.map(r => r[f]))];
  let order;
  if (sort.by === "label") order = keys.sort((a, b) => String(a).localeCompare(String(b), undefined, {numeric: true}));
  else {
    const tot = new Map();
    rows.forEach(r => tot.set(r[f], (tot.get(r[f]) || 0) + (kind === "bump" ? 0 : r.v)));
    order = keys.sort((a, b) => tot.get(a) - tot.get(b));
  }
  if (sort.order !== "asc") order.reverse();
  const other = order.indexOf("Other");
  if (other >= 0) { order.splice(other, 1); order.push("Other"); }
  const pos = new Map(order.map((k, i) => [k, i]));
  return rows.map((r, i) => [r, i]).sort((a, b) => (pos.get(a[0][f]) - pos.get(b[0][f])) || a[1] - b[1]).map(e => e[0]);
}

const LABEL = {"(count)": "Number of rows", "(value)": "Value", "(columns)": ""};
function lab(col) {
  const nm = state.names && state.names.columns || {};
  return nm[col] || (LABEL[col] ?? col ?? "");
}

function autoLabels(kind, map) {
  return ({
    scatter: [lab(map.v), lab(map.v2)], histogram: [lab(map.v), "Count"],
    line: [lab(map.t), lab(map.v)], stacked_area: [lab(map.t), lab(map.v)], bump: [lab(map.t), "Rank"],
    heatmap: [lab(map.series), lab(map.v)], dot_range: ["", map.wide ? "" : lab(map.v)], treemap: ["", lab(map.v)], donut: ["", lab(map.v)],
    sankey: ["", lab(map.v)], map: ["", lab(map.v)],
  }[kind] || [lab(map.cat), lab(map.v)]);
}

function defaultSort(kind) { return kind === "bar" ? {by: "value", order: "desc"} : null; }

const YEARISH = /^\d{4}([-_ ]?([qQsShHmMwW]\d{1,2}|\d{2}))?$/;
const valuesOf = (rows, col) => [...new Set(rows.map(x => x[col]).filter(v => v !== "" && v != null).map(String))];
function yearCols() {
  const d = state.data;
  let c = yearColCache.get(d);
  if (!c) {
    c = d.cols.filter(x => x.type === "time" || (x.type === "category" && x.distinct > 0 && x.distinct <= 200 && valuesOf(d.rows, x.name).every(v => YEARISH.test(v)))).map(x => x.name);
    yearColCache.set(d, c);
  }
  return c;
}
const yearColCache = new WeakMap(), knownCache = new WeakMap();
function drawnYears(rows) {
  const cols = yearCols(), set = new Set(), known = new Set();
  const grab = (list, into) => { for (const r of list) for (const c of cols) { const y = yearOf(r[c]); if (Number.isInteger(y) && y >= 1800 && y <= 2200) into.add(y); } };
  grab(rows, set);
  const d = state.data;
  if (!knownCache.has(d)) { grab(d.rows, known); knownCache.set(d, known); }
  return {drawn: [...set].sort((a, b) => a - b), known: knownCache.get(d)};
}

function trueYears(title, years) {
  if (!title || !years || !years.drawn.length) return title;
  const {drawn, known} = years, lo = drawn[0], hi = drawn.at(-1);
  const span = lo === hi ? String(lo) : `${lo} to ${hi}`;
  const RANGE = /\b((?:18|19|20|21)\d{2})(\s*(?:to|until|through|-|–|—)\s*)((?:18|19|20|21)\d{2})\b/g;
  let out = title.replace(RANGE, (m, a, sep, b) => (known.has(+a) || known.has(+b)) && (+a !== lo || +b !== hi) ? span : m);
  out = out.replace(/(\b(?:since|from|after)\s+)?\b((?:18|19|20|21)\d{2})\b(?!\s*(?:to|until|through|-|–|—)\s*\d)/gi, (m, pre, y, at, s) => {
    const n = +y;
    if (!known.has(n) || /(?:to|until|through|-|–|—)\s*$/.test(s.slice(0, at))) return m;
    if (pre) return n === lo ? m : pre + lo;
    if (drawn.length === 1) return n === lo ? m : span;
    return span;
  });
  return out;
}

function namesContext(r) {
  const used = new Set(Object.values(r.roles || {}).flat());
  const filters = (r.filters || []).filter(f => f.keep && f.keep.length === 1 && !used.has(f.column)).map(f => {
    const reader = (r.controls || []).some(c => c.column === f.column);
    return {column: f.column, value: String(f.keep[0]), reader, options: reader ? valuesOf(state.data.rows, f.column).slice(0, 24) : []};
  });
  const y = drawnYears(dropAggregates(r.kind, filterRows(state.data.rows, r.filters), r.roles, r.filters));
  return {filters, years: y.drawn, data_years: [...y.known].sort((a, b) => a - b).slice(0, 400)};
}

function namesColumns() { return state.data.cols.map(c => ({name: c.name, type: c.type, distinct: c.distinct, samples: (c.samples || []).map(String)})); }

function catKey(r) {
  const used = new Set(Object.values(r.roles || {}).flat());
  return JSON.stringify((r.filters || []).filter(f => f.keep && f.keep.length === 1 && !used.has(f.column) && !yearCols().includes(f.column)).map(f => [f.column, String(f.keep[0])]).sort());
}

async function refreshTitle() {
  const r = state.recipe;
  if (!r || !state.names || r.title != null || state.namesFor === undefined) return;
  const k = catKey(r);
  if (k === state.namesFor) return;
  state.namesFor = k;
  const my = seq;
  const roles = Object.fromEntries(Object.entries(r.roles).filter(([q, v]) => ["cat", "series", "t", "v", "v2"].includes(q) && v && !String(v).startsWith("(")));
  try {
    const w = await api("/api/viz/names", {json: {text: "", columns: namesColumns(), kind: r.kind, roles, file: state.data.name, ...namesContext(r)}});
    if (my !== seq || !state.recipe || catKey(state.recipe) !== k || !w || !w.title) return;
    state.names = {...state.names, title: w.title};
    render();
  } catch (e) { }
}

function showingNote(recipe) {
  const used = new Set(Object.values(recipe.roles || {}).flat());
  const one = (recipe.filters || []).filter(f => f.keep && f.keep.length === 1 && !used.has(f.column) && (colByName(f.column)?.distinct || 0) > 1);
  const cat = one.filter(f => !yearCols().includes(f.column));
  if (!cat.length) return "";
  const order = [...cat, ...one.filter(f => yearCols().includes(f.column))];
  const vals = [...new Set(order.map(f => String(f.keep[0])))];
  return `Showing: ${vals.join(", ")}.`;
}

function hiddenPicks(recipe) {
  if (!recipe || !state.data) return "";
  const used = new Set(Object.values(recipe.roles || {}).flat());
  const ctl = new Set((recipe.controls || []).map(c => c.column).filter(Boolean));
  return (recipe.filters || []).filter(f => f.auto && f.keep && f.keep.length === 1 && !used.has(f.column) && !ctl.has(f.column) && !yearCols().includes(f.column))
    .map(f => {
      const vals = valuesOf(state.data.rows, f.column);
      if (vals.length < 2) return "";
      const geo = vals.filter(v => QV.countryId(v) || QV.isEU(v)).length >= vals.length * 0.5 || QV.regionCountry(vals);
      return `Showing ${f.keep[0]}. ${vals.length} ${geo ? "areas" : "values of " + lab(f.column)} in the file.`;
    }).filter(Boolean).join(" ");
}

function drawPicks() {
  const el = $("shown-line"), text = hiddenPicks(state.recipe);
  el.textContent = text;
  el.hidden = !text;
}

function buildSpec(recipe) {
  const d = state.data, kind = recipe.kind, map = recipe.roles;
  let rows = filterRows(d.rows, recipe.filters);
  rows = dropAggregates(kind, rows, map, recipe.filters);
  const years = drawnYears(rows);
  rows = renameRows(rows, recipe.rename);
  blended.n = 0;
  let out = aggregate(kind, rows, map, recipe.agg, recipe.unit ?? (state.names && state.names.unit));
  const blend = blended.n;
  if (blend) out = [];
  out = percentShare(kind, out, recipe.percent);
  const one = (recipe.filters || []).find(f => f.keep && f.keep.length === 1 && colByName(f.column)?.type === "time" && !Object.values(map).includes(f.column));
  const aggRenamed = new Set(Object.values(recipe.rename || {}).flatMap(m => Object.entries(m || {}).filter(([o]) => isAggregate(o)).map(([, n]) => String(n))));
  const rate = isRate(recipe);
  out = topN(kind, out, recipe.top, {field: topField(kind, map, recipe.top), isAgg: v => isAggregate(v) || aggRenamed.has(String(v)), rate,
    year: one ? String(one.keep[0]) : years.drawn.length === 1 ? years.drawn[0] : null});
  const topText = topNote(topped.info);
  out = sortRows(kind, out, recipe.sort || defaultSort(kind));
  let [xl, yl] = autoLabels(kind, map);
  if (one) { if (yl) yl += ", " + one.keep[0]; else if (xl) xl += ", " + one.keep[0]; }
  const pct = recipe.percent && recipe.percent !== "none";
  const vName = map.wide ? map.wide.join(" ") : map.v || "";
  const autoUnit = pct ? "%" : /%|pct|percent/i.test(vName) ? "%" : /€|eur\b|_eur|euro/i.test(vName) ? "€" : /\$|usd|dollar/i.test(vName) ? "$" : (state.names && state.names.unit) || "";
  const pick = (k, auto) => (recipe[k] != null ? recipe[k] : auto);
  const showing = showingNote(recipe);
  const spec = {
    kind, title: trueYears(pick("title", (state.names && state.names.title) || ""), years), xLabel: pick("xLabel", xl), yLabel: pick("yLabel", pct && yl ? "Share of " + yl.replace(/^./, c => c.toLowerCase()) + " (%)" : yl),
    unit: pick("unit", kind === "bump" ? "" : autoUnit), decimals: recipe.decimals ?? null, orientation: recipe.orientation || (kind === "bar" && recipe.top && recipe.top.auto ? "horizontal" : "auto"),
    valueLabels: recipe.valueLabels || "auto", stack: recipe.stack || "percent", highlight: recipe.highlight || [], colors: recipe.colors || {},
    legendTitle: recipe.legendTitle || "", note: recipe.note || "", autoNote: [showing, topText].filter(Boolean).join(" "), source: isMock() && QV.MOCK_SOURCE ? QV.MOCK_SOURCE : recipe.source || "", sourceUrl: isMock() ? "" : recipe.sourceUrl || "", rows: out,
    style: state.style,
  };
  if (blend) spec.blend = blend;
  if (rate) spec.rate = true;
  for (const k of LAYOUT) if (recipe[k] != null) spec[k] = recipe[k];
  delete spec.controls;
  if (Array.isArray(recipe.controls) && recipe.controls.length) Object.assign(spec, compileControls(recipe, spec));
  return spec;
}

const MAX_COMBOS = 60, MAX_VARIANT_ROWS = 60000;

function columnSteps(col, recipe, type) {
  const vals = [...new Set(state.data.rows.map(r => r[col]).filter(v => v !== "" && v != null).map(String))];
  const c = colByName(col);
  if (c && (c.type === "time" || c.type === "number")) vals.sort(timeSorter(vals));
  const used = type === "slider" && Object.values(recipe.roles || {}).flat().includes(col);
  return vals.map((v, i) => ({label: v, ops: [{op: "clear_filters", column: col}, {op: "filter", column: col, keep: used ? vals.slice(0, i + 1) : [v]}]}));
}

function compileControls(recipe, spec) {
  const base = clone(recipe);
  delete base.controls;
  const out = [], data = [];
  for (const c of recipe.controls) {
    const o = {type: c.type, label: c.label || "", position: c.position === "bottom" ? "bottom" : "top"};
    if (c.type === "legend") { out.push(o); continue; }
    if (c.type === "checkbox") {
      const field = c.field === "cat" || c.field === "series" ? c.field : spec.rows.some(r => r.series != null && r.series !== "") ? "series" : "cat";
      o.field = field;
      o.items = [...new Set(spec.rows.map(r => r[field]).filter(v => v != null && v !== "").map(String))].slice(0, 60);
      if (o.items.length < 2) continue;
      if (!o.label) o.label = field === "cat" ? lab(recipe.roles.cat) : lab(recipe.roles.series) || "Show";
      out.push(o);
      continue;
    }
    const steps = c.column ? columnSteps(c.column, base, c.type) : (c.options || []).map(x => ({label: x.label, set: x.set || {}, ops: x.ops || []}));
    if (steps.length < 2) continue;
    if (c.column && !o.label) o.label = lab(c.column);
    o.options = steps.map(x => x.label);
    o.style = c.style === "buttons" ? "buttons" : c.type === "select" ? "dropdown" : null;
    o.play = c.type === "slider" ? c.play !== false : false;
    const f = c.column && (base.filters || []).find(x => x.column === c.column && x.keep && x.keep.length === 1);
    o.initial = f ? Math.max(0, o.options.indexOf(String(f.keep[0]))) : c.column && c.type === "slider" ? steps.length - 1 : 0;
    o.data = data.length;
    data.push({o, steps});
    out.push(o);
  }
  const res = {controls: out};
  if (!data.length) return res;
  const combos = data.reduce((n, d) => n * d.steps.length, 1);
  if (combos > MAX_COMBOS) throw new Error(`These controls make ${combos} versions of the chart. The limit is ${MAX_COMBOS}, so keep fewer steps or one control.`);
  const baseKeys = Object.keys(spec).filter(k => k !== "controls");
  const variants = {};
  let rows = 0;
  const walk = (i, pick) => {
    if (i === data.length) {
      let r = base, note = "";
      try {
        for (let j = 0; j < pick.length; j++) { const st = data[j].steps[pick[j]]; r = applyChange(r, {set: st.set || {}, ops: st.ops || []}); }
      } catch (e) { r = null; note = "Nothing to draw for this choice."; }
      const s2 = r ? buildSpec(r) : {...spec, rows: []};
      const patch = {rows: s2.rows};
      for (const k of new Set([...baseKeys, ...Object.keys(s2)])) if (k !== "rows" && k !== "controls" && JSON.stringify(s2[k]) !== JSON.stringify(spec[k])) patch[k] = s2[k] ?? null;
      if (note) patch.note = note;
      rows += s2.rows.length;
      variants[pick.join("-")] = patch;
      return;
    }
    for (let k = 0; k < data[i].steps.length; k++) walk(i + 1, [...pick, k]);
  };
  walk(0, []);
  if (rows > MAX_VARIANT_ROWS) throw new Error("These controls need too much data for one chart file. Keep fewer steps.");
  for (const d of data) {
    if (d.steps[0].set === undefined) continue;
    for (let k = 0; k < d.steps.length; k++) {
      const key = data.map(x => (x === d ? k : x.o.initial)).join("-");
      if (variants[key] && JSON.stringify(variants[key].rows) === JSON.stringify(spec.rows)) { d.o.initial = k; break; }
    }
  }
  res.variants = variants;
  return res;
}

const TOTAL_NAME = /^(total|totals|all|overall|both sexes|all sexes|all ages|all sizes|_t|tot|insgesamt|gesamt|ensemble|totaal|totale|todos|tous)$|^(total|all)\b(?!\s+other)|\btotal$/i;

function rangeOf(label) {
  const s = String(label).toLowerCase().replace(/[–—]/g, "-");
  const n = x => parseFloat(x.replace(/[\s,.](?=\d{3}\b)/g, ""));
  let m;
  if ((m = /^ge(\d+)$/.exec(s))) return [n(m[1]), Infinity];
  if ((m = /^lt(\d+)$/.exec(s))) return [0, n(m[1]) - 1];
  if ((m = /^(?:from\s+)?(\d[\d,. ]*?)\s*(?:to|-|_)\s*(\d[\d,. ]*)/.exec(s)) && !/or more|and more|\+/.test(s.slice(m[0].length, m[0].length + 3))) return [n(m[1]), n(m[2])];
  if ((m = /(\d[\d,. ]*?)\s*(?:\+|[a-z ]*\bor more\b|[a-z ]*\band (?:more|over)\b)/.exec(s))) return [n(m[1]), Infinity];
  if ((m = /\b(?:more than|over|above)\s+(\d[\d,. ]*)/.exec(s))) return [n(m[1]) + 1, Infinity];
  if ((m = /\b(?:less than|fewer than|under|below)\s+(\d[\d,. ]*)/.exec(s))) return [0, n(m[1]) - 1];
  if ((m = /\bup to\s+(\d[\d,. ]*)/.exec(s))) return [0, n(m[1])];
  return null;
}

function totalByRange(vals) {
  const rs = vals.map(v => [v, rangeOf(v)]).filter(x => x[1] && x[1].every(y => !Number.isNaN(y)));
  for (const [v, [lo, hi]] of rs) {
    const parts = rs.filter(x => x[0] !== v && x[1][0] >= lo && x[1][1] <= hi).sort((a, b) => a[1][0] - b[1][0]);
    if (parts.length < 2 || parts[0][1][0] !== lo || parts.at(-1)[1][1] !== hi) continue;
    if (parts.every((p, i) => !i || p[1][0] === parts[i - 1][1][1] + 1 || p[1][0] === parts[i - 1][1][1])) return v;
  }
  return null;
}

function defaultPick(vals) {
  const a = aggInfo();
  return vals.find(v => a.isAgg && a.isAgg(v)) || vals.find(v => TOTAL_NAME.test(v.trim())) || totalByRange(vals) || vals[0];
}

function variesWithin(rows, keys, col) {
  const seen = new Map();
  for (const r of rows) {
    const v = r[col];
    if (v === "" || v == null) continue;
    const k = keys.map(f => String(r[f] ?? "")).join("\u0000");
    const prev = seen.get(k);
    if (prev === undefined) seen.set(k, String(v));
    else if (prev !== String(v)) return true;
  }
  return false;
}

function observing(kind, map) { return map.v === "(count)" || kind === "histogram" || (kind === "scatter" && !map.cat); }

function withAutoFilters(r) {
  const d = state.data, map = r.roles || {}, kind = r.kind;
  const used = new Set(Object.values(map).flat());
  const prev = new Map((r.filters || []).filter(f => f.auto && f.keep && f.keep.length === 1).map(f => [f.column, String(f.keep[0])]));
  const filters = (r.filters || []).filter(f => !f.auto);
  const watch = observing(kind, map), explicit = r.agg && r.agg !== "auto";
  const keys = watch ? [] : (AGG_KEYS[kind] || []).map(f => map[f]).filter(c => c && colByName(c));
  const isYear = c => yearCols().includes(c.name);
  const cands = d.cols.filter(c => c.type !== "number" && !isFlagCol(c) && !used.has(c.name)).sort((a, b) => isYear(b) - isYear(a));
  let rows = filterRows(d.rows, filters);
  for (const c of cands) {
    const year = isYear(c);
    if (!year && (watch || explicit)) continue;
    if (filters.some(f => f.column === c.name && (watch || (f.keep && f.keep.length === 1)))) continue;
    const vals = valuesOf(rows, c.name);
    if (vals.length < 2) continue;
    if (!watch && !variesWithin(rows, keys, c.name)) continue;
    if (!year && vals.length > 24 && vals.length >= rows.length * 0.9) continue;
    const old = prev.get(c.name);
    const pick = old !== undefined && vals.includes(old) ? old : year ? vals.slice().sort(timeSorter(vals)).at(-1) : defaultPick(vals);
    filters.push({column: c.name, keep: [pick], auto: true});
    rows = rows.filter(x => String(x[c.name]) === pick);
  }
  return {...r, filters};
}

const AUTO_CTL_MAX = 24;
function withAutoControls(r) {
  if (!r || !r.kind) return r;
  const used = new Set(Object.values(r.roles || {}).flat());
  const auto = (r.filters || []).filter(f => f.auto && f.keep && f.keep.length === 1);
  const keep = (r.controls || []).filter(c => !c.auto || (auto.some(f => f.column === c.column) && !used.has(c.column)));
  const out = {...r, controls: keep};
  if (!r.noAutoControls && auto.some(f => !yearCols().includes(f.column))) {
    const steps = c => valuesOf(state.data.rows, c).length;
    let combos = keep.filter(c => c.column || c.options).reduce((n, c) => n * (c.options ? c.options.length : steps(c.column)), 1);
    const order = [...auto.filter(f => !yearCols().includes(f.column)), ...auto.filter(f => yearCols().includes(f.column))];
    for (const f of order) {
      const n = steps(f.column);
      if (out.controls.length >= 4 || out.controls.some(c => c.column === f.column) || n < 2 || n > AUTO_CTL_MAX || combos * n > MAX_COMBOS) continue;
      combos *= n;
      out.controls = [...out.controls, {type: "select", column: f.column, style: "dropdown", auto: true}];
    }
    const rank = c => order.findIndex(f => f.column === c.column);
    out.controls = [...out.controls.filter(c => !c.auto), ...out.controls.filter(c => c.auto).sort((a, b) => rank(a) - rank(b))];
  }
  if (!out.controls.length) delete out.controls;
  return out;
}

const RATE_TREEMAP = "A treemap adds the values up, and these are rates, so the tiles would mean nothing. Nothing was changed.";
function summedRates(spec) {
  if (spec.kind !== "treemap" || !spec.rate) return false;
  const total = spec.rows.reduce((a, r) => a + (Number.isFinite(r.v) && r.v > 0 && r.cat !== "" ? r.v : 0), 0);
  return !(spec.unit === "%" && Math.abs(total - 100) < 0.6);
}

function fitsKind(kind, recipeLike) {
  const roles = inRoom(roomOf(recipeLike), () => rolesFor(kind, recipeLike && recipeLike.roles));
  if (!roles) return null;
  if (kind === "map") {
    const vals = [...new Set(state.data.rows.map(r => r[roles.cat]).filter(Boolean))];
    const share = vals.filter(v => QV.countryId(v) || QV.isEU(v)).length / Math.max(1, vals.length);
    if (share < 0.5 && !QV.regionCountry(vals)) return null;
  }
  const r = withAutoFilters({...(recipeLike || {}), kind, roles});
  const spec = buildSpec(r);
  return spec.rows.length && !summedRates(spec) ? r : null;
}

function kindOptions(first, ranked) {
  const byJev = (ranked || []).filter(r => Array.isArray(r) && KIND_NAMES[r[0]]).slice().sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0)).map(r => r[0]);
  return [...new Set([first, ...byJev, ...KIND_ORDER])].filter(k => k === first || fitsKind(k, {filters: []}));
}


let fitting = false, fitTries = 0;
function render() {
  if (!fitting) fitTries = 0;
  if (!state.recipe) { state.spec = null; chart.clear(); paintSteps(); drawKinds(); drawPicks(); fitScreen(); return Promise.resolve(null); }
  paintSteps();
  const spec = buildSpec(state.recipe);
  state.spec = spec;
  drawKinds();
  drawPicks();
  const drawn = drawChart({fitH: fitScreen()});
  $("png").disabled = $("html").disabled = false;
  drawSuggest();
  return drawn;
}

function drawChart(opts) {
  if (!state.spec) return Promise.resolve(null);
  const patches = withMock(state.recipe && state.recipe.patches);
  return chart.render(state.spec, {...opts, patches}).then(d => { if (d && !d.superseded) state.orient = d.orient || null; fitTop(d); return d; }, e => ({errors: [], error: e.message, timeout: true}));
}

const FIT_KINDS = new Set(["bar", "stacked_bar", "heatmap", "dot_range"]);
function fitTop(d) {
  const r = state.recipe;
  if (!d || d.superseded || !d.fit || !r || !FIT_KINDS.has(r.kind) || (r.top && !r.top.auto)) return;
  const col = r.roles && r.roles.cat;
  if (!col || String(col).startsWith("(")) return;
  const base = {...r, top: null};
  delete base.controls;
  const items = valuesOf(buildSpec(base).rows, "cat");
  const aggs = items.filter(v => isAggregate(v)).length;
  const room = Math.max(1, d.fit.cap - aggs);
  const want = room >= items.length - aggs ? null : room;
  const cur = r.top && r.top.auto ? r.top.n : null;
  if (want === cur || (cur != null && want != null && want > cur && want < cur + 2) || ++fitTries > 4) return;
  r.top = want == null ? null : {n: want, other: false, by: "latest", column: col, auto: true};
  fitting = true;
  try { render(); } finally { fitting = false; }
}

function drawKinds() {
  const box = $("kinds");
  if (!state.recipe) { box.replaceChildren(); return; }
  const list = state.opts.includes(state.recipe.kind) ? state.opts : [state.recipe.kind, ...state.opts];
  const preview = state.view === 2, best = state.opts[0];
  box.classList.remove("locked");
  box.setAttribute("aria-label", preview ? "Chart types that fit this data. The first is the best fit." : "Chart type");
  box.replaceChildren(...list.map(k => {
    const b = document.createElement("button");
    b.type = "button"; b.role = "tab"; b.textContent = KIND_NAMES[k] || k;
    const on = k === state.recipe.kind;
    b.className = (on ? "active" : "") + (k === best ? " best" : "");
    b.setAttribute("aria-selected", String(on));
    if (k === best) b.title = "Best fit for this data";
    b.onclick = () => { if (!on) localChange({set: {kind: k}, autoTime: true}, `Switched to ${(KIND_NAMES[k] || k).toLowerCase()} chart`, state.view === 2); };
    return b;
  }));
  const act = box.querySelector(".active");
  if (act && box.scrollWidth > box.clientWidth + 1) {
    const l = act.offsetLeft - box.offsetLeft, r = l + act.offsetWidth;
    if (l < box.scrollLeft || r > box.scrollLeft + box.clientWidth) box.scrollLeft = Math.max(0, l - 24);
  }
  kindsEdge();
}

function kindsEdge() {
  const box = $("kinds");
  box.classList.toggle("at-end", box.scrollLeft + box.clientWidth >= box.scrollWidth - 2);
}
$("kinds").addEventListener("scroll", kindsEdge, {passive: true});

function mergeFilter(filters, op) {
  const out = filters.filter(f => !(f.auto && f.column === op.column)).map(f => ({...f}));
  let f = out.find(x => x.column === op.column);
  if (!f) { f = {column: op.column}; out.push(f); }
  if (op.keep) { f.keep = op.keep.map(String); delete f.drop; }
  if (op.drop) {
    if (f.keep) f.keep = f.keep.filter(v => !op.drop.map(String).includes(v));
    else f.drop = [...new Set([...(f.drop || []), ...op.drop.map(String)])];
  }
  if (op.min != null) f.min = op.min;
  if (op.max != null) f.max = op.max;
  return out;
}

function mergeFaces(old, v) {
  if (!v || typeof v !== "object") return null;
  const out = {...(old && typeof old === "object" ? old : {}), ...v};
  for (const k of Object.keys(out)) if (out[k] == null) delete out[k];
  return Object.keys(out).length ? out : null;
}

function applyChange(recipe, change) {
  const r = clone(recipe);
  const set = change.set || {};
  for (const [k, v] of Object.entries(set)) {
    if (k === "kind") continue;
    if (k === "highlight") r.highlight = v || [];
    else if (k === "colors") r.colors = v && Object.keys(v).length ? {...(r.colors || {}), ...v} : {};
    else if (k === "fontStyle") r.fontStyle = mergeFaces(r.fontStyle, v);
    else r[k] = v;
  }
  const oldKey = recipe.roles && recipe.roles[KEY_FIELD[recipe.kind]];
  if (r.top && r.top.n && !r.top.column && oldKey && !String(oldKey).startsWith("(")) r.top = {...r.top, column: oldKey};
  let rolesHint = {...r.roles}, topOp = false;
  for (const op of change.ops || []) {
    if (op.op === "filter") r.filters = mergeFilter(r.filters || [], op);
    else if (op.op === "clear_filters") r.filters = op.column ? (r.filters || []).filter(f => f.column !== op.column) : [];
    else if (op.op === "top_n") { r.top = op.n ? {n: op.n, other: !!op.other, ...(op.by != null ? {by: String(op.by)} : {})} : {n: 0}; topOp = true; }
    else if (op.op === "sort") r.sort = {by: op.by, order: op.order || "desc"};
    else if (op.op === "aggregate") r.agg = op.how;
    else if (op.op === "percent_share") { r.percent = op.within === "none" ? null : op.within; if (op.within !== "none" && set.unit === undefined) r.unit = null; }
    else if (op.op === "rename") r.rename = {...(r.rename || {}), [op.column]: {...((r.rename || {})[op.column] || {}), ...op.map}};
    else if (op.op === "roles") {
      for (const k of ["cat", "series", "t", "v", "v2"]) if (k in op) {
        if (op[k]) rolesHint[k] = op[k]; else rolesHint[k] = null;
      }
      if ("series" in op || "v" in op || "v2" in op) delete rolesHint.wide;
    }
  }
  const kind = set.kind || r.kind;
  const sameKind = kind === r.kind;
  const rolesOp = (change.ops || []).some(o => o.op === "roles");
  const room = roomOf(r);
  if (topOp && r.top && r.top.n) for (const o of (change.ops || []).filter(x => x.op === "roles")) for (const c of [o.cat, o.series]) {
    if (c && colByName(c)) room.set(c, roomOf({...r, top: {...r.top, column: c}}).get(c));
  }
  if (sameKind && !rolesOp) r.roles = recipe.roles;
  else if (sameKind) {
    for (const n of NEED[kind] || []) if (n.endsWith("?") && !(n.slice(0, -1) in rolesHint)) rolesHint[n.slice(0, -1)] = null;
    r.roles = inRoom(room, () => heuristicMap(kind, state.data.cols, rolesHint) || rolesFor(kind, rolesHint));
  } else r.roles = inRoom(room, () => rolesFor(kind, rolesHint));
  const asked = (change.ops || []).filter(x => x.op === "roles").map(x => x.series).find(c => c && colByName(c));
  if (!r.roles && asked) throw new Error(roleRefusal(kind, "series", asked, room));
  if (!r.roles) throw new Error(`This data has no columns that fit a ${(KIND_NAMES[kind] || kind).toLowerCase()} chart.`);
  for (const o of (change.ops || []).filter(x => x.op === "roles")) for (const k of ["cat", "series", "t"]) {
    const want = o[k];
    if (!want || String(want).startsWith("(") || !colByName(want) || r.roles[k] === want || (kind === "dot_range" && r.roles.wide)) continue;
    throw new Error(roleRefusal(kind, k, want, room));
  }
  if (topOp && r.top && r.top.n) r.top.column = topColumn(kind, r.roles, r.filters);
  if (!sameKind) {
    for (const k of AXIS_FIELDS) if (set[k] === undefined) delete r[k];
    if (!set.sort && r.sort && !(change.ops || []).some(o => o.op === "sort")) r.sort = null;
    for (const k of ["xLabel", "yLabel"]) if (set[k] === undefined) r[k] = null;
    if (set.stack === undefined && kind !== "stacked_bar") r.stack = null;
    delete r.patches;
  }
  r.kind = kind;
  if (change.patch && change.patch.code) r.patches = [...(r.patches || []), {code: String(change.patch.code), note: String(change.patch.note || "")}];
  if (set.controls !== undefined) r.noAutoControls = true;
  Object.assign(r, withAutoFilters(r));
  const spec = buildSpec(r);
  if (spec.blend) throw new Error("That would add up or average several rows into one value. Say how to combine them, for example \"sum them\" or \"show the average\", or pick one value with a filter.");
  if (!spec.rows.length) throw new Error("That change leaves nothing to draw, so it was not applied.");
  if (summedRates(spec)) throw new Error(RATE_TREEMAP);
  return r;
}

const ROLE_PLACE = {heatmap: {cat: "the rows", series: "the columns"}, stacked_bar: {cat: "the bars", series: "the parts of each bar"},
  dot_range: {cat: "the rows", series: "the two dots"}, line: {t: "the time axis", series: "the lines"}, stacked_area: {t: "the time axis", series: "the layers"},
  sankey: {cat: "the sources", series: "the targets"}};
function roleRefusal(kind, k, col, room) {
  const c = colByName(col), n = inRoom(room, () => distinctOf(c)), name = (KIND_NAMES[kind] || kind).toLowerCase();
  const place = (ROLE_PLACE[kind] && ROLE_PLACE[kind][k]) || (k === "cat" ? "the categories" : k === "t" ? "the time axis" : "the groups");
  if (k === "series" && c.type !== "number") {
    if (kind === "dot_range" && n !== 2) return `A dot range needs exactly two values for its dots, and ${col} has ${n}. Keep two of them with a filter first. Nothing was changed.`;
    const max = kind === "sankey" ? 30 : 24;
    if (n > max) return `${col} has ${n} values, too many for ${place} of a ${name} chart. The most is ${max}. Ask for a top ${Math.min(20, max)} first. Nothing was changed.`;
  }
  return `${col} cannot be ${place} of a ${name} chart. Nothing was changed.`;
}

function topColumn(kind, map, filters) {
  const opts = (TOP_FIELDS[kind] || [KEY_FIELD[kind]]).map(k => map[k]).filter(c => c && !String(c).startsWith("(") && colByName(c));
  if (opts.length < 2) return opts[0];
  const rows = filterRows(state.data.rows, filters);
  return opts.map(c => [c, valuesOf(rows, c).length]).sort((a, b) => b[1] - a[1])[0][0];
}

function pushUndo(label, msgIndex) {
  state.undo.push({recipe: clone(state.recipe), label, msgIndex});
}

function localChange(change, label, quiet) {
  try {
    const next = withAutoControls(applyChange(state.recipe, change));
    pushUndo(label, quiet ? null : state.chat.length);
    state.recipe = next;
    setErr("");
    render();
    if (!quiet) {
      addChat("note", label, {applied: true});
      notePatchesDropped(state.undo.at(-1).recipe, next);
    }
    refreshTitle();
  } catch (e) { setErr(e.message); }
}

function notePatchesDropped(before, after) {
  const n = ((before && before.patches) || []).length;
  if (!n || ((after && after.patches) || []).length || !after || after.kind === before.kind) return;
  addChat("note", n === 1 ? "The drawn change was removed with the chart type switch." : `The ${n} drawn changes were removed with the chart type switch.`);
}

function undo() {
  const u = state.undo.pop();
  if (!u) return;
  state.recipe = u.recipe;
  if (u.msgIndex != null && state.chat[u.msgIndex]) state.chat[u.msgIndex].undone = true;
  else state.chat.push({role: "note", text: `Undone: ${u.label}`});
  render();
  drawChat();
  refreshTitle();
}

function addChat(role, text, extra = {}) {
  state.chat.push({role, text, ...extra});
  drawChat();
  return state.chat.length - 1;
}

function drawChat() {
  const log = $("chat-log");
  log.replaceChildren(...state.chat.map((m, i) => {
    const div = document.createElement("div");
    div.className = "msg " + m.role + (m.undone ? " undone" : "") + (m.pending ? " pending" : "");
    const p = document.createElement("p");
    if (m.pending) {
      p.className = "dots";
      p.setAttribute("aria-label", "Changing the chart");
      p.append(...[0, 1, 2].map(() => document.createElement("i")));
    } else p.textContent = m.text;
    div.append(p);
    if (m.meta) { const s = document.createElement("span"); s.className = "meta"; s.textContent = m.meta; div.append(s); }
    if (m.undone) { const s = document.createElement("span"); s.className = "meta"; s.textContent = "Undone"; div.append(s); }
    else if ((m.role === "assistant" || m.role === "note") && m.applied && state.undo.at(-1)?.msgIndex === i) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "linkish"; b.textContent = "Undo this";
      b.onclick = undo;
      div.append(b);
    }
    return div;
  }));
  log.scrollTop = log.scrollHeight;
  if (state.recipe) drawSuggest(); else $("chat-empty").hidden = true;
  keep();
}

function colsForAI(message = "") {
  const words = message.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");
  return state.data.cols.map(c => {
    const o = {name: c.name, type: c.type, distinct: c.distinct, samples: (c.samples || []).slice(0, 3).map(String)};
    if (c.type === "number") { o.min = c.min; o.max = c.max; }
    else {
      const vals = [...new Set(state.data.rows.map(r => r[c.name]).filter(v => v !== "" && v != null).map(String))];
      if (vals.length <= MAX_VALUES) o.values = vals;
      else {
        const hits = vals.filter(v => { const n = v.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, ""); return n.length > 1 && words.includes(n); }).slice(0, 7);
        o.samples = [...new Set([...hits, ...o.samples])].slice(0, 10);
      }
    }
    return o;
  });
}

function blankRecipe() { return {kind: null, roles: {}, filters: [], source: state.data.source_hint || ""}; }

let CAPS = null;
fetch("capabilities.json", {credentials: "same-origin"}).then(r => (r.ok ? r.json() : null)).then(j => { CAPS = j; }).catch(() => {});

function missedFields(set, drawn) {
  if (!drawn || drawn.superseded || !Array.isArray(drawn.used)) return [];
  const used = new Set(drawn.used);
  const blank = v => v == null || v === "auto" || (Array.isArray(v) ? !v.length : typeof v === "object" && !Object.keys(v).length);
  return Object.entries(set || {}).filter(([k, v]) => k !== "kind" && k !== "controls" && k !== "logo" && !blank(v) && !used.has(k)).map(([k]) => k);
}

function sayMissed(missed, kind, rest) {
  const labels = [...new Set(missed.map(k => (CAPS && CAPS.labels && CAPS.labels[k]) || k))];
  const what = labels.length === 1 ? labels[0] : labels.slice(0, -1).join(", ") + " and " + labels.at(-1);
  const name = (CAPS && CAPS.names && CAPS.names[kind]) || "chart";
  return `The ${what} did not show on this ${name}, so that part did not change.` + (rest ? " The rest of the change was applied." : "");
}

async function applyReply(base, res, m, message, pend) {
  const changed = Object.keys(res.set || {}).length || (res.ops || []).length || !!res.patch;
  m.text = res.reply || (changed ? "Done." : "I did not change anything.");
  m.meta = window.QV_DEBUG ? `${(res.model || "").split("/").pop()} ${res.ms} ms $${(res.cost || 0).toFixed(5)}${res.tries > 1 ? " retried: " + res.retry_reason : ""}${res.patch ? " patch" : ""}` : "";
  if (!changed) return {};
  let next;
  try { next = withAutoControls(applyChange(base, res)); } catch (e) { m.text = e.message; return {}; }
  pushUndo(message, pend);
  state.recipe = next;
  m.applied = true;
  const saysOther = /\bOther\b|\bas other\b/;
  if ((res.ops || []).some(o => o.op === "top_n" && o.n) && next.top && isRate(next) && (next.top.other || saysOther.test(m.text))) {
    const kept = (m.text.match(/[^.!?]+[.!?]*/g) || []).filter(x => !saysOther.test(x)).join("").trim();
    m.text = ((kept || `Kept the top ${next.top.n}.`) + " " + RATE_OTHER).trim();
  }
  notePatchesDropped(base, next);
  const drawn = await render();
  const missed = missedFields(res.set, drawn);
  if (missed.length) {
    const rest = (res.ops || []).length || !!res.patch || Object.keys(res.set || {}).some(k => k !== "kind" && !missed.includes(k)) || (res.set && res.set.kind && res.set.kind !== base.kind);
    m.text = sayMissed(missed, next.kind, rest);
  }
  let err = "";
  if (res.patch) {
    const last = next.patches.length - 1;
    err = (drawn && (drawn.timeout ? drawn.error || "the chart stopped answering" : (drawn.errors || []).find(e => e.index === last)?.message)) || "";
  }
  const noop = !err && state.recipe === next && await sameChart(base, next) && state.recipe === next;
  if (!err && !noop) return {};
  if (state.recipe === next) {
    state.undo.pop();
    state.recipe = base.kind ? base : null;
    render();
  }
  m.applied = false;
  return err ? {failed: String(err)} : {noop: noEffect(base, res, drawn)};
}

const NO_CHANGE = "The chart did not change, so nothing was applied.";

async function sameChart(a, b) {
  if (!a || !a.kind || !b || !b.kind || typeof chart.sig !== "function") return false;
  const before = await chart.sig(buildSpec(a), withMock(a.patches));
  if (!before) return false;
  const after = await chart.sig(buildSpec(b), withMock(b.patches));
  return before === after;
}

function noEffect(base, res, drawn) {
  const used = new Set(drawn && Array.isArray(drawn.used) ? drawn.used : []);
  const show = v => (v == null ? "auto" : JSON.stringify(v));
  const parts = Object.entries(res.set || {}).filter(([k]) => k !== "kind").map(([k, v]) =>
    `${k} went from ${show(base[k])} to ${show(v)}, and the renderer ${used.has(k) ? "read it but drew exactly the same chart" : "never read it"}`);
  for (const o of res.ops || []) parts.push(`the ${o.op} step ran but the drawing stayed the same`);
  if (res.patch) parts.push("the patch ran without an error but changed nothing in the drawing");
  const change = {reply: res.reply || "", set: res.set || {}, ops: res.ops || []};
  if (res.patch) change.patch = res.patch;
  return {change, detail: ("The chart was drawn again after your change and came out identical to before. " + parts.join(". ") + ". The change was taken back.").slice(0, 1500)};
}

function topForAI(top) {
  const o = {n: top.n, other: !!top.other};
  if (top.by) o.by = top.by;
  if (top.column) o.column = top.column;
  if (top.auto) o.fit = "screen";
  return o;
}

function recipeForAI(r) {
  const s = r.kind ? state.spec || buildSpec(r) : {title: null, xLabel: null, yLabel: null, unit: null};
  const out = {kind: r.kind, roles: Object.fromEntries(Object.entries(r.roles).filter(([k]) => k !== "wide")), title: s.title, xLabel: s.xLabel, yLabel: s.yLabel,
    unit: s.unit, decimals: r.decimals ?? null, filters: r.filters || [], top: r.top && r.top.n ? topForAI(r.top) : null, sort: r.sort || defaultSort(r.kind), aggregate: r.agg || "auto",
    percent_share: r.percent || "none", highlight: r.highlight || [], colors: r.colors || {}, source: r.source || "", note: r.note || "", what_is_shown: s.autoNote || "",
    legendTitle: r.legendTitle || ""};
  if (r.kind && isRate(r)) out.values_are = "rates";
  if (r.kind === "bar") out.orientation = (r === state.recipe && state.orient) || r.orientation || "auto";
  if (r.kind === "stacked_bar") out.orientation = r.orientation === "vertical" ? "vertical" : "horizontal";
  if (r.kind === "stacked_bar") out.stack = r.stack || "percent";
  if (r.rename && Object.keys(r.rename).length) out.rename = r.rename;
  if (r.patches && r.patches.length) out.patches = r.patches.map(p => p.note || "a drawn change");
  const layout = Object.fromEntries(LAYOUT.filter(k => r[k] != null).map(k => [k, r[k]]));
  if (layout.controls) layout.controls = layout.controls.map(c => { const o = {...c}; delete o.auto; return o; });
  if (Object.keys(layout).length) out.layout = layout;
  return out;
}

function drawnNames(spec) {
  const out = new Set();
  for (const row of spec.rows) { if (row.cat != null) out.add(String(row.cat)); if (row.series != null) out.add(String(row.series)); if (out.size >= 200) break; }
  return [...out];
}

async function sendChat(message) {
  if (!state.data || state.busy) return;
  if (/^\s*(undo|go back|revert)\s*[.!]?\s*$/i.test(message)) { undo(); return; }
  const base = state.recipe || blankRecipe();
  state.busy = true;
  const my = seq;
  $("chat-send").disabled = true;
  const history = state.chat.filter(m => m.role === "user" || m.role === "assistant").slice(-8).map(m => ({role: m.role, text: m.text}));
  addChat("user", message);
  const pend = addChat("assistant", "", {pending: true});
  setStatus("", true);
  const spec = state.spec || buildSpec(base);
  const body = {
    message, recipe: recipeForAI(base), columns: colsForAI(message),
    sample: state.data.rows.slice(0, SAMPLE_ROWS).map(r => state.data.cols.map(c => r[c.name])),
    history, chart_rows: spec.rows.slice(0, 12), chart_names: drawnNames(spec),
  };
  if (state.recipe && state.spec) body.outline = await chart.outline(6000);
  try {
    let res = await api("/api/viz/chat", {json: body});
    if (my !== seq) return;
    const m = state.chat[pend];
    let out = await applyReply(base, res, m, message, pend);
    if (my !== seq) return;
    if (out.failed) {
      res = await api("/api/viz/chat", {json: {...body, patch_error: {code: res.patch.code, error: out.failed}}});
      if (my !== seq) return;
      out = await applyReply(base, res, m, message, pend);
      if (my !== seq) return;
      if (out.failed) m.text = "That change did not work, so the chart stays as it was.";
      else if (out.noop) m.text = NO_CHANGE;
    } else if (out.noop && res.patch) m.text = NO_CHANGE;
    else if (out.noop) {
      res = await api("/api/viz/chat", {json: {...body, no_effect: out.noop}});
      if (my !== seq) return;
      out = await applyReply(base, res, m, message, pend);
      if (my !== seq) return;
      if (out.failed || out.noop || !m.applied) m.text = NO_CHANGE;
    }
    m.pending = false;
    drawChat();
  } catch (e) {
    if (my !== seq) return;
    const m = state.chat[pend];
    m.pending = false;
    m.text = e instanceof CapError ? "The AI budget is used up for now, see the note at the top. Undo and downloads still work." : e.message;
    m.role = "error";
    drawChat();
  } finally {
    if (my === seq) {
      state.busy = false;
      $("chat-send").disabled = false;
      setStatus("");
      if (state.recipe) drawSuggest();
      refreshTitle();
    }
  }
}

$("chat-form").onsubmit = e => {
  e.preventDefault();
  const v = $("chat-input").value.trim();
  if (!v) return;
  $("chat-input").value = "";
  sendChat(v);
};
const KIND_ORDER = ["bar", "line", "stacked_bar", "heatmap", "map", "treemap", "scatter", "dot_range", "stacked_area", "donut", "sankey", "bump", "histogram"];
const KIND_SAY = {bar: "a bar chart", line: "a line chart", stacked_area: "a stacked area chart", stacked_bar: "a stacked bar chart", scatter: "a scatter plot",
  histogram: "a histogram", heatmap: "a heatmap", treemap: "a treemap", donut: "a donut chart", sankey: "a flow chart", bump: "a ranking chart", dot_range: "a dot range chart", map: "a map"};

function suggestions() {
  const r = state.recipe, s = state.spec;
  if (!r || !s || !state.data) return [];
  const kind = r.kind, out = [];
  const fresh = !state.chat.some(m => m.role === "user");
  if (fresh) {
    const used = new Set(Object.values(r.roles).flat());
    const other = usableCols().find(c => c.type === "number" && !used.has(c.name));
    if (other && !["histogram", "scatter"].includes(kind)) out.push(`Show ${lab(other.name).replace(/^[A-Z](?=[a-z])/, c => c.toLowerCase())} instead`);
    const tfree = usableCols().find(c => c.type === "time" && c.distinct > 2 && !used.has(c.name));
    if (tfree && !r.roles.t && fitsKind("line", {filters: []})) out.push("Show it over time");
  }
  const tcol = r.roles.t ? colByName(r.roles.t) : null;
  if (tcol) {
    const years = [...new Set(state.data.rows.map(x => yearOf(x[tcol.name])).filter(Number.isFinite))].sort((a, b) => a - b);
    if (years.length >= 5 && !(r.filters || []).some(x => x.column === tcol.name)) out.push(`Only since ${years[Math.max(0, years.length - 5)]}`);
  }
  const auto = (r.filters || []).find(x => x.auto && x.keep && x.keep.length === 1);
  if (auto) {
    const vals = [...new Set(state.data.rows.map(x => x[auto.column]).filter(v => v !== "" && v != null).map(String))].sort(timeSorter([...new Set(state.data.rows.map(x => String(x[auto.column])))]));
    const prev = vals[vals.indexOf(auto.keep[0]) - 1];
    if (prev) out.push(`Show ${prev} instead of ${auto.keep[0]}`);
  }
  const f = KEY_FIELD[kind];
  const items = f ? [...new Set(s.rows.map(x => x[f]).filter(v => v != null && v !== ""))].map(String) : [];
  const plain = items.filter(n => !isAggregate(n) && n !== "Other");
  if (["bar", "line", "scatter", "map", "dot_range", "stacked_bar", "heatmap", "bump", "sankey", "stacked_area"].includes(kind) && plain.length >= 3 && !(r.highlight || []).length) {
    out.push(`Highlight ${plain.find(n => /^belgi/i.test(n)) || plain[1]}`);
  }
  const alt = [...new Set([...state.opts, ...KIND_ORDER])].find(k => k !== kind && fitsKind(k, {filters: []}));
  if (alt) out.push(`Make it ${KIND_SAY[alt]}`);
  if (["bar", "stacked_bar", "dot_range", "heatmap"].includes(kind) && items.length > 2) {
    const srt = r.sort || defaultSort(kind);
    out.push(srt && srt.by === "value" && srt.order !== "asc" ? "Sort A to Z" : "Sort from largest to smallest");
  }
  if (f && !["scatter", "histogram"].includes(kind) && items.length > 10 && !(r.top && r.top.n)) out.push("Show the top 10 only");
  const pctOk = ["bar", "line", "stacked_area", "treemap", "donut", "heatmap"].includes(kind) || (kind === "stacked_bar" && r.stack === "absolute");
  if (pctOk && !r.percent && s.unit !== "%" && r.roles.v !== "(count)") out.push("Show percentages");
  if (s.title && s.title.split(/\s+/).length > 6) out.push("Shorter title");
  const extra = controlChip(r, s);
  if (extra) out.splice(Math.min(2, out.length), 0, extra);
  return out.slice(0, 5);
}

function controlChip(r, s) {
  const have = r.controls || [];
  if (have.length >= 2) return null;
  const used = new Set(Object.values(r.roles || {}).flat());
  const tcol = state.data.cols.find(c => c.type === "time" && c.distinct >= 3 && c.distinct <= 40 && !used.has(c.name) && !have.some(x => x.column === c.name));
  if (tcol && !have.some(c => c.type === "slider") && !["line", "stacked_area", "bump", "histogram"].includes(r.kind)) {
    const what = /year/i.test(tcol.name) ? "year" : "time";
    return {text: `Add a ${what} slider`, change: {set: {controls: [...have, {type: "slider", column: tcol.name, label: lab(tcol.name), play: true}]}}, note: `Added a ${what} slider`};
  }
  const series = new Set(s.rows.map(x => x.series).filter(v => v != null && v !== ""));
  if (series.size >= 3 && ["line", "stacked_area", "stacked_bar", "scatter"].includes(r.kind) && !have.some(c => c.type === "legend")) {
    return {text: "Let readers hide series", change: {set: {controls: [...have, {type: "legend"}]}}, note: "Legend items now hide or show their series"};
  }
  return null;
}

function drawSuggest() {
  const box = $("suggest");
  const started = state.chat.some(m => m.role === "user");
  const list = state.busy || started ? [] : suggestions();
  box.replaceChildren(...list.map(t => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = typeof t === "string" ? t : t.text;
    b.onclick = () => {
      if (!state.recipe || state.busy) return;
      if (typeof t === "string") sendChat(t);
      else localChange(t.change, t.note);
    };
    return b;
  }));
  $("chat-empty").hidden = !list.length;
  fadeSuggest();
}

function fadeSuggest() {
  const box = $("suggest"), max = box.scrollWidth - box.clientWidth;
  box.classList.toggle("fade-l", box.scrollLeft > 1);
  box.classList.toggle("fade-r", box.scrollLeft < max - 1);
}
$("suggest").addEventListener("scroll", fadeSuggest, {passive: true});
$("suggest").addEventListener("wheel", e => {
  const box = e.currentTarget;
  if (!e.shiftKey || e.deltaX || !e.deltaY || box.scrollWidth <= box.clientWidth) return;
  e.preventDefault();
  box.scrollLeft += e.deltaY;
}, {passive: false});
if (typeof ResizeObserver !== "undefined") new ResizeObserver(fadeSuggest).observe($("suggest"));

function growStep(from) {
  const sec = $("step-data");
  if (from == null || !sec.animate || typeof matchMedia !== "function" || sec.offsetParent === null || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const to = sec.getBoundingClientRect().height;
  if (Math.abs(to - from) < 2) return;
  const ease = "cubic-bezier(.2, .7, .2, 1)";
  sec.style.overflow = "hidden";
  const a = sec.animate([{height: from + "px"}, {height: to + "px"}], {duration: 360, easing: ease});
  a.onfinish = a.oncancel = () => { sec.style.overflow = ""; };
  const shown = $("drop").hidden ? $("data-summary") : $("drop");
  shown.animate([{opacity: 0, transform: "translateY(6px)"}, {opacity: 1, transform: "none"}], {duration: 360, easing: ease});
}

function showData(d) {
  const swap = $("drop").hidden !== !!d;
  const from = swap && $("step-data").getBoundingClientRect ? $("step-data").getBoundingClientRect().height : null;
  state.data = d;
  $("data-summary").hidden = !d;
  $("drop").hidden = !!d;
  $("describe").hidden = !!d;
  if (!d) return growStep(from);
  $("file-name").textContent = d.name;
  $("file-mock").hidden = !d.mock;
  mockShown = null;
  $("mock-box").hidden = true;
  $("file-meta").textContent = `${d.n_rows.toLocaleString()} rows, ${d.cols.length} columns${d.truncated ? ", cut to the first 100,000 rows" : ""}`;
  $("col-list").replaceChildren(...d.cols.map(c => {
    const li = document.createElement("li");
    li.title = `${c.type}, ${c.distinct} distinct, e.g. ${(c.samples || []).join(", ")}`;
    const flag = isFlagCol(c);
    li.innerHTML = `<span class="ctype ${flag ? "flag" : c.type === "number" || c.type === "time" ? c.type : "text"}">${flag ? "flag" : c.type === "number" ? "123" : c.type === "time" ? "time" : "abc"}</span> ${esc(c.name)}`;
    return li;
  }));
  const notes = [];
  if (d.melted) notes.push(`Turned ${d.melted} year columns into rows, so time can go on an axis.`);
  (d.notes || []).forEach(n => notes.push(n));
  $("data-notes").textContent = notes.join(" ");
  const links = (d.sources || []).filter(x => x && /^https?:\/\//.test(String(x.url)));
  if (links.length) $("data-notes").append(" Sources: ", ...links.flatMap((x, i) => {
    const a = document.createElement("a");
    a.href = x.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = x.title || x.url;
    return i ? [", ", a] : [a];
  }));
  $("data-notes").hidden = !notes.length && !links.length;
  $("sheet-wrap").hidden = !(d.sheets && d.sheets.length > 1);
  if (d.sheets && d.sheets.length > 1) $("sheet").replaceChildren(...d.sheets.map(s => { const o = new Option(s, s); o.selected = s === d.sheet; return o; }));
  paintReading(d);
  drawPreview(d);
  paintSteps();
  fitScreen();
  growStep(from);
}

let readings = {list: [], current: 0};
function setReadings(res) {
  const r = res.reading || {}, seen = new Set(), list = [];
  for (const a of [{summary: r.summary, recipe: r.recipe}, ...(r.alternatives || [])]) {
    if (!a || !a.recipe) continue;
    const k = JSON.stringify(a.recipe);
    if (seen.has(k)) continue;
    seen.add(k); list.push(a);
  }
  readings = {list, current: 0};
}

function paintReading(d) {
  const r = d.reading;
  closeReadings();
  $("header-pick").hidden = true;
  $("reading").hidden = !(r && r.summary);
  if (!r || !r.summary) return;
  const pic = r.source === "picture";
  $("reading-text").textContent = r.summary;
  $("reading-tip").textContent = pic ? PIC_TIP : FILE_TIP;
  $("reading-warn-btn").setAttribute("aria-label", pic ? "Warning: some values were hard to read from the picture" : "Warning: we are not sure this file was read correctly");
  $("reading-warn").hidden = pic ? !unsureCells(d).length : !(typeof r.confidence === "number" && r.confidence < 0.7);
  $("reading-warn").classList.remove("open");
  document.querySelector(".reading-more").hidden = pic || !d.file_id;
}

const FILE_TIP = "We are not sure this file was read correctly. Check the preview, or pick another reading.";
const PIC_TIP = "Some values were hard to read from the picture. They are marked in yellow. Check them against the chart and fix them if needed.";

function unsureCells(d) {
  const p = d && d.reading && d.reading.picture;
  return p && Array.isArray(p.flagged) ? p.flagged : [];
}

function picSummary(n) {
  return n ? `Read from a chart picture, ${n} value${n === 1 ? "" : "s"} unsure, check ${n === 1 ? "it" : "them"}` : "Read from a chart picture, check the values";
}

function readNumber(text) {
  const t = String(text).trim().replace(/[\s\u00a0]/g, "");
  if (!t) return null;
  const n = Number(/^-?\d*,(\d{1,2}|\d{4,})$/.test(t) ? t.replace(",", ".") : t.replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function editCell(i, column, input) {
  const d = state.data, n = readNumber(input.value);
  if (!d || !d.rows[i]) return;
  if (n === null) { input.value = d.rows[i][column]; input.classList.add("bad"); return; }
  input.classList.remove("bad");
  input.value = n;
  d.rows[i] = {...d.rows[i], [column]: n};
  const col = d.cols.find(c => c.name === column), vals = d.rows.map(r => r[column]).filter(v => typeof v === "number");
  if (col && vals.length) { col.min = Math.min(...vals); col.max = Math.max(...vals); }
  const p = d.reading.picture;
  p.flagged = p.flagged.filter(f => !(f.row === i && f.column === column));
  d.reading.summary = picSummary(p.flagged.length);
  input.closest("td").classList.remove("unsure");
  state.data = {...d};
  paintReading(state.data);
  if (state.recipe) state.spec = buildSpec(state.recipe);
  keep();
}

function closeReadings(focus) {
  $("readings-menu").hidden = true;
  $("readings").setAttribute("aria-expanded", "false");
  if (focus) $("readings").focus();
}

function openReadings() {
  const items = readings.list.map((a, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "menuitemradio");
    b.setAttribute("aria-checked", String(i === readings.current));
    b.textContent = a.summary || `Reading ${i + 1}`;
    b.onclick = () => { closeReadings(true); if (i !== readings.current) rereadWith({recipe: a.recipe}, i); };
    return b;
  });
  const pick = document.createElement("button");
  pick.type = "button";
  pick.setAttribute("role", "menuitem");
  pick.textContent = "Choose header row…";
  pick.onclick = () => { closeReadings(); openHeaderPick(); };
  const sep = document.createElement("hr");
  sep.setAttribute("role", "separator");
  $("readings-menu").replaceChildren(...items, ...(items.length ? [sep] : []), pick);
  $("readings-menu").hidden = false;
  $("readings").setAttribute("aria-expanded", "true");
  const on = $("readings-menu").querySelector('[aria-checked="true"]') || $("readings-menu").querySelector("button");
  if (on) on.focus();
}

$("readings").onclick = () => ($("readings-menu").hidden ? openReadings() : closeReadings());
$("readings-menu").addEventListener("keydown", e => {
  const items = [...$("readings-menu").querySelectorAll("button")], i = items.indexOf(document.activeElement);
  if (e.key === "Escape") { e.preventDefault(); closeReadings(true); }
  else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
  } else if (e.key === "Home" || e.key === "End") { e.preventDefault(); items[e.key === "Home" ? 0 : items.length - 1].focus(); }
  else if (e.key === "Tab") closeReadings();
});
document.addEventListener("click", e => {
  if (!$("readings-menu").hidden && !e.target.closest(".reading-more")) closeReadings();
  if (!e.target.closest(".warn")) $("reading-warn").classList.remove("open");
});
$("reading-warn-btn").onclick = () => $("reading-warn").classList.toggle("open");
$("reading-warn").addEventListener("keydown", e => { if (e.key === "Escape") $("reading-warn").classList.remove("open"); });

function openHeaderPick() {
  const head = (state.data && state.data.raw_head) || [];
  const cur = ((readings.list[readings.current] || {}).recipe?.blocks?.[0]?.header_rows || []).at(-1);
  $("header-rows").replaceChildren(...head.map((row, i) => {
    const b = document.createElement("button");
    b.type = "button";
    const cells = row.map(v => String(v).trim()).filter(Boolean);
    b.innerHTML = `<span class="rn">Row ${i + 1}</span><span class="rc">${esc(cells.join("  |  ") || "(empty)")}</span>`;
    b.setAttribute("aria-label", `Row ${i + 1}: ${cells.join(", ") || "empty"}`);
    if (i === cur) b.setAttribute("aria-selected", "true");
    b.disabled = !cells.length;
    b.onclick = () => { $("header-pick").hidden = true; rereadWith({header_row: i}, -1); };
    return b;
  }));
  $("header-pick").hidden = false;
  const on = $("header-rows").querySelector('[aria-selected="true"]') || $("header-rows").querySelector("button:not(:disabled)");
  if (on) { on.focus(); on.scrollIntoView({block: "nearest"}); }
  fitScreen();
}
$("header-cancel").onclick = () => { $("header-pick").hidden = true; $("readings").focus(); fitScreen(); };
$("header-pick").addEventListener("keydown", e => { if (e.key === "Escape") { $("header-pick").hidden = true; $("readings").focus(); fitScreen(); } });

function toData(res) {
  const names = res.columns.map(c => c.name);
  const rows = res.rows.map(r => Object.fromEntries(names.map((n, i) => [n, r[i] == null ? "" : r[i]])));
  return {...res, rows, cols: res.columns};
}

async function rereadWith(body, index) {
  const d = state.data;
  if (!d || !d.file_id) return;
  setErr("");
  setStatus("Reading the file again…", true);
  const send = () => api("/api/viz/reread", {json: {file_id: d.file_id, sheet: d.sheet || null, ...body}});
  try {
    let res;
    try { res = await send(); }
    catch (e) {
      if (!(e.detail && e.detail.reason === "gone" && lastFile)) throw e;
      const q = new URLSearchParams({name: lastFile.name});
      if (d.sheet) q.set("sheet", d.sheet);
      await api("/api/viz/parse?" + q, {body: await lastFile.arrayBuffer(), headers: {"Content-Type": "application/octet-stream"}});
      res = await send();
    }
    if (index < 0) {
      const r = res.reading || {};
      readings.list.push({summary: r.summary || "Your header row", recipe: r.recipe});
      index = readings.list.length - 1;
    }
    readings.current = index;
    resetChart();
    state.reached = 1;
    showData(toData(res));
    go(1);
    setStatus("");
    $("readings").focus();
  } catch (e) {
    setStatus("");
    if (!(e instanceof CapError)) setErr(e.detail && e.detail.errors ? e.message + " " + e.detail.errors[0] : e.message);
  }
}

function drawPreview(d) {
  const pic = !!(d.reading && d.reading.source === "picture");
  const cols = d.cols, rows = pic ? d.rows : d.rows.slice(0, 8);
  const unsure = new Set(unsureCells(d).map(f => f.row + "\u0000" + f.column));
  const span = c => Math.max(c.name.length, ...rows.map(r => r[c.name] == null ? 0 : String(r[c.name]).length));
  const text = cols.filter(c => c.type !== "number");
  const grow = (text.length ? text : cols).reduce((a, c) => span(c) > span(a) ? c : a, (text.length ? text : cols)[0]);
  const head = document.createElement("tr");
  head.append(...cols.map(c => {
    const th = document.createElement("th");
    th.textContent = c.name;
    th.className = [c.type === "number" ? "num" : "", isFlagCol(c) ? "flag" : "", c === grow ? "grow" : ""].filter(Boolean).join(" ");
    return th;
  }));
  const aggCol = cols.find(c => c.type !== "number" && !isFlagCol(c) && rows.some(r => isAggregate(r[c.name])));
  const body = rows.map((r, i) => {
    const tr = document.createElement("tr");
    const agg = cols.some(c => c.type !== "number" && !isFlagCol(c) && isAggregate(r[c.name]));
    if (agg) tr.className = "agg";
    tr.append(...cols.map(c => {
      const td = document.createElement("td"), v = r[c.name];
      td.textContent = v == null ? "" : typeof v === "number" ? v.toLocaleString("en-GB", {maximumFractionDigits: 4}) : String(v);
      if (c.type === "number") td.className = "num";
      if (isFlagCol(c)) td.className = "flag";
      const flagged = unsure.has(i + "\u0000" + c.name);
      if (pic && c.type === "number") {
        const input = document.createElement("input");
        input.type = "text";
        input.inputMode = "decimal";
        input.className = "cell-edit";
        input.value = v == null ? "" : String(v);
        input.setAttribute("aria-label", `${c.name} for ${cols.filter(k => k.type !== "number").map(k => r[k.name]).join(", ")}${flagged ? ", unsure" : ""}, edit to fix`);
        input.onchange = () => editCell(i, c.name, input);
        input.onkeydown = e => { if (e.key === "Enter") input.blur(); };
        if (flagged) td.classList.add("unsure");
        td.replaceChildren(input);
      }
      if (agg && c === aggCol && isAggregate(v)) {
        const wrap = document.createElement("span"), txt = document.createElement("span"), tag = document.createElement("span");
        wrap.className = "agg-cell"; txt.className = "agg-name"; tag.className = "tag";
        txt.textContent = td.textContent;
        tag.textContent = "total";
        wrap.append(txt, tag);
        td.replaceChildren(wrap);
      }
      return td;
    }));
    return tr;
  });
  const thead = document.createElement("thead"), tbody = document.createElement("tbody");
  thead.append(head); tbody.append(...body);
  $("preview").replaceChildren(thead, tbody);
  $("preview-meta").textContent = d.rows.length > rows.length ? `First ${rows.length} of ${d.rows.length.toLocaleString()} rows.` : "";
}

$("preview").addEventListener("mouseover", e => {
  const c = e.target.closest("td, th");
  if (!c) return;
  if (c.scrollWidth > c.clientWidth + 1) c.title = c.textContent; else c.removeAttribute("title");
});

let lastFile = null;
const isPicture = file => /\.(png|jpe?g)$/i.test(file.name || "") || /^image\/(png|jpeg)$/.test(file.type || "");
async function loadFile(file, sheet) {
  if (!file) return;
  const pic = isPicture(file);
  if (file.size > 5 * 1024 * 1024) { setErr(pic ? "That picture is over 5 MB. Save a smaller copy and try again." : "That file is over 5 MB. Save only the sheet or columns you need and try again."); return; }
  lastFile = file;
  setErr("");
  const msg = pic ? "Reading the values from the picture…" : "Reading the file…";
  dropBusy(msg);
  setStatus(msg, true);
  try {
    const buf = await file.arrayBuffer();
    const q = new URLSearchParams({name: file.name});
    if (sheet && !pic) q.set("sheet", sheet);
    const res = await api((pic ? "/api/viz/redraw?" : "/api/viz/parse?") + q, {body: buf, headers: {"Content-Type": "application/octet-stream"}});
    forget();
    resetChart();
    state.reached = 1;
    setReadings(res);
    showData(toData(res));
    go(1);
    if (QV.loadRegionIndex) QV.loadRegionIndex();
    setStatus("");
    $("next").focus();
  } catch (e) {
    setStatus("");
    if (!(e instanceof CapError)) setErr(e.message);
  } finally {
    dropBusy("");
  }
}

const isMock = () => !!(state.data && state.data.mock);
const withMock = patches => (QV.withMockPatch ? QV.withMockPatch(patches || [], isMock()) : patches || []);
const mockChart = QVFrame.mount($("mock-chart"));
let mockShown = null;
const MOCK_SAY = {picking: "Finding a chart for it…", refining: "Naming the sample…", web: "Looking for real numbers on the web…", empty: "There's no graph to show"};

function drawMock(spec) {
  mockShown = spec;
  $("mock-box").hidden = false;
  mockChart.render({...spec, style: "franri"}, {still: true, patches: QV.withMockPatch([], spec.mock !== false)}).catch(() => null);
  paintSteps();
}

function clearMock() {
  mockShown = null;
  $("mock-box").hidden = true;
  mockChart.clear();
  paintSteps();
}

function paintMock(st) {
  $("describe-web").disabled = !st.webEligible;
  $("describe-web").checked = st.web;
  $("describe-state").textContent = st.phase === "error" || st.error ? st.error : MOCK_SAY[st.phase] || "";
  $("mock-kind").textContent = KIND_NAMES[st.kind] || "";
  $("mock-prev").hidden = $("mock-next").hidden = st.opts.length < 2;
  $("mock-tag").hidden = !st.spec || st.mock === false;
  const links = (st.spec && st.mock === false ? st.sources : []).filter(x => x && /^https?:\/\//.test(String(x.url)));
  $("mock-sources").replaceChildren(...(links.length ? ["Sources: "] : []), ...links.flatMap((x, i) => {
    const a = document.createElement("a");
    a.href = x.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = x.title || x.url;
    return i ? [", ", a] : [a];
  }));
  $("mock-sources").hidden = !links.length;
}

const typing = QV.mockTyping ? QV.mockTyping({
  post: (path, body, signal) => api(path, {json: body, signal}),
  draw: drawMock, clear: clearMock, onState: paintMock,
}) : {input() {}, setWeb: () => false, step() {}, table: () => null, stop() {}};

function loadMock() {
  const res = typing.table();
  if (!res) return false;
  typing.stop();
  lastFile = null;
  forget();
  resetChart();
  state.reached = 1;
  readings = {list: [], current: 0};
  showData(toData(res));
  return true;
}

$("describe-input").addEventListener("input", e => { setErr(""); typing.input(e.target.value); });
$("describe-web").addEventListener("change", e => { e.target.checked = typing.setWeb(e.target.checked); });
$("mock-prev").onclick = () => typing.step(-1);
$("mock-next").onclick = () => typing.step(1);
document.addEventListener("keydown", e => {
  if (state.view !== 1 || state.data || !mockShown || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
  if (e.target.closest && e.target.closest("input, textarea, select, [contenteditable]")) return;
  e.preventDefault();
  typing.step(e.key === "ArrowLeft" ? -1 : 1);
});

function dropBusy(msg) {
  const on = !!msg && $("drop").offsetParent !== null;
  $("drop").classList.toggle("loading", on);
  document.body.classList.toggle("drop-loading", on);
  $("drop-busy-text").textContent = on ? msg : "";
}

function resetChart() {
  seq++;
  if (ctrl) ctrl.abort();
  state.recipe = null; state.spec = null; state.decide = null; state.names = null; state.auto = null; state.undo = []; state.chat = []; state.opts = [];
  state.busy = false; state.drawing = false;
  pickMsg("");
  $("chat-send").disabled = false;
  setStatus("");
  chart.clear();
  $("png").disabled = $("html").disabled = true;
  drawKinds(); drawChat();
  paintSteps();
}

function startOver() {
  resetChart();
  lastFile = null;
  state.data = null;
  forget();
  state.reached = 1;
  const from = $("drop").hidden && $("step-data").getBoundingClientRect ? $("step-data").getBoundingClientRect().height : null;
  $("data-summary").hidden = true;
  $("drop").hidden = false;
  $("describe").hidden = false;
  $("describe-input").value = "";
  typing.input("");
  $("preview").replaceChildren();
  growStep(from);
  $("chat-input").value = "";
  $("file").value = "";
  setErr("");
  $("restart-ask").hidden = true;
  go(1);
  paintSteps();
  $("file").focus();
}

function askStartOver() {
  if (!state.recipe && !state.chat.length) { startOver(); return; }
  const box = $("restart-ask");
  box.hidden = !box.hidden;
  if (!box.hidden) $("restart-no").focus();
}
$("restart").onclick = askStartOver;
$("restart-yes").onclick = startOver;
$("restart-no").onclick = () => { $("restart-ask").hidden = true; $("restart").focus(); };
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("restart-ask").hidden) { $("restart-ask").hidden = true; $("restart").focus(); } });
document.addEventListener("click", e => { if (!$("restart-ask").hidden && !e.target.closest(".restart-wrap")) $("restart-ask").hidden = true; });
$("next").onclick = () => {
  if (!stepDone(state.view) || state.view >= 4) return;
  if (state.view === 1 && !state.data && !loadMock()) return;
  const n = state.view + 1;
  reach(n, n === 3 ? "chat-input" : n === 4 ? "png" : "next");
};

$("file").onchange = e => { loadFile(e.target.files[0]); e.target.value = ""; };
$("replace").onclick = () => $("file").click();
$("sheet").onchange = () => {
  if (lastFile) { loadFile(lastFile, $("sheet").value); return; }
  if (state.data) $("sheet").value = state.data.sheet || "";
  setErr("The file is no longer on the page. Load it again to pick another sheet.");
};
const drop = $("drop");
["dragenter", "dragover"].forEach(t => document.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(t => document.addEventListener(t, e => { e.preventDefault(); if (t === "drop" || !e.relatedTarget) drop.classList.remove("over"); }));
document.addEventListener("drop", e => { const f = e.dataTransfer && e.dataTransfer.files[0]; if (f) loadFile(f); });

let pickText = ["", ""];
function pickMsg(msg, head) {
  pickText = [msg || "", head || ""];
  $("pick-msg").textContent = msg || "";
  $("pick-msg").hidden = !msg;
  $("h-ask").textContent = head || "Here is the chart that fits your data best";
}

function guessKind() {
  const types = state.data.cols.map(c => c.type);
  const choice = types.includes("time") ? "line" : types.filter(t => t === "number").length >= 2 && !types.includes("category") ? "scatter" : "bar";
  return {choice, ranked: ["bar", "line", "stacked_bar", "heatmap", "scatter", "treemap", "map"].map(k => [k, 0.1]), guess: true};
}

async function autoChart() {
  if (!state.data || state.auto) return;
  const my = ++seq;
  if (ctrl) ctrl.abort();
  ctrl = new AbortController();
  const signal = ctrl.signal;
  state.auto = "running";
  state.busy = true; state.drawing = true;
  pickMsg("", "Finding the chart that fits your data best");
  paintSteps();
  setErr("");
  setStatus("", true);
  const columns = namesColumns();
  let p, failed = null;
  const told = state.data.described;
  if (told && KIND_NAMES[told.kind]) p = {choice: told.kind, ranked: [], guess: true};
  else try { p = await api("/api/viz/decide", {json: {text: "", columns, file: state.data.name || "", sheet: state.data.sheets && state.data.sheets.length > 1 ? state.data.sheet || "" : ""}, signal}); }
  catch (e) {
    if (my !== seq) return;
    failed = e;
    p = guessKind();
  }
  if (my !== seq) return;
  state.decide = p.guess ? null : p;
  const desc = state.data.described;
  if (desc) state.names = {title: desc.title || "", unit: desc.unit || "", columns: {}};
  const order = [p.choice, ...(p.ranked || []).map(r => r[0]).filter(k => k !== p.choice)];
  let recipe = null;
  const orient = ["horizontal", "vertical"].includes(state.data.orientation_hint) ? {orientation: state.data.orientation_hint} : {};
  const given = told ? {roles: told.roles, sourceUrl: state.data.source_url || "", note: (state.data.notes || [])[0] || ""} : {};
  for (const k of order) { recipe = fitsKind(k, {filters: [], source: state.data.source_hint || "", ...given, ...(k === "bar" || k === "stacked_bar" ? orient : {})}); if (recipe) break; }
  state.auto = "done";
  state.drawing = false; state.busy = false;
  setStatus("");
  if (!recipe) {
    pickMsg("No chart fits this data on its own. Go to the next step and say in the chat what you want to see.", "No chart yet");
    render();
    return;
  }
  state.recipe = withAutoControls(recipe);
  state.opts = kindOptions(recipe.kind, p.ranked);
  if (failed instanceof CapError) pickMsg("The AI budget is used up, so this is a simple first guess. You can switch the chart type above it.", "Here is a first guess at your chart");
  else if (failed) pickMsg("The AI could not be reached, so this is a simple first guess. You can switch the chart type above it.", "Here is a first guess at your chart");
  else pickMsg("");
  render();
  drawChat();
  if (failed || told) return;
  setStatus("", true);
  const roles = Object.fromEntries(Object.entries(recipe.roles).filter(([k, v]) => ["cat", "series", "t", "v", "v2"].includes(k) && v && !String(v).startsWith("(")));
  try {
    const w = await Promise.race([
      api("/api/viz/names", {json: {text: "", columns, kind: recipe.kind, roles, file: state.data.name, ...namesContext(state.recipe)}, signal}),
      new Promise(ok => setTimeout(() => ok(null), 9000)),
    ]);
    if (my !== seq || !w) return;
    state.names = w;
    state.namesFor = catKey(state.recipe);
    if (w.roles && Object.keys(w.roles).length) {
      const fixed = rolesFor(state.recipe.kind, {...state.recipe.roles, ...w.roles});
      const next = fixed && withAutoFilters({...state.recipe, roles: fixed});
      if (next && buildSpec(next).rows.length) state.recipe = withAutoControls(next);
    }
    render();
  } catch (e) {
  } finally {
    if (my === seq) { setStatus(""); paintSteps(); }
  }
}

const fileName = () => (isMock() ? "mockup-" : "") + ((state.spec && state.spec.title) || (state.recipe && state.recipe.kind) || "chart").toLowerCase()
  .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "chart";

$("png").onclick = async () => {
  if (!state.spec) return;
  try { await QV.pngFromMarkup(await chart.png(), fileName() + ".png"); } catch (e) { setErr("Could not make the PNG: " + e.message); }
};

$("html").onclick = async () => {
  if (!state.spec) return;
  try {
    const st = await chart.state();
    const page = await QV.exportHTML(state.spec, null, {...st, flagData: await chart.flags(), patches: withMock(state.recipe && state.recipe.patches)});
    QV.download(new Blob([page], {type: "text/html"}), fileName() + ".html");
  } catch (e) { setErr("Could not make the HTML file: " + e.message); }
};

function paintTheme() {
  const dark = window.QVTheme && QVTheme.get() === "dark";
  const b = $("theme");
  b.setAttribute("aria-pressed", String(dark));
  b.setAttribute("aria-label", dark ? "Light mode" : "Dark mode");
  b.title = dark ? "Light mode" : "Dark mode";
}
$("theme").onclick = () => { if (window.QVTheme) QVTheme.toggle(); };
window.addEventListener("qv-theme", paintTheme);
paintTheme();

function snapshot() {
  const parts = {};
  if (keepBox.data !== state.data) {
    keepBox.data = state.data;
    keepBox.id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    parts.data = {v: KEEP_V, id: keepBox.id, data: state.data};
  }
  const done = state.auto === "done";
  parts.ui = {v: KEEP_V, at: Date.now(), id: keepBox.id, auto: done ? "done" : null, decide: state.decide, names: state.names, namesFor: state.namesFor,
    recipe: state.recipe, undo: state.undo, chat: state.chat.filter(m => !m.pending), opts: state.opts, spec: state.spec,
    view: done ? state.view : 1, reached: done ? state.reached : 1, readings, pick: pickText, style: state.style};
  return parts;
}

function keep() {
  if (!window.QVKeep || !state.keepId || !state.data || keepBox.off) return;
  clearTimeout(keepBox.timer);
  keepBox.timer = setTimeout(keepNow, 600);
}

function keepNow() {
  clearTimeout(keepBox.timer);
  keepBox.timer = 0;
  if (!window.QVKeep || !state.keepId || keepBox.off) return Promise.resolve();
  if (!state.data) return forget();
  if (state.busy || state.drawing) { keep(); return Promise.resolve(); }
  let parts;
  try { parts = snapshot(); } catch (e) { return Promise.resolve(); }
  return QVKeep.put(state.keepId, parts).catch(() => { keepBox.data = null; });
}

function forget() {
  clearTimeout(keepBox.timer);
  keepBox.timer = 0; keepBox.data = null; keepBox.id = null;
  if (!window.QVKeep || !state.keepId) return Promise.resolve();
  return QVKeep.drop(state.keepId).catch(() => {});
}

function restoreFrom(ui, saved) {
  if (state.data || !ui || !saved || ui.v !== KEEP_V || saved.v !== KEEP_V || !ui.id || ui.id !== saved.id || !(Date.now() - ui.at < KEEP_MS)) return false;
  const d = saved.data;
  if (!d || !Array.isArray(d.cols) || !Array.isArray(d.rows) || !Array.isArray(ui.chat) || !Array.isArray(ui.undo) || !Array.isArray(ui.opts)) return false;
  try {
    readings = ui.readings && Array.isArray(ui.readings.list) ? ui.readings : {list: [], current: 0};
    showData(d);
    keepBox.data = d; keepBox.id = ui.id;
    Object.assign(state, {auto: ui.auto === "done" ? "done" : null, decide: ui.decide || null, names: ui.names || null, namesFor: ui.namesFor,
      recipe: ui.recipe || null, undo: ui.undo, chat: ui.chat, opts: ui.opts, spec: ui.spec || null, busy: false, drawing: false});
    state.reached = state.auto ? Math.min(4, Math.max(1, ui.reached | 0)) : 1;
    const pick = Array.isArray(ui.pick) ? ui.pick : [];
    pickMsg(pick[0], pick[1]);
    if (QV.loadRegionIndex) QV.loadRegionIndex();
    render();
    drawChat();
    go(Math.min(state.reached, Math.max(1, ui.view | 0)));
    return true;
  } catch (e) {
    readings = {list: [], current: 0};
    startOver();
    return false;
  }
}

function browserId() {
  try {
    let id = localStorage.getItem("quickviz-browser");
    if (!id) { id = Date.now().toString(36) + Math.random().toString(36).slice(2, 10); localStorage.setItem("quickviz-browser", id); }
    return id;
  } catch (e) { return "this-browser"; }
}

async function boot() {
  if (!window.QVKeep) return;
  state.keepId = state.keepId || browserId();
  QVKeep.prune(KEEP_MS).catch(() => {});
  let got = null;
  try { got = await QVKeep.get(state.keepId); } catch (e) { return; }
  if (state.data || !got || (!got.ui && !got.data)) return;
  if (!restoreFrom(got.ui, got.data) && !state.data) forget();
}

window.addEventListener("pagehide", () => { if (keepBox.timer) keepNow(); });
window.QVSave = () => (keepBox.timer ? keepNow() : Promise.resolve());
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden" && keepBox.timer) keepNow(); });

QV.ready.then(() => { if (state.recipe) render(); });
paintSteps();
drawChat();
boot();
