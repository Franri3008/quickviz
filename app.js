const $ = id => document.getElementById(id);
const svgEl = $("chart");
const webdataEl = $("webdata");
const webSourcesEl = $("web-sources");
let seq = 0, timer = null, csvTimer = null, ctrl = null;
let state = {kind: null, ranked: [], fill: null, text: "", data: null, spec: null, colRoles: {}, opts: [], idx: 0, names: null, fixes: {}, webEligible: false, webSpecs: null};
let lastPick = null;

async function post(path, body, signal) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal});
  let j = {};
  try { j = await r.json(); } catch (e) { }
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
function setErr(msg) { $("err").textContent = msg ? String(msg).slice(0, 200) : ""; }
function setCached(on) { $("cached").hidden = !on; }
function haveQV() {
  if (window.QV && QV.render) return true;
  setErr("Charts did not load (window.QV missing)");
  return false;
}

const NUM_RE = /^[-+]?[$€£]?\s*(\d{1,3}(,\d{3})+|\d+)?(\.\d+)?([eE][-+]?\d+)?\s*%?$/;
const toNum = s => +String(s).replace(/[,$€£%\s]/g, "");
const isNum = s => s !== "" && NUM_RE.test(s) && /\d/.test(s) && !isNaN(toNum(s));
const TIME_NAME = /^(year|yr|date|month|time|quarter|qtr|week|day|period|season|fy|timestamp|datetime|hour)s?$|(_|\b)(year|date|month|quarter|week|day|period|season|time)$/i;
const DATE_RE = /^(\d{4}([-\/.]\d{1,2}([-\/.]\d{1,2})?)?|\d{4}[- ]?(q|Q)[1-4]|(q|Q)[1-4][- ]?\d{4}|\d{4}[- ]?(w|W)\d{1,2}|\d{1,2}[-\/.]\d{1,2}[-\/.]\d{2,4}|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?([- ]\d{2,4})?)([ T]\d{1,2}:\d{2}(:\d{2})?)?$/i;

function parseJSON(text) {
  let j;
  try { j = JSON.parse(text); } catch (e) { return null; }
  if (j && !Array.isArray(j) && typeof j === "object") {
    const arrs = Object.values(j).filter(Array.isArray);
    if (arrs.length === 1 && typeof arrs[0][0] === "object") j = arrs[0];
    else if (arrs.length > 1 && arrs.length === Object.keys(j).length)
      j = d3.range(d3.max(arrs, a => a.length)).map(i => Object.fromEntries(Object.entries(j).map(([k, a]) => [k, a[i]])));
  }
  if (!Array.isArray(j) || !j.length || typeof j[0] !== "object") return null;
  const names = [...new Set(j.flatMap(r => Object.keys(r || {})))];
  const rows = j.map(r => Object.fromEntries(names.map(n => [n, r?.[n] == null ? "" : typeof r[n] === "object" ? JSON.stringify(r[n]) : String(r[n]).trim()])));
  return {rows, cols: names.map(name => colInfo(name, rows.map(r => r[name]).filter(v => v !== "")))};
}

function parseText(text) {
  text = text.replace(/^﻿/, "").trim();
  if (!text) return null;
  if (/^[\[{]/.test(text)) return parseJSON(text);
  const head = text.split("\n", 1)[0];
  const n = ch => head.split(ch).length - 1;
  const sep = n("\t") > 0 && n("\t") >= n(",") ? "\t" : n(";") > n(",") ? ";" : ",";
  const raw = d3.dsvFormat(sep).parse(text);
  const names = raw.columns.map(c => c.trim()).filter(Boolean);
  if (!names.length || !raw.length) return null;
  const rows = raw.map(r => { const o = {}; for (const c of raw.columns) o[c.trim()] = (r[c] ?? "").trim(); return o; });
  const cols = names.map(name => colInfo(name, rows.map(r => r[name]).filter(v => v !== "")));
  return {rows, cols};
}

function colInfo(name, vals) {
  const distinct = new Set(vals).size;
  const nNum = vals.filter(isNum).length, nDate = vals.filter(v => DATE_RE.test(v)).length;
  const ints = vals.every(v => isNum(v) && Number.isInteger(toNum(v)));
  const yearLike = ints && vals.length && vals.every(v => toNum(v) >= 1800 && toNum(v) <= 2100);
  let type = "category";
  if (!vals.length) type = "category";
  else if (TIME_NAME.test(name) && (nDate >= 0.9 * vals.length || yearLike || ints || !nNum)) type = "time";
  else if (yearLike && distinct > 1 && distinct < vals.length * 0.9 + 2) type = "time";
  else if (nNum >= 0.9 * vals.length) type = "number";
  else if (nDate >= 0.9 * vals.length) type = "time";
  return {name, type, distinct, samples: [...new Set(vals)].slice(0, 3)};
}

function summary(d) {
  return `${d.rows.length} rows. Columns: ` + d.cols.map(c =>
    `${c.name} (${c.type}, ${c.distinct} distinct, e.g. ${c.samples.map(s => String(s).slice(0, 20)).join(", ")})`).join("; ") + ".";
}

function showData(d, name) {
  state.data = d ? {...d, name} : null;
  if (d) state.webSpecs = null;
  if (d) { webdataEl.checked = false; state.webEligible = false; }
  webdataEl.disabled = !!d || !state.webEligible;
  $("clear").hidden = !d;
  $("colsum").textContent = d ? `${name ? name + " / " : ""}${d.rows.length} rows / ` +
    d.cols.map(c => `${c.name} ${c.type === "number" ? "#" : c.type === "time" ? "time" : "cat " + c.distinct}`).join(" / ") : "";
}

const NEED = {
  bar: ["cat", "v"], treemap: ["cat", "v"], donut: ["cat", "v"], map: ["cat", "v"],
  line: ["t", "v", "series?"], stacked_area: ["t", "series", "v"],
  stacked_bar: ["cat", "series", "v"], heatmap: ["cat", "series", "v"], sankey: ["cat", "series", "v"],
  dot_range: ["cat", "series", "v"], scatter: ["v", "v2", "series?"], histogram: ["v"], bump: ["t", "cat", "v"],
};
const RATE_NAME = /rate|pct|percent|share|avg|average|mean|median|price|score|index|ratio|temp|age|rank|%/i;

function fits(r, c, kind) {
  if (!c) return false;
  if (r === "v" || r === "v2") return c.type === "number";
  if (r === "t") return c.type === "time";
  if (r === "series") return c.type !== "number" && c.distinct >= 2 && (kind === "dot_range" || c.distinct <= (kind === "sankey" ? 30 : 20));
  if (r === "cat") return c.type !== "number";
  return false;
}

function guess(r, cols, used, kind) {
  const free = cols.filter(c => !used.has(c.name) && fits(r, c, kind));
  if (!free.length) return null;
  const score = c => {
    if (r === "t") return (c.type === "time" ? 1000 : 0) - c.distinct / 1000;
    if (r === "series") return (kind === "dot_range" ? (c.distinct === 2 ? 100 : 0) : 0) - c.distinct + (c.type === "category" ? 5 : 0);
    if (r === "cat") return (c.type === "category" ? 100 : 0) + Math.min(c.distinct, 50);
    if (r === "v" || r === "v2") return (/^(id|index|#)$/i.test(c.name) ? -100 : 0) - cols.indexOf(c) * 0.01;
    return 0;
  };
  return free.sort((a, b) => score(b) - score(a))[0].name;
}

function wideCols(cols, used) { return cols.filter(c => c.type === "number" && !used.has(c.name)).slice(0, 8).map(c => c.name); }

function heuristicMap(kind, cols, jev = {}) {
  const map = {}, used = new Set(), how = {};
  const need = NEED[kind] || [];
  const byName = Object.fromEntries(cols.map(c => [c.name, c]));
  for (const spec of need) {
    const r = spec.replace("?", ""), opt = spec.endsWith("?");
    if (r === "v" || r === "v2") continue;
    const j = jev[r];
    if (j === "(none)" && opt) { how[r] = "none"; continue; }
    if (j && fits(r, byName[j], kind) && !used.has(j)) { map[r] = j; how[r] = "jev"; used.add(j); continue; }
    const g = opt ? (r === "series" ? guess(r, cols.filter(c => c.type === "category"), used, kind) : null) : guess(r, cols, used, kind);
    if (g) { map[r] = g; how[r] = "guess"; used.add(g); continue; }
    if (opt) continue;
    if (r === "series") { map.series = "(columns)"; how.series = "wide"; continue; }
    if (r === "v2") return null;
    return null;
  }
  if (need.includes("v")) {
    const j = jev.v;
    if (map.series === "(columns)") {
      const w = wideCols(cols, used);
      if (w.length < 2) return null;
      map.wide = w; map.v = "(value)"; how.v = "wide";
    } else if (j && fits("v", byName[j], kind) && !used.has(j)) { map.v = j; how.v = "jev"; used.add(j); }
    else {
      const g = guess("v", cols, used, kind);
      if (g) { map.v = g; how.v = "guess"; used.add(g); }
      else if (kind === "histogram" || kind === "scatter") return null;
      else { map.v = "(count)"; how.v = "count"; }
    }
  }
  if (kind === "scatter") {
    const j = jev.v2;
    if (j && fits("v2", byName[j], kind) && !used.has(j)) { map.v2 = j; how.v2 = "jev"; }
    else { const g = guess("v2", cols, used, kind); if (!g) return null; map.v2 = g; how.v2 = "guess"; }
  }
  return {map, how};
}

function timeSorter(vals) {
  if (vals.every(isNum)) return (a, b) => toNum(a) - toNum(b);
  if (vals.every(v => !isNaN(Date.parse(v)))) return (a, b) => Date.parse(a) - Date.parse(b);
  const order = new Map(vals.map((v, i) => [v, i]));
  return (a, b) => order.get(a) - order.get(b);
}

function aggregate(kind, data, map) {
  let rows = data.rows;
  if (map.wide) rows = rows.flatMap(r => map.wide.map(w => ({...r, "(columns)": w, "(value)": r[w]})));
  const val = r => map.v === "(count)" ? 1 : toNum(r[map.v]);
  const good = r => map.v === "(count)" || isNum(r[map.v]);
  const mean = map.v !== "(count)" && RATE_NAME.test(map.v);
  const agg = (keys) => {
    const m = new Map();
    for (const r of rows) {
      if (!good(r)) continue;
      const k = keys.map(f => String(r[map[f]] ?? ""));
      if (k.some(x => x === "")) continue;
      const id = JSON.stringify(k);
      const e = m.get(id) || {k, s: 0, n: 0};
      e.s += val(r); e.n += 1; m.set(id, e);
    }
    return [...m.values()].map(e => {
      const o = {}; keys.forEach((f, i) => o[f] = e.k[i]);
      o.v = mean ? e.s / e.n : e.s; return o;
    });
  };
  const topBy = (out, f, n) => {
    const tot = d3.rollup(out, g => d3.sum(g, d => Math.abs(d.v)), d => d[f]);
    const keep = new Set([...tot].sort((a, b) => b[1] - a[1]).slice(0, n).map(d => d[0]));
    return out.filter(d => keep.has(d[f]));
  };
  const sortT = out => { const s = timeSorter([...new Set(out.map(d => d.t))]); return out.sort((a, b) => s(a.t, b.t)); };
  let out;
  switch (kind) {
    case "map":
      out = agg(["cat"]); break;
    case "bar": case "treemap":
      out = agg(["cat"]).sort((a, b) => b.v - a.v).slice(0, kind === "bar" ? 25 : 60); break;
    case "donut": {
      const all = agg(["cat"]).sort((a, b) => b.v - a.v);
      out = all.slice(0, 5);
      if (all.length > 5) out.push({cat: "Other", v: d3.sum(all.slice(5), d => d.v)});
      break;
    }
    case "line":
      out = map.series ? topBy(agg(["t", "series"]), "series", 8) : agg(["t"]); out = sortT(out); break;
    case "stacked_area":
      out = sortT(topBy(agg(["t", "series"]), "series", 8)); break;
    case "stacked_bar": case "heatmap":
      out = topBy(topBy(agg(["cat", "series"]), "cat", kind === "heatmap" ? 30 : 20), "series", kind === "heatmap" ? 30 : 8); break;
    case "sankey":
      out = topBy(agg(["cat", "series"]), "cat", 15).filter(d => d.cat !== d.series && d.v > 0); break;
    case "dot_range": {
      let a = agg(["cat", "series"]);
      const ss = [...new Set(a.map(d => d.series))];
      const sorter = timeSorter(ss);
      const two = ss.length > 2 ? [ss.slice().sort(sorter)[0], ss.slice().sort(sorter).at(-1)] : ss;
      a = a.filter(d => two.includes(d.series));
      const both = new Set([...d3.rollup(a, g => g.length, d => d.cat)].filter(d => d[1] === 2).map(d => d[0]));
      out = topBy(a.filter(d => both.has(d.cat)), "cat", 25); break;
    }
    case "scatter":
      out = rows.filter(r => isNum(r[map.v]) && isNum(r[map.v2])).slice(0, 3000).map(r => {
        const o = {v: toNum(r[map.v]), v2: toNum(r[map.v2])};
        if (map.series) o.series = r[map.series];
        return o;
      });
      break;
    case "histogram":
      out = rows.filter(r => isNum(r[map.v])).slice(0, 20000).map(r => ({v: toNum(r[map.v])})); break;
    case "bump": {
      let a = agg(["t", "cat"]);
      const isRank = /rank|position|place|pos\b/i.test(map.v || "");
      if (!isRank) {
        const byT = d3.group(a, d => d.t);
        a = [...byT.values()].flatMap(g => g.sort((x, y) => y.v - x.v).map((d, i) => ({...d, v: i + 1})));
      }
      const best = d3.rollup(a, g => d3.min(g, d => d.v), d => d.cat);
      const keep = new Set([...best].sort((x, y) => x[1] - y[1]).slice(0, 10).map(d => d[0]));
      out = sortT(a.filter(d => keep.has(d.cat))); break;
    }
    default: out = [];
  }
  return out;
}

const LABEL = {"(count)": "Count", "(value)": "Value", "(columns)": ""};
function buildSpec(kind, map) {
  const d = state.data, nm = state.names || {}, lab = n => nm.columns?.[n] || (LABEL[n] ?? n ?? "");
  const rows = aggregate(kind, d, map);
  const xy = {
    scatter: [lab(map.v), lab(map.v2)], histogram: [lab(map.v), "Count"],
    line: [lab(map.t), lab(map.v)], stacked_area: [lab(map.t), lab(map.v)], bump: [lab(map.t), "Rank"],
    heatmap: [lab(map.series), lab(map.v)], dot_range: [lab(map.v), lab(map.cat)],
  }[kind] || [lab(map.cat), lab(map.v)];
  const title = nm.title || "";
  const unit = /%|pct|percent/i.test(map.v || "") ? "%" : /\$|usd|dollar/i.test(map.v || "") ? "$" : /€|eur/i.test(map.v || "") ? "€" : (nm.unit || "");
  return {kind, title, xLabel: xy[0], yLabel: xy[1], unit, mock: false, rows};
}

function renderSpec(spec) {
  if (!haveQV()) return;
  state.spec = spec;
  QV.render(svgEl, spec);
  $("png").hidden = $("html").hidden = false;
}

function sameThought(a = "", b = "") { a = a.toLowerCase(); b = b.toLowerCase(); return !!a && !!b && (a.startsWith(b) || b.startsWith(a)); }

function drawMock() {
  if (!haveQV() || !state.kind) return;
  const f = state.fill && sameThought(state.text, state.fillText) ? state.fill : {};
  renderSpec(QV.mock(state.kind, f, state.kind + "|" + (f.title || state.text)));
}

function hintsFor(kind, cols) {
  const byRole = r => cols.filter(c => state.colRoles[c.name]?.role === r)
    .sort((a, b) => (state.colRoles[b.name].confidence ?? 0) - (state.colRoles[a.name].confidence ?? 0)).map(c => c.name);
  const names = byRole("name"), values = byRole("value"), times = byRole("time"), groups = byRole("group");
  const catList = [...names, ...groups], serList = [...groups, ...names, ...times];
  const h = {v: values[0], v2: values[1], t: times[0]};
  if ((NEED[kind] || []).includes("cat")) h.cat = catList[0];
  h.series = serList.find(x => x !== h.cat && x !== h.t);
  if (kind === "line" && !h.series) h.series = "(none)";
  const at = n => cols.findIndex(c => c.name === n);
  if (kind === "sankey" && h.cat && h.series && at(h.series) < at(h.cat)) [h.cat, h.series] = [h.series, h.cat];
  return h;
}

function countryShare(rows, col) {
  const vals = [...new Set(rows.map(r => r[col]).filter(Boolean))];
  return vals.length ? vals.filter(v => QV.countryId(v)).length / vals.length : 0;
}

function specFor(kind) {
  const d = state.data;
  const kept = d.cols.filter(c => state.colRoles[c.name]?.role !== "ignore");
  const cols = kept.length ? kept : d.cols;
  const m = heuristicMap(kind, cols, {...hintsFor(kind, cols), ...(state.fixes[kind] || {})}) || heuristicMap(kind, d.cols);
  if (!m) return null;
  // a map needs a column of real country names
  // a map needs a column of real countries, or of regions of one country
  if (kind === "map" && !(QV.countryId && (countryShare(d.rows, m.map.cat) >= 0.5 ||
      QV.regionCountry([...new Set(d.rows.map(r => r[m.map.cat]).filter(Boolean))])))) return null;
  const spec = buildSpec(kind, m.map);
  return spec.rows.length ? {spec, m} : null;
}

function drawData(kind) {
  const f = specFor(kind);
  if (!f) return false;
  const {spec, m} = f;
  renderSpec(spec);
  const roleText = Object.entries(m.map).filter(([k]) => k !== "wide").map(([k, v]) =>
    `${k}=${v === "(columns)" ? m.map.wide.join("+") : v}${m.how[k] === "guess" ? " (rule)" : ""}`).join(", ");
  const r = $("roles");
  if (r) r.textContent = roleText;
  return true;
}

const MIN_P = 0.05;
function buildOpts() {
  const ranked = state.ranked.length ? state.ranked.filter(([k, p]) => p >= MIN_P || k === state.kind).map(r => r[0]) : [state.kind];
  state.opts = state.data ? ranked.filter(k => k === state.kind || specFor(k)) : ranked;
  state.idx = Math.max(0, state.opts.indexOf(state.kind));
}

function showCycle() {
  const n = state.opts.length, k = state.opts[state.idx];
  const p = (state.ranked.find(r => r[0] === k) || [])[1];
  $("prev").hidden = $("next").hidden = n < 2;
  $("optcount").textContent = n ? `${state.idx + 1} of ${n}${p != null ? ` — ${k} ${p.toFixed(2)}` : ""}` : "";
}

function step(delta) {
  const n = state.opts.length;
  if (n < 2) return;
  switchKind(state.opts[(state.idx + delta + n) % n]);
}

$("prev").onclick = () => step(-1);
$("next").onclick = () => step(1);
document.addEventListener("keydown", e => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
  if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "ArrowRight") { step(1); e.preventDefault(); }
  if (e.key === "ArrowLeft") { step(-1); e.preventDefault(); }
});

function showAlts() {
  $("alts").innerHTML = state.ranked.filter(([k]) => k !== state.kind && state.opts.includes(k)).slice(0, 2).map(([k, v]) =>
    `<span data-k="${esc(k)}">${esc(k)} ${v.toFixed(2)}</span>`).join("");
  document.querySelectorAll("#alts span").forEach(s => s.onclick = () => switchKind(s.dataset.k));
  state.idx = Math.max(0, state.opts.indexOf(state.kind));
  showCycle();
}

async function switchKind(kind) {
  const my = ++seq;
  if (ctrl) ctrl.abort();
  ctrl = new AbortController();
  setErr("");
  const prev = state.kind;
  state.kind = kind;
  if (state.webSpecs?.[kind]) { renderSpec(state.webSpecs[kind]); showAlts(); return; }
  if (!state.data) { drawMock(); if (!state.fill) fillLabels(my, ctrl.signal); showAlts(); return; }
  const ok = drawData(kind);
  if (!ok) { state.kind = prev; setErr(`This data has no columns that fit a ${kind} chart`); }
  showAlts();
  $("meta").querySelector("b") && ($("meta").querySelector("b").textContent = state.kind);
}

async function applyWords(promise, my, key) {
  setPhase("refining");
  try {
    const w = await Promise.race([promise, new Promise((_, no) => setTimeout(() => no(new Error("The check took too long, showing the chart as drawn")), 6000))]);
    if (my !== seq) return;
    state[key] = w;
    if (key === "fill") state.fillText = state.text;
    if (key === "names" && w.roles && Object.keys(w.roles).length) state.fixes[state.kind] = w.roles;
    if (w.cached) setCached(true);
    if (key === "fill") drawMock(); else drawData(state.kind);
    const fixed = key === "names" && w.roles && Object.keys(w.roles).length ? `, fixed ${Object.keys(w.roles).join(" and ")}` : "";
    $("meta").insertAdjacentText("beforeend", ` — checked by ${(w.model || "LLM").split("/").pop()} ${w.ms} ms${fixed}`);
  } catch (e) {
    if (e.name !== "AbortError" && my === seq && !/too long/.test(e.message)) setErr(/Too many/.test(e.message) ? e.message : "The check failed, showing the chart as drawn");
  } finally {
    if (my === seq) setPhase("");
  }
}

function currentMap() {
  const d = state.data;
  if (!d) return null;
  const kept = d.cols.filter(c => state.colRoles[c.name]?.role !== "ignore");
  const cols = kept.length ? kept : d.cols;
  const m = heuristicMap(state.kind, cols, {...hintsFor(state.kind, cols), ...(state.fixes[state.kind] || {})}) || heuristicMap(state.kind, d.cols);
  return m && m.map;
}

(() => {
  const css = document.createElement("style");
  css.textContent = `
.qv-refining{position:absolute;inset:0;z-index:3;pointer-events:none;display:flex;align-items:center;justify-content:center;
  background:rgba(12,14,14,.55);opacity:0;visibility:hidden;transition:opacity .2s,visibility .2s}
body[data-qv-phase="refining"] .qv-refining{opacity:1;visibility:visible}
.qv-refining span{width:34px;height:34px;border-radius:50%;border:3px solid rgba(255,255,255,.25);border-top-color:#fff;animation:qv-spin .8s linear infinite}
@keyframes qv-spin{to{transform:rotate(360deg)}}`;
  document.head.prepend(css);
  const ov = document.createElement("div");
  ov.className = "qv-refining";
  ov.innerHTML = "<span></span>";
  ov.setAttribute("aria-hidden", "true");
  (svgEl.parentNode || document.body).appendChild(ov);
})();
function setPhase(p) { if (p) document.body.dataset.qvPhase = p; else delete document.body.dataset.qvPhase; }

function showEmpty() {
  seq++;
  if (ctrl) ctrl.abort();
  state.kind = null; state.spec = null; state.opts = []; state.ranked = []; state.webSpecs = null;
  svgEl.innerHTML = "";
  $("meta").textContent = "There's no graph to show";
  $("alts").innerHTML = ""; $("optcount").textContent = "";
  $("prev").hidden = $("next").hidden = $("png").hidden = $("html").hidden = true;
  state.webEligible = false;
  webdataEl.checked = false;
  webdataEl.disabled = true;
  webSourcesEl.hidden = true;
  dispatchEvent(new CustomEvent("qv:web-state", {detail: "done"}));
  setPhase("empty");
}

function showWebSources(sources) {
  webSourcesEl.replaceChildren();
  if (!sources?.length) { webSourcesEl.hidden = true; return; }
  const label = document.createElement("span");
  label.textContent = "Sources:";
  webSourcesEl.append(label);
  for (const source of sources) {
    const link = document.createElement("a");
    link.href = source.url;
    link.textContent = source.title;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    webSourcesEl.append(link);
  }
  webSourcesEl.hidden = false;
}

async function fillLabels(my, signal) {
  const text = state.text;
  if (!text) return;
  try {
    const f = await post("/api/fill", {text, kind: state.kind}, signal);
    if (my !== seq) return;
    state.fill = f; drawMock();
    if (f.cached) setCached(true);
    $("meta").innerHTML += ` — labels ${f.ms} ms`;
  } catch (e) {
    if (e.name !== "AbortError" && my === seq) setErr(/Too many/.test(e.message) ? e.message : "Labels failed, showing generic ones");
  }
}

async function run() {
  const text = state.text, d = state.data;
  if (!d && text.length < 4) return;
  let useWeb = !d && webdataEl.checked;
  const my = ++seq;
  if (ctrl) ctrl.abort();
  ctrl = new AbortController();
  const t0 = performance.now();
  setCached(false);
  showWebSources([]);
  state.webSpecs = null;
  if (useWeb) {
    state.spec = null;
    state.opts = [];
    svgEl.replaceChildren();
    $("png").hidden = $("html").hidden = true;
    $("optcount").textContent = "";
    dispatchEvent(new CustomEvent("qv:web-state", {detail: "loading"}));
  }
  try {
    const signal = ctrl.signal;
    const columns = d && d.cols.map(c => ({name: c.name, type: c.type, distinct: c.distinct, samples: c.samples}));
    if (d) { state.names = null; state.fixes = {}; }
    const p = d ? await post("/api/decide", {text, columns}, signal)
      : lastPick?.text === text ? lastPick.result : await post("/api/pick", {text}, signal);
    if (my !== seq) return;
    if (!d) {
      lastPick = {text, result: p};
      state.webEligible = Number(p.web_data) >= 0.7;
      webdataEl.disabled = !state.webEligible;
      if (!state.webEligible && useWeb) {
        useWeb = false;
        webdataEl.checked = false;
        dispatchEvent(new CustomEvent("qv:web-state", {detail: "done"}));
      }
    }
    if (!d && p.chartable != null && p.chartable < 0.5) return showEmpty();
    if (my !== seq) return;
    setErr("");
    if (p.cached) setCached(true);
    const total = Math.round(performance.now() - t0);
    $("meta").innerHTML = `<b>${esc(p.choice)}</b> — confidence ${(p.confidence ?? 0).toFixed(2)} — Jev ${p.ms} ms, round trip ${total} ms${d ? ` — ${Object.keys(p.columns || {}).length} column roles in the same call — <span id="roles"></span>` : ""}`;
    state.ranked = p.ranked || [];
    const kindChanged = p.choice !== state.kind;
    if (useWeb) {
      state.kind = p.choice;
      state.fill = null;
      state.opts = [state.kind];
      showAlts();
      const found = await post("/api/web-data", {text, kind: state.kind}, signal);
      if (my !== seq) return;
      state.webSpecs = {[found.spec.kind]: found.spec, ...(found.alternatives || {})};
      state.opts = Object.keys(state.webSpecs);
      renderSpec(found.spec);
      showCycle();
      if (found.cached) setCached(true);
      showWebSources(found.sources);
      return;
    }
    if (!d) {
      state.kind = p.choice;
      buildOpts(); showAlts(); drawMock();
      await applyWords(post("/api/fill", {text, kind: state.kind}, signal), my, "fill");
      return;
    }
    state.colRoles = p.columns || {};
    const order = [p.choice, ...state.ranked.map(r => r[0]).filter(k => k !== p.choice)];
    for (const k of order) {
      state.kind = k;
      if (drawData(k)) break;
    }
    $("meta").querySelector("b").textContent = state.kind + (state.kind !== p.choice ? ` (Jev said ${p.choice}, no fit)` : "");
    buildOpts(); showAlts();
    const roles = Object.fromEntries(Object.entries(currentMap() || {}).filter(([k, v]) => ["cat", "series", "t", "v", "v2"].includes(k) && !v.startsWith("(")));
    await applyWords(post("/api/names", {text, columns, kind: state.kind, roles}, signal), my, "names");
  } catch (e) {
    if (e.name !== "AbortError" && my === seq) setErr(e.message);
  } finally {
    if (useWeb && my === seq) dispatchEvent(new CustomEvent("qv:web-state", {detail: "done"}));
  }
}

webdataEl.addEventListener("change", () => {
  if (state.data || !state.webEligible) { webdataEl.checked = false; return; }
  state.fill = null;
  state.kind = null;
  clearTimeout(timer);
  if (state.text.length >= 4) run();
  else showEmpty();
});

$("q").addEventListener("input", e => {
  clearTimeout(timer);
  const previousText = state.text;
  state.text = e.target.value.trim();
  if (state.text !== previousText) {
    lastPick = null;
    seq++;
    if (ctrl) ctrl.abort();
    setPhase("");
    state.webEligible = false;
    webdataEl.disabled = true;
  }
  if (state.demo) {
    state.demo = false;
    $("csv").value = ""; $("csv").readOnly = false;
    showData(null); state.kind = null;
  }
  if (!state.data && state.text.length < 4) return showEmpty();
  if (document.body.dataset.qvPhase === "empty") setPhase("");
  timer = setTimeout(run, webdataEl.checked ? 700 : 200);
});

function loadText(text, name) {
  const d = parseText(text);
  if (!d) { showData(null); setErr(text.trim() ? "Could not read that as CSV, TSV or JSON" : ""); return; }
  // region names (Chilean regions, US states) need the region index before a map can be offered
  if (QV.loadRegionIndex) QV.loadRegionIndex().then(() => { if (state.data === d || state.data?.rows === d.rows) { buildOpts(); showAlts(); } });
  setErr("");
  showData(d, name);
  run();
}

$("csv").addEventListener("input", e => {
  clearTimeout(csvTimer);
  state.demo = false;
  csvTimer = setTimeout(() => loadText(e.target.value, "pasted"), 300);
});

$("file").addEventListener("change", async e => {
  const f = e.target.files[0];
  if (!f) return;
  if (f.size > 20e6) return setErr("File is over 20 MB");
  const text = await f.text();
  $("csv").value = text.length > 20000 ? text.slice(0, 20000) + "\n…" : text;
  $("csv").readOnly = text.length > 20000;
  state.demo = false;
  loadText(text, f.name);
  e.target.value = "";
});

$("clear").onclick = () => {
  $("csv").value = ""; $("csv").readOnly = false;
  showData(null); state.kind = null;
  if (state.text.length >= 4) run();
};

const fileName = () => ((state.spec && state.spec.title) || state.kind || "chart").toLowerCase()
  .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "chart";

$("png").onclick = () => {
  if (!haveQV() || !QV.exportPNG) return;
  QV.exportPNG(svgEl, fileName() + ".png");
};

$("html").onclick = async () => {
  if (!state.spec) return;
  const code = await (await fetch("charts.js")).text();
  const safe = t => t.replace(/<\/(script)/gi, "<\\/$1");
  const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(state.spec.title || "Chart")}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&display=swap">
<script src="https://cdn.jsdelivr.net/npm/d3@7"><\/script>
<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12"><\/script>
<style>html,body{height:100%;margin:0;background:#fff}
body{box-sizing:border-box;padding:24px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
#chart{display:block;width:100%;height:100%;overflow:visible}</style>
</head><body>
<svg id="chart"></svg>
<script>window.QV_GEO_BASE = ${JSON.stringify(new URL(".", location.href).href)};<\/script>
<script>${safe(code)}<\/script>
<script>
const spec = ${safe(JSON.stringify(state.spec))};
const el = document.getElementById("chart");
function fit() {
  const box = document.body.getBoundingClientRect(), pad = 48;
  const aspect = Math.max(0.6, (box.width - pad) / Math.max(200, box.height - pad));
  QV.render(el, spec, {width: Math.max(360, 420 * aspect)});
  el.removeAttribute("width"); el.removeAttribute("height");
}
fit();
let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(fit, 150); });
<\/script>
</body></html>
`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([page], {type: "text/html"}));
  a.download = fileName() + ".html";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};

(async () => {
  try {
    const r = await fetch("demo/demos.json");
    if (!r.ok) return;
    const demos = await r.json();
    if (!Array.isArray(demos) || !demos.length) return;
    const box = $("demos");
    box.innerHTML = "Try: " + demos.map((dm, i) => `<button type="button" data-i="${i}">${esc(dm.name || "Demo " + (i + 1))}</button>`).join("");
    box.hidden = false;
    box.querySelectorAll("button").forEach(b => b.onclick = async () => {
      const dm = demos[+b.dataset.i];
      let csv = dm.csv || "";
      if (!csv.includes("\n")) {
        const path = /^(demo\/|\/|https?:)/.test(csv) ? csv : "demo/" + csv;
        const res = await fetch(path);
        if (!res.ok) return setErr(`Demo file ${csv} not found`);
        csv = await res.text();
      }
      $("q").value = dm.description || "";
      state.text = $("q").value.trim();
      $("csv").value = csv; $("csv").readOnly = false;
      loadText(csv, dm.name || "demo");
      state.demo = !!state.data;
    });
  } catch (e) { }
})();

// ---------- version, from the qv-version meta tag the server fills in ----------
(() => {
  const v = document.querySelector('meta[name="qv-version"]')?.content;
  if (!v || v.includes("__")) return;
  window.QV_VERSION = v;
  const el = document.createElement("div");
  el.id = "qv-version";
  el.textContent = "v" + v;
  el.style.cssText = "position:fixed;right:12px;bottom:10px;font:500 11px -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;opacity:.45;pointer-events:none";
  document.body.appendChild(el);
})();
