(function () {
  const QV = window.QV;
  if (!QV) throw new Error("charts-mock.js needs charts.js loaded first");

  const MOCK_SOURCE = "Mockup data, not real numbers";
  const WORLD = ["United States", "Brazil", "China", "India", "Germany", "Nigeria", "Australia", "Canada", "Russia", "Mexico",
    "Indonesia", "South Africa", "Argentina", "France", "Japan", "Egypt"];
  const NEED = {
    bar: ["cat", "v"], treemap: ["cat", "v"], donut: ["cat", "v"], map: ["cat", "v"],
    line: ["t", "series", "v"], stacked_area: ["t", "series", "v"],
    stacked_bar: ["cat", "series", "v"], heatmap: ["cat", "series", "v"], sankey: ["cat", "series", "v"],
    dot_range: ["cat", "series", "v"], scatter: ["v", "v2", "series"], histogram: ["v"], bump: ["t", "cat", "v"],
  };

  const str = v => (v == null ? "" : String(v));
  const uniq = a => [...new Set(a)];

  function rng(seed) {
    let h = 1779033703 ^ seed.length;
    for (let i = 0; i < seed.length; i++) { h = Math.imul(h ^ seed.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
    let a = h >>> 0;
    return () => {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function mock(kind, labels, seed) {
    const f = labels && typeof labels === "object" ? {...labels} : {};
    const clean = a => (Array.isArray(a) ? uniq(a.map(str).map(s => s.trim()).filter(Boolean)) : []);
    const list = (a, min) => { const c = clean(a); return c.length >= min ? c : null; };
    const rg = Array.isArray(f.range) && f.range.length === 2 && Number.isFinite(+f.range[0]) && Number.isFinite(+f.range[1]) && +f.range[1] > +f.range[0]
      ? [+f.range[0], +f.range[1]] : [0, 100];
    const timeish = a => a && a.every(x => /^(\d{4}([-\/]\d{2,4})?|(19|20)\d{2}[- ]?q[1-4]|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?( \d{4})?)$/i.test(x));
    let catList = list(f.categories, 2), ser = list(f.series, 2);
    if (timeish(catList) && ser && !timeish(ser)) [catList, ser] = [ser, null];
    if (!catList && ser && !timeish(ser)) catList = ser;
    const cats = (catList || ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]).slice(0, 12);
    const series = (ser || ["Group 1", "Group 2", "Group 3"]).slice(0, 8);
    const r = rng([kind, JSON.stringify([f.title, f.x, f.y, f.unit, cats, ser, rg]), seed == null ? "" : String(seed)].join("|"));
    const span = rg[1] - rg[0], within = (a = 0, b = 1) => rg[0] + (a + r() * (b - a)) * span;
    const tl = list(f.times, 3);
    const years = n => (tl ? tl.slice(0, 12) : d3.range(n).map(i => String(new Date().getFullYear() - n + i)));
    let unit = str(f.unit);
    if (f.number === "percent" && !unit) unit = "%";
    const round = f.number === "integer" ? v => Math.max(0, Math.round(v))
      : f.number === "percent" ? v => Math.round(v * 10) / 10
      : v => (Math.abs(v) >= 100 ? Math.round(v) : Math.abs(v) >= 1 ? Math.round(v * 10) / 10 : Math.round(v * 1000) / 1000);
    let rows = [], geo = null;
    switch (kind) {
      case "bar":
        rows = cats.map(cat => ({cat, v: round(within(0.15, 1))}));
        break;
      case "map": {
        const named = (catList || []).filter(n => QV.countryId && QV.countryId(n));
        const regional = /^[A-Z]{3}$/.test(str(f.country)) && catList && catList.length >= 2 && named.length < catList.length / 2;
        const places = regional ? catList : named.length >= 2 ? named : WORLD;
        if (regional) geo = str(f.country);
        rows = places.slice(0, 60).map(cat => ({cat, v: round(within(0.1, 1))}));
        break;
      }
      case "treemap": case "donut": {
        const parts = kind === "treemap" ? cats : cats.length <= 5 ? cats : ser && ser.length <= 5 ? ser : cats.slice(0, 4);
        rows = parts.map(cat => ({cat, v: round(within(kind === "treemap" ? 0.15 : 0.2, 1))}));
        if (unit === "%") { const t = d3.sum(rows, e => e.v); rows.forEach(e => { e.v = Math.round(e.v / t * 1000) / 10; }); }
        break;
      }
      case "line": {
        const S = list(f.categories, 2) ? cats.slice(0, 8) : ser ? series : [null];
        S.forEach(s => {
          let v = within(0.3, 0.6);
          years(8).forEach(t => {
            v = Math.min(rg[1], Math.max(rg[0], v + (r() - 0.4) * span * 0.12));
            rows.push(s ? {t, series: s, v: round(v)} : {t, v: round(v)});
          });
        });
        break;
      }
      case "stacked_area":
        (list(f.categories, 2) ? cats.slice(0, 8) : series).forEach((s, i, all) => {
          let v = within(0.1, 0.3) / all.length * 2;
          years(8).forEach(t => { v = Math.max(span * 0.02, v * (0.9 + r() * 0.3)); rows.push({t, series: s, v: round(v)}); });
        });
        break;
      case "stacked_bar": case "sankey": {
        const src = kind === "sankey" && list(f.sources, 2), dst = kind === "sankey" && list(f.targets, 2);
        const L = src && dst ? src.slice(0, 6) : kind === "sankey" ? cats.slice(0, 5) : cats;
        const R = src && dst ? dst.slice(0, 6) : series;
        L.forEach(cat => R.forEach(s => { if (kind !== "sankey" || r() > 0.2) rows.push({cat, series: s, v: round(within(0.1, 1))}); }));
        break;
      }
      case "heatmap": {
        const cols = ser && ser.length >= 3 ? series : years(6);
        cats.forEach(cat => {
          const base = r();
          cols.forEach((s, j) => rows.push({cat, series: s, v: round(rg[0] + Math.min(1, Math.max(0, base * 0.6 + r() * 0.4 + j * 0.03)) * span)}));
        });
        break;
      }
      case "scatter":
        d3.range(60).forEach(() => {
          const a = r();
          rows.push({v: round(a * 100), v2: round(rg[0] + (a * 0.7 + r() * 0.3) * span), ...(ser ? {series: series[Math.floor(r() * series.length)]} : {})});
        });
        break;
      case "histogram":
        d3.range(400).forEach(() => rows.push({v: round(rg[0] + (r() + r() + r() + r()) / 4 * span)}));
        break;
      case "bump": {
        const order = d3.shuffle(cats.slice(0, 6), r);
        years(6).forEach(t => {
          for (let k = 0; k < 2; k++) { const i = Math.floor(r() * (order.length - 1)); [order[i], order[i + 1]] = [order[i + 1], order[i]]; }
          order.forEach((cat, i) => rows.push({t, cat, v: i + 1}));
        });
        break;
      }
      case "dot_range": {
        const S = (ser || ["2020", "2025"]).slice(0, 2);
        cats.forEach(cat => {
          const a = within(0.1, 0.75);
          rows.push({cat, series: S[0], v: round(a)}, {cat, series: S[1], v: round(Math.min(rg[1], Math.max(rg[0], a + (r() - 0.25) * span * 0.35)))});
        });
        break;
      }
    }
    const xLabel = kind === "histogram" ? str(f.y || f.x) : str(f.x);
    const yLabel = kind === "histogram" ? "Count" : kind === "bump" ? "Rank" : ["treemap", "donut", "sankey"].includes(kind) ? str(f.y) : str(f.y || "Value");
    return mark({kind, title: str(f.title), xLabel, yLabel, unit: kind === "bump" ? "" : unit, rows, ...(geo ? {geo} : {})});
  }

  function mark(spec) {
    return {...spec, mock: true, source: MOCK_SOURCE, sourceUrl: "", note: spec.note || ""};
  }

  function withMockPatch(patches) {
    return (patches || []).filter(p => p && !p.mock);
  }

  function renderMock(svgEl, spec, opts) {
    const o = {...(opts || {})};
    o.patches = withMockPatch(o.patches);
    return QV.render(svgEl, spec, o);
  }

  const ROLE_NAMES = {cat: "Category", series: "Group", t: "Year", v: "Value", v2: "Second value"};

  function columnNames(spec) {
    const k = spec.kind, x = str(spec.xLabel).trim(), y = str(spec.yLabel).trim();
    const n = {...ROLE_NAMES};
    if (k === "map") n.cat = x || "Country";
    else if (["bar", "treemap", "donut", "stacked_bar", "heatmap", "dot_range", "bump", "sankey"].includes(k) && x) n.cat = x;
    if (k === "sankey") { n.cat = "From"; n.series = "To"; }
    if (["line", "stacked_area", "bump"].includes(k) && x) n.t = x;
    if (k === "heatmap" && spec.rows.every(r => /^\d{4}$/.test(str(r.series)))) n.series = "Year";
    if (k === "dot_range" && spec.rows.every(r => /^\d{4}$/.test(str(r.series)))) n.series = "Year";
    if (k === "scatter") { n.v = x || "X value"; n.v2 = y || "Y value"; }
    else if (k === "bump") n.v = "Rank";
    else if (y && y !== "Count") n.v = y;
    if (spec.unit && !/[(]/.test(n.v) && k !== "bump") n.v = `${n.v} (${spec.unit})`;
    const seen = new Set();
    Object.keys(n).forEach(r => { let s = n[r], i = 2; while (seen.has(s.toLowerCase())) s = `${n[r]} ${i++}`; seen.add(s.toLowerCase()); n[r] = s; });
    return n;
  }

  function toTable(spec, extra) {
    const ex = extra || {};
    const rows = (spec && spec.rows) || [];
    const roles = (NEED[spec.kind] || []).filter(r => rows.some(e => e[r] != null && e[r] !== ""));
    const names = columnNames(spec);
    const isNum = r => r === "v" || r === "v2";
    const isTime = r => r === "t" || (r === "series" && rows.every(e => /^\d{4}$/.test(str(e.series))));
    const cols = roles.map(r => {
      const vals = rows.map(e => e[r]).filter(v => v != null && v !== "");
      const info = {name: names[r], type: isNum(r) ? "number" : isTime(r) ? "time" : "category", distinct: new Set(vals.map(String)).size,
        samples: uniq(vals.map(String)).slice(0, 3)};
      if (isNum(r) && vals.length) { info.min = d3.min(vals); info.max = d3.max(vals); }
      if (r === "v" && spec.unit) info.unit = spec.unit;
      return info;
    });
    const mockData = spec.mock !== false;
    const sources = Array.isArray(ex.sources) ? ex.sources.filter(s => s && /^https?:\/\//.test(str(s.url))) : [];
    const hint = mockData ? MOCK_SOURCE : sources.length ? sources.map(s => str(s.title)).join(", ").slice(0, 160) : "";
    const notes = !mockData && sources.length ? ["Found by web search. Check the numbers against the sources."] : [];
    return {
      name: mockData ? "Mockup data" : "Web data",
      columns: cols,
      rows: rows.map(e => roles.map(r => (e[r] == null ? null : e[r]))),
      n_rows: rows.length, truncated: false, melted: 0,
      source_hint: hint, source_url: !mockData && sources[0] ? sources[0].url : "",
      notes, aggregates: [], sheet: null,
      reading: {summary: mockData ? "Mockup data made from your description" : "Numbers found by web search", confidence: 1, recipe: null, alternatives: [], issues: []},
      mock: mockData, sources,
      described: {kind: spec.kind, title: str(spec.title), unit: str(spec.unit), roles: Object.fromEntries(roles.map(r => [r, names[r]])), geo: spec.geo || null},
    };
  }

  function sourced(spec, sources) {
    const ok = (sources || []).filter(x => x && /^https?:\/\//.test(str(x.url)));
    return {...spec, mock: false, source: ok.map(x => str(x.title)).join(", ").slice(0, 160) || "Web search", sourceUrl: ok[0] ? ok[0].url : "",
      note: spec.note || "Found by web search. Check the numbers against the sources."};
  }

  function sameThought(a = "", b = "") {
    a = a.toLowerCase(); b = b.toLowerCase();
    return !!a && !!b && (a.startsWith(b) || b.startsWith(a));
  }

  function typing(cfg) {
    const c = {
      paths: {pick: "/api/pick", fill: "/api/fill", web: "/api/web-data"},
      minChars: 4, wait: 200, webWait: 700, minP: 0.05, chartable: 0.5, webScore: 0.7, fillMs: 6000,
      ...cfg,
    };
    c.paths = {...{pick: "/api/pick", fill: "/api/fill", web: "/api/web-data"}, ...(cfg.paths || {})};
    let seq = 0, timer = null, ctrl = null, lastPick = null;
    const s = {text: "", kind: null, ranked: [], opts: [], idx: 0, fill: null, fillText: "", web: false, webEligible: false, webSpecs: null, sources: [], spec: null, phase: "idle", error: ""};

    const emit = patch => { Object.assign(s, patch); if (c.onState) c.onState(snapshot()); };
    const snapshot = () => ({phase: s.phase, error: s.error, text: s.text, kind: s.kind, ranked: s.ranked.slice(), opts: s.opts.slice(), idx: s.idx,
      web: s.web, webEligible: s.webEligible, sources: s.sources.slice(), spec: s.spec, mock: s.spec ? s.spec.mock !== false : null});
    const abort = () => { seq++; if (ctrl) ctrl.abort(); ctrl = new AbortController(); return seq; };

    function show(spec) { s.spec = spec; if (c.draw) c.draw(spec); }

    function drawMock() {
      if (!s.kind) return;
      const f = s.fill && sameThought(s.text, s.fillText) ? s.fill : {};
      show(mock(s.kind, f, s.kind + "|" + (f.title || s.text)));
    }

    function buildOpts() {
      const ranked = s.ranked.length ? s.ranked.filter(([k, p]) => p >= c.minP || k === s.kind).map(r => r[0]) : [s.kind];
      s.opts = ranked.filter(k => NEED[k]);
      s.idx = Math.max(0, s.opts.indexOf(s.kind));
    }

    function empty() {
      abort();
      Object.assign(s, {kind: null, spec: null, opts: [], ranked: [], webSpecs: null, webEligible: false, web: false, sources: []});
      if (c.clear) c.clear();
      emit({phase: "empty", error: ""});
    }

    async function fillLabels(my, signal) {
      emit({phase: "refining"});
      try {
        const f = await Promise.race([c.post(c.paths.fill, {text: s.text, kind: s.kind}, signal),
          new Promise((_, no) => setTimeout(() => no(new Error("slow")), c.fillMs))]);
        if (my !== seq) return;
        s.fill = f; s.fillText = s.text;
        drawMock();
        emit({phase: "idle"});
      } catch (e) {
        if (my !== seq || e.name === "AbortError") return;
        emit({phase: "idle", error: /Too many/.test(e.message) ? e.message : e.message === "slow" ? "" : "Labels failed, showing generic ones"});
      }
    }

    async function run() {
      const text = s.text;
      if (text.length < c.minChars) return;
      let useWeb = s.web;
      const my = abort(), signal = ctrl.signal;
      s.webSpecs = null; s.sources = [];
      if (useWeb) { s.spec = null; if (c.clear) c.clear(); }
      emit({phase: useWeb ? "web" : "picking", error: ""});
      try {
        const p = lastPick && lastPick.text === text ? lastPick.result : await c.post(c.paths.pick, {text}, signal);
        if (my !== seq) return;
        lastPick = {text, result: p};
        s.webEligible = Number(p.web_data) >= c.webScore;
        if (!s.webEligible) useWeb = s.web = false;
        if (p.chartable != null && p.chartable < c.chartable) return empty();
        s.ranked = p.ranked || [];
        s.kind = p.choice;
        if (useWeb) {
          s.opts = [s.kind]; s.idx = 0;
          emit({phase: "web"});
          const found = await c.post(c.paths.web, {text, kind: s.kind}, signal);
          if (my !== seq) return;
          const all = {[found.spec.kind]: found.spec, ...(found.alternatives || {})};
          s.webSpecs = Object.fromEntries(Object.entries(all).map(([k, v]) => [k, sourced(v, found.sources)]));
          s.opts = Object.keys(s.webSpecs); s.idx = 0;
          s.sources = found.sources || [];
          show(s.webSpecs[found.spec.kind]);
          emit({phase: "idle"});
          return;
        }
        buildOpts();
        drawMock();
        emit({phase: "idle"});
        await fillLabels(my, signal);
      } catch (e) {
        if (e.name !== "AbortError" && my === seq) emit({phase: "error", error: e.message});
      }
    }

    function input(text) {
      clearTimeout(timer);
      const t = str(text).trim();
      if (t !== s.text) {
        lastPick = null;
        abort();
        s.webEligible = false;
        s.text = t;
      }
      if (s.text.length < c.minChars) return empty();
      timer = setTimeout(run, s.web ? c.webWait : c.wait);
    }

    function setWeb(on) {
      s.web = !!on && s.webEligible;
      s.fill = null;
      clearTimeout(timer);
      if (s.text.length >= c.minChars) run(); else empty();
      return s.web;
    }

    function switchKind(kind) {
      if (!NEED[kind]) return;
      const my = abort();
      s.kind = kind;
      s.idx = Math.max(0, s.opts.indexOf(kind));
      if (s.webSpecs && s.webSpecs[kind]) { show(s.webSpecs[kind]); emit({phase: "idle"}); return; }
      drawMock();
      emit({phase: "idle"});
      if (!s.fill || !sameThought(s.text, s.fillText)) fillLabels(my, ctrl.signal);
    }

    function step(delta) {
      const n = s.opts.length;
      if (n < 2) return;
      switchKind(s.opts[(s.idx + delta + n) % n]);
    }

    function table() {
      if (!s.spec) return null;
      return toTable(s.spec, {sources: s.spec.mock === false ? s.sources : []});
    }

    return {input, setWeb, step, switchKind, table, state: snapshot, stop: () => { clearTimeout(timer); abort(); }};
  }

  Object.assign(QV, {
    mock, markMock: mark, markSourced: sourced, mockTable: toTable, mockTyping: typing, renderMock, withMockPatch,
    MOCK_SOURCE, mockKinds: Object.keys(NEED),
  });
})();
