(function () {
  const THEMES = window.QV_THEMES || {ceps: window.CEPS};
  const themeOf = style => THEMES[style] || THEMES.ceps || window.CEPS || Object.values(THEMES)[0];
  let T = themeOf("ceps");
  let FONT = T.font;
  const FS = {min: T.fs.min, tick: T.fs.tick, label: T.fs.label, title: T.fs.title, axis: T.fs.title, big: 22};
  const pxSize = n => { n = Math.max(9, Math.min(24, Math.round(n))); return {tick: n, label: n + 1, min: Math.max(9, Math.min(T.fs.min, n - 2)), axis: Math.min(T.fs.title + 4, n + 3)}; };
  let SHADES = T.shades;
  const SYM = {square: "symbolSquare", diamond: "symbolDiamond", triangle: "symbolTriangle"};
  let NF = d3, NUMSTYLE = "auto", LMAX = null, USE = null;
  const NUM_FIELDS = ["decimals", "thousands", "decimalMark", "numberStyle"];
  const mark = (...keys) => { if (USE) keys.forEach(k => USE.add(k)); };
  const track = (spec, used) => new Proxy(spec, {get(t, k, r) { if (typeof k === "string") used.add(k); return Reflect.get(t, k, r); }});
  const SIZES = {small: {tick: T.fs.min, label: T.fs.tick}, normal: {tick: T.fs.tick, label: T.fs.label}, large: {tick: T.fs.label, label: T.fs.title}};
  let WHITE = T.paper;
  let INK, MUTED, FAINT, RULE, GRID, DASH, PAPER, NODATA, CONTEXT, WATER, GREEN, NAVY, RED, GREY, FOCUS, CAT, HL, DIV, HEAT, SEQ, MID, DIVLO, DIVHI;
  const NAMED = {};
  function tone(el, style) {
    T = themeOf(style);
    FONT = T.font; SHADES = T.shades; WHITE = T.paper;
    const cs = el && el.isConnected ? getComputedStyle(el) : null;
    const v = (n, d) => (cs && cs.getPropertyValue("--qv-" + n).trim()) || d;
    INK = v("ink", T.ink); MUTED = v("muted", T.grey); FAINT = v("faint", T.grey2); RULE = v("rule", T.grey3); GRID = v("grid", T.rule);
    DASH = T.gridDash;
    PAPER = v("paper", T.paper); NODATA = v("nodata", T.greyTint); CONTEXT = v("context", T.noData); WATER = T.water;
    GREEN = v("green", T.primary); NAVY = v("navy", T.euColor); RED = v("red", T.red); GREY = v("grey", T.grey); FOCUS = v("focus", T.focusColor);
    Object.keys(NAMED).forEach(k => delete NAMED[k]);
    Object.assign(NAMED, T.named);
    CAT = T.cat.slice();
    HL = T.hl.slice();
    const list = (n, d) => { const x = v(n, ""); return x ? x.split(",").map(c => c.trim()) : d; };
    DIV = list("div", T.div);
    HEAT = list("heat", T.heat);
    SEQ = list("seq", T.seq);
    MID = v("mid", T.mid);
    DIVLO = T.divLo; DIVHI = T.divHi;
  }
  tone(null);
  let PAD = 16;
  const BASE_H = 520;
  const NARROW_H = 480;
  const FIT_MIN = 300;
  const ROW_MIN = 18;
  const ROW_FLOOR = 14;
  const SPACE_MAX = 900;
  const OTHER = "Other";
  const FADE_MS = 260;
  const PATCH_MS = 1000;
  const CANVAS_SIDE = 16384;
  const CANVAS_AREA = 16777216;
  const FRAME_CSP = "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'";
  let H = BASE_H;
  let DEC = null;
  let AUTO_DEC = null;
  let WHOLE = false;

  const BASE = window.QV_BASE || (document.currentScript && document.currentScript.src
    ? new URL(".", document.currentScript.src).href : location.href);
  const getJSON = url => (window.QV_GET_JSON ? Promise.resolve(window.QV_GET_JSON(url)) : fetch(url).then(r => (r.ok ? r.json() : null)));

  let measureCtx = null;
  function tw(s, size = FS.tick, weight = 400, font = FONT) {
    measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
    measureCtx.font = `${weight} ${size}px ${font}`;
    return measureCtx.measureText(String(s)).width;
  }
  function clip(s, max, size = FS.tick, weight = 400) {
    s = String(s);
    if (tw(s, size, weight) <= max) return s;
    let lo = 0, hi = s.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (tw(s.slice(0, mid) + "…", size, weight) <= max) lo = mid; else hi = mid - 1;
    }
    return lo ? s.slice(0, lo).trimEnd() + "…" : "…";
  }
  function wrap(s, max, size, weight = 400, lines = 2) {
    const words = String(s).split(/\s+/).filter(Boolean), out = [];
    let cur = "";
    for (const w of words) {
      const next = cur ? cur + " " + w : w;
      if (tw(next, size, weight) <= max || !cur) cur = next;
      else { out.push(cur); cur = w; }
    }
    if (cur) out.push(cur);
    if (out.length > lines) { const rest = out.slice(lines - 1).join(" "); out.length = lines - 1; out.push(clip(rest, max, size, weight)); }
    return out.map(l => clip(l, max, size, weight));
  }
  let FST = null;
  const FACES = ["bold", "italic", "bold italic", "normal"];
  const faceOf = part => (FST && FACES.includes(FST[part]) ? FST[part] : null);
  const fw = (part, def = 400, emph = false) => { const v = faceOf(part); return emph ? 700 : v ? (v.startsWith("bold") ? 700 : 400) : def; };
  const fi = part => ((faceOf(part) || "").endsWith("italic") ? "italic" : null);
  const fm = (part, def = 400, emph = false) => (fi(part) ? "italic " : "") + fw(part, def, emph);
  function face(sel, part, def = 400, emph = false) {
    return sel.attr("font-weight", typeof emph === "function" ? (...a) => fw(part, def, emph(...a)) : fw(part, def, emph)).attr("font-style", fi(part));
  }

  function num(v) {
    if (v == null || v === "") return NaN;
    if (typeof v === "number") return v;
    const n = Number(String(v).replace(/[,\s$€£%]/g, ""));
    return Number.isFinite(n) ? n : NaN;
  }
  const str = v => (v == null ? "" : String(v));
  const uniq = arr => [...new Set(arr)];

  function unitParts(u) {
    u = str(u).trim();
    if (!u) return ["", ""];
    if (/^[$€£¥₹]$/.test(u) || /^[A-Z]{0,2}\$$/.test(u)) return [u, ""];
    if (u === "%" || u === "pp" || u === "p.p.") return ["", u === "%" ? "%" : " " + u];
    return ["", " " + u];
  }
  function withUnit(s, unit) {
    const [p, suf] = unitParts(unit);
    let neg = "";
    s = s.replace(/^[-−]/, () => ((neg = "−"), ""));
    return neg + p + s + suf;
  }
  function short(v) {
    mark(...NUM_FIELDS);
    if (NUMSTYLE === "full") return full(v);
    const a = Math.abs(v);
    const f = DEC != null ? NF.format(`.${DEC}f`) : NF.format(".3~r");
    if (a >= 1e12) return f(v / 1e12) + "T";
    if (a >= 1e9) return f(v / 1e9) + "B";
    if (a >= 1e6) return f(v / 1e6) + "M";
    if (NUMSTYLE === "short" && a >= 1e3) return f(v / 1e3) + "k";
    if (DEC != null) return NF.format(`,.${DEC}f`)(v);
    if (AUTO_DEC != null && a < 1e5) return NF.format(`,.${AUTO_DEC}f`)(v);
    if (a >= 1e4) return f(v / 1e3) + "k";
    if (a >= 1) return NF.format(",.4~r")(v);
    if (a === 0) return "0";
    return NF.format(".2~r")(v);
  }
  function full(v) {
    mark(...NUM_FIELDS);
    const a = Math.abs(v);
    if (a >= 1e6 && NUMSTYLE !== "full") return short(v);
    if (DEC != null) return NF.format(`,.${DEC}f`)(v);
    if (a >= 100) return NF.format(",.0f")(v);
    if (a >= 1) return NF.format(",.2~f")(v);
    return NF.format(".3~r")(v);
  }
  function tickShort(v) {
    const keep = DEC, keepA = AUTO_DEC; DEC = null; AUTO_DEC = null;
    const s = short(v);
    DEC = keep; AUTO_DEC = keepA;
    return s;
  }
  const symbolUnit = u => /^([$€£¥₹%]|[A-Z]{0,2}\$)$/.test(str(u).trim());
  const fmtShort = (v, unit) => withUnit(short(v), symbolUnit(unit) ? unit : "");
  const fmtFull = (v, unit) => withUnit(full(v), unit);
  const fmtTick = (v, unit) => withUnit(tickShort(v), symbolUnit(unit) ? unit : "");

  const EU_RE = /^(eu|eu ?2[78]|eu-2[78]|eu2[78]_20\d\d|eu ?27 ?\(?(from )?2020\)?|european union.*|eu average|eu total|euro ?area.*|ea ?\d*|eurozone|eu countries)$/i;
  const isEU = n => EU_RE.test(String(n).trim());

  function hexLum(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return 0.5;
    const n = parseInt(m[1], 16), c = [n >> 16 & 255, n >> 8 & 255, n & 255].map(x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  const paint = c => { const k = typeof c === "string" ? c.trim().toLowerCase() : ""; return Object.hasOwn(NAMED, k) ? NAMED[k] : (/^#([0-9a-f]{3}|[0-9a-f]{6})$/.test(k) ? k : null); };
  const textOn = fill => (hexLum(d3.color(fill) ? d3.color(fill).formatHex() : fill) > 0.32 ? T.ink : WHITE);

  function palette(C, names, opts = {}) {
    const spec = C.spec, over = spec.colors || {}, hl = new Set((spec.highlight || []).map(String));
    const hasEU = names.some(isEU);
    const pool = hasEU ? CAT.filter(c => c !== NAVY) : CAT.slice();
    const map = new Map();
    let i = 0, j = 0;
    (C.colorOrder ? uniq([...C.colorOrder, ...names]) : names).forEach(n => {
      if (map.has(n)) return;
      const o = over[n];
      if (paint(o)) { map.set(n, paint(o)); return; }
      if (n === OTHER) { map.set(n, opts.other || FAINT); return; }
      if (isEU(n) && !hl.has(n)) { map.set(n, NAVY); return; }
      if (hl.size) { map.set(n, hl.has(n) ? (opts.hlSame ? FOCUS : HL[j++ % HL.length]) : (opts.rest || GREY)); return; }
      map.set(n, opts.single || pool[i++ % pool.length]);
    });
    const fn = n => map.get(n) || FAINT;
    fn.hl = hl;
    return fn;
  }
  const TIME_CAT = /^(\d{4}([-/.]\d{1,2}){0,2}|\d{4}\s?(Q[1-4]|H[12]|M\d{1,2})|(Q[1-4]|H[12])\s?\d{4})$/i;
  const isHl = (C, n) => (C.spec.highlight || []).map(String).includes(String(n));

  function countryShareOf(names) { return names.length ? names.filter(n => countryId(n) || isEU(n)).length / names.length : 0; }

  const LOGO_POS = ["bottom-right", "bottom-left", "top-right", "top-left"];
  function logoBox(spec, W) {
    const L = T.logo, o = spec.logo && typeof spec.logo === "object" ? spec.logo : {};
    if (!L || o.show === false) return null;
    const pos = LOGO_POS.includes(o.pos) ? o.pos : "bottom-right";
    const h = Math.round(Math.max(20.7, Math.min(29.9, W * 0.0368)));
    return {pos, h, w: Math.round(h * L.w / L.h), top: pos.startsWith("top"), right: pos.endsWith("right"), gap: 12, y: null};
  }
  function drawLogo(C) {
    const lg = C.logo, L = T.logo;
    if (!lg || lg.y == null || !L) return;
    const a = C.root.append("a").attr("class", "qv-logo").attr("href", L.href).attr("target", "_blank").attr("rel", "noopener");
    const g = a.append("svg").attr("x", lg.right ? C.W - PAD - lg.w : PAD).attr("y", lg.y).attr("width", lg.w).attr("height", lg.h)
      .attr("viewBox", `0 0 ${L.w} ${L.h}`).attr("role", "img").attr("aria-label", L.label);
    L.paths.forEach(p => g.append("path").attr("d", p.d).attr("fill", L.fill).attr("fill-rule", p.evenodd ? "evenodd" : null));
  }

  function header(C) {
    const {root, spec, W} = C;
    const lg = C.logo && C.logo.top ? C.logo : null, room = lg ? lg.w + lg.gap : 0;
    if (lg) lg.y = PAD;
    const below = lg ? PAD + lg.h + 8 : PAD;
    if (!spec.title) return below;
    mark("titleSize");
    const center = spec.titleAlign === "center";
    const lines = wrap(spec.title, W - 2 * PAD - (center ? 2 : 1) * room, FS.title, fm("title", 700), 2);
    const al = center ? ["middle", W / 2] : spec.titleAlign === "right" ? ["end", W - PAD - (lg && lg.right ? room : 0)] : ["start", PAD + (lg && !lg.right ? room : 0)];
    const t = root.append("text").attr("class", "qv-title").attr("x", al[1]).attr("y", PAD + FS.title * 0.85).attr("text-anchor", al[0])
      .attr("font-family", FONT).attr("font-size", FS.title).call(face, "title", 700).attr("fill", INK);
    lines.forEach((l, i) => t.append("tspan").attr("x", al[1]).attr("dy", i ? FS.title * 1.25 : 0).text(l));
    return Math.max(below, PAD + lines.length * FS.title * 1.25 + 8);
  }

  const legPos = (C, def = "bottom") => (C.spec.legendPos && C.spec.legendPos !== "auto" ? C.spec.legendPos : def);
  const legDir = (C, pos) => (C.spec.legendDir && C.spec.legendDir !== "auto" ? C.spec.legendDir : pos === "left" || pos === "right" ? "vertical" : "horizontal");
  const isSide = pos => pos === "left" || pos === "right";
  function keyPlace(C, def = "bottom") {
    const pos = legPos(C, def);
    if (isSide(pos) && C.W < 560) return {pos: "bottom", dir: "horizontal"};
    return {pos, dir: legDir(C, pos)};
  }

  function sortLegend(C, items, values) {
    const s = C.spec.legendSort;
    if (!s || s === "auto") return items;
    const out = items.slice();
    const name = it => String(it.label || it.name);
    if (s === "az" || s === "za") out.sort((a, b) => name(a).localeCompare(name(b), undefined, {numeric: true}));
    if (s === "za" || s === "reverse") out.reverse();
    if (s === "value" && values) out.sort((a, b) => (values.get(b.name) ?? -Infinity) - (values.get(a.name) ?? -Infinity));
    return out;
  }

  function legend(C, names, color, extra, values) {
    let items = (names || []).map(n => ({name: String(n), color: color(n), series: true})).concat(extra || []);
    if (C.toggle && names && names.length) {
      const shown = new Set(names.map(String));
      const all = uniq([...(C.colorOrder || []).filter(n => shown.has(n) || C.offSeries.has(n)), ...shown]);
      items = all.map(n => ({name: n, color: color(n), series: true, off: C.offSeries.has(n)})).concat(extra || []);
    }
    if (!items.length) { C.leg = null; return C.top; }
    const mode = C.spec.legend;
    if (mode === "off" || (items.length < (mode === "on" ? 1 : 2) && !C.spec.legendTitle)) { C.leg = null; return C.top; }
    items = sortLegend(C, items, values);
    const {pos, dir} = keyPlace(C), side = isSide(pos);
    const maxW = side ? Math.min(240, C.W * 0.3) : C.W - 2 * PAD, rowH = 24;
    const titleRow = side || dir === "vertical";
    const tf = fm("legend", 700), lf = fm("legend");
    const title = C.spec.legendTitle ? clip(C.spec.legendTitle, titleRow ? maxW : maxW * 0.5, FS.tick, tf) : "";
    const rows = [[]];
    let x = title && !titleRow ? tw(title, FS.tick, tf) + 14 : 0;
    const fr = flagRoom(true, FS.tick);
    items.forEach(it => {
      const flag = C.legFlags ? flagKey(it.name) : null;
      const label = clip(it.label || it.name, (side ? maxW - 20 : 220) - (flag ? fr : 0), FS.tick, lf), w = 14 + 6 + (flag ? fr : 0) + tw(label, FS.tick, lf) + 18;
      if ((dir === "vertical" || x + w > maxW) && rows.at(-1).length) { rows.push([]); x = 0; }
      rows.at(-1).push({...it, label, w, flag});
      x += w;
    });
    const rowW = (row, ri) => d3.sum(row, it => it.w) - 18 + (ri === 0 && title && !titleRow ? tw(title, FS.tick, tf) + 14 : 0);
    const w = Math.max(title && titleRow ? tw(title, FS.tick, tf) : 0, d3.max(rows, rowW) || 0);
    C.leg = {title, rows, titleRow, pos, dir, w, h: (rows.length + (title && titleRow ? 1 : 0)) * rowH, rowW};
    if (pos === "top") { C.leg.y = C.top; C.top += C.leg.h + 8; }
    return C.top;
  }

  function drawLegend(C, x0, y0, centered) {
    const L = C.leg, g = C.root.append("g").attr("class", "qv-legend");
    let y = y0;
    if (L.title && L.titleRow) {
      g.append("text").attr("x", centered ? Math.max(PAD, (C.W - L.w) / 2) : x0).attr("y", y + 12).attr("dy", "0.35em").attr("font-size", FS.tick)
        .call(face, "legend", 700).attr("fill", INK).attr("font-family", FONT).text(L.title);
      y += 24;
    }
    const blockX = centered && L.dir === "vertical" ? Math.max(PAD, (C.W - L.w) / 2) : x0;
    L.rows.forEach((row, ri) => {
      let x = centered && L.dir !== "vertical" ? Math.max(PAD, (C.W - L.rowW(row, ri)) / 2) : blockX;
      const cy = y + ri * 24 + 12;
      if (ri === 0 && L.title && !L.titleRow) {
        g.append("text").attr("x", x).attr("y", cy).attr("dy", "0.35em").attr("font-size", FS.tick).call(face, "legend", 700)
          .attr("fill", INK).attr("font-family", FONT).text(L.title);
        x += tw(L.title, FS.tick, fm("legend", 700)) + 14;
      }
      row.forEach(it => {
        const gi = g.append("g").attr("transform", `translate(${x},${cy})`);
        gi.append("title").text(it.name);
        if (C.toggle && it.series) {
          const flip = () => C.toggleFn(it.name);
          gi.attr("class", "qv-toggle").attr("data-name", it.name).attr("tabindex", 0).attr("role", "button").attr("aria-pressed", String(!it.off))
            .attr("aria-label", `${it.off ? "Show" : "Hide"} ${it.name}`).on("click", flip)
            .on("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); } });
          gi.append("rect").attr("x", -3).attr("y", -11).attr("width", it.w - 12).attr("height", 22).attr("fill", "transparent");
          if (it.off) gi.attr("opacity", 0.45);
        }
        gi.append("rect").attr("y", -7).attr("width", 14).attr("height", 14).attr("fill", it.off ? WHITE : it.color).attr("stroke", it.off ? it.color : null).attr("stroke-width", it.off ? 1.5 : null);
        if (it.flag) flagAt(C, gi, it.flag, 20, 0, FS.tick);
        gi.append("text").attr("x", 20 + (it.flag ? flagRoom(true, FS.tick) : 0)).attr("dy", "0.35em").attr("font-size", FS.tick).call(face, "legend").attr("fill", INK)
          .attr("font-family", FONT).text(it.label);
        x += it.w;
      });
    });
  }

  function keyMeasure(C, o) {
    if (C.spec.legend === "off") return null;
    const {pos} = keyPlace(C), side = isSide(pos);
    let {dir} = keyPlace(C);
    const title = o.title || "", n = o.labels.length;
    const lf = fm("legend"), tf = fm("legend", 700);
    const lw = d3.max(o.labels, l => tw(l, FS.tick, lf)) || 0;
    if (dir === "horizontal" && o.type !== "grad") {
      const avail = side ? Math.min(260, C.W * 0.34) : C.W - 2 * PAD, cell = Math.min(110, Math.max(Math.min(64, avail / n), lw + 14), avail / n);
      const ew = o.edges && o.edges.length === n - 1 ? d3.max(o.edges, l => tw(l, FS.tick, lf)) || 0 : Infinity;
      if (lw + 8 > cell) { if (ew + 8 <= Math.min(64, avail / n)) o = {...o, edgeLabels: true}; else dir = "vertical"; }
    }
    const K = {...o, pos, dir, side};
    if (dir === "vertical") {
      K.len = o.type === "grad" ? Math.round(Math.max(110, Math.min(220, H * 0.4))) : n * 22;
      K.titleTxt = title ? clip(title, side ? Math.min(220, C.W * 0.3) : C.W - 2 * PAD, FS.tick, tf) : "";
      K.w = Math.max(K.titleTxt ? tw(K.titleTxt, FS.tick, tf) : 0, 14 + 8 + lw);
      K.h = (K.titleTxt ? 26 : 0) + K.len + 8;
    } else {
      const avail = side ? Math.min(260, C.W * 0.34) : C.W - 2 * PAD;
      if (o.type === "grad") K.len = Math.min(240, avail);
      else { K.cell = K.edgeLabels ? Math.min(64, avail / n) : Math.min(110, Math.max(Math.min(64, avail / n), lw + 14), avail / n); K.len = K.cell * n; }
      const tW = title ? tw(title, FS.tick, tf) + 16 : 0;
      K.stack = !!title && (side || tW + K.len > avail);
      K.titleW = title && !K.stack ? tW : 0;
      K.titleTxt = title ? clip(title, K.stack ? avail : tW, FS.tick, tf) : "";
      K.w = K.stack ? Math.max(K.len, tw(K.titleTxt, FS.tick, tf)) : K.titleW + K.len;
      K.h = (K.stack ? 22 : 0) + 42;
    }
    return K;
  }
  function keyMargins(K) {
    if (!K) return {top: 0, right: 0, bottom: 0, left: 0};
    return {top: K.pos === "top" ? K.h + 8 : 0, bottom: K.pos === "bottom" ? K.h + 10 : 0,
      right: K.pos === "right" ? K.w + 24 : 0, left: K.pos === "left" ? K.w + 24 : 0};
  }
  function drawKey(C, K, b, topY) {
    if (!K) return;
    let x, y;
    if (K.pos === "right") { x = b.grid ? b.left + b.iw + 24 : C.W - PAD - K.w; y = b.top + Math.max(0, (b.ih - K.h) / 2); }
    else if (K.pos === "left") { x = b.grid ? b.left - b.lw - 10 - 24 - K.w : PAD; y = b.top + Math.max(0, (b.ih - K.h) / 2); }
    else { x = b.grid ? Math.max(PAD, Math.min(C.W - PAD - K.w, b.left + (b.iw - K.w) / 2)) : Math.max(PAD, (C.W - K.w) / 2); y = K.pos === "top" ? topY : C.plotBottom - K.h; }
    const g = C.root.append("g").attr("class", "qv-key").attr("transform", `translate(${x},${y})`);
    const txt = (tx, ty, str0, o = {}) => g.append("text").attr("x", tx).attr("y", ty).attr("font-size", FS.tick).call(face, "legend", o.bold ? 700 : 400)
      .attr("fill", INK).attr("font-family", FONT).attr("text-anchor", o.anchor || "start").attr("dy", o.dy || null).text(str0);
    const gradient = vertical => {
      const gid = "qvgrad" + Math.random().toString(36).slice(2, 8);
      const grad = C.root.append("defs").append("linearGradient").attr("id", gid);
      if (vertical) grad.attr("x1", 0).attr("y1", 1).attr("x2", 0).attr("y2", 0);
      K.stops.forEach(([t, c]) => grad.append("stop").attr("offset", t).attr("stop-color", c));
      return `url(#${gid})`;
    };
    if (K.dir === "vertical") {
      let ty = 0;
      if (K.titleTxt) { txt(0, 12, K.titleTxt, {bold: true}); ty = 26; }
      if (K.type === "grad") {
        g.append("rect").attr("y", ty).attr("width", 14).attr("height", K.len).attr("fill", gradient(true)).attr("stroke", RULE).attr("stroke-width", 0.5);
        K.ticks.forEach(([t, lab]) => txt(22, ty + K.len * (1 - t), lab, {dy: t === 1 ? "0.75em" : t === 0 ? "-0.05em" : "0.35em"}));
      } else {
        K.colors.map((c, i) => i).reverse().forEach((i, r) => {
          g.append("rect").attr("y", ty + r * 22 + 3).attr("width", 14).attr("height", 14).attr("fill", K.colors[i]);
          txt(22, ty + r * 22 + 10, K.labels[i], {dy: "0.35em"});
        });
      }
    } else {
      const by = K.stack ? 22 : 0, bx = K.titleW || 0;
      if (K.titleTxt) txt(0, 12, K.titleTxt, {bold: true, dy: "0.1em"});
      if (K.type === "grad") {
        g.append("rect").attr("x", bx).attr("y", by).attr("width", K.len).attr("height", 14).attr("fill", gradient(false)).attr("stroke", RULE).attr("stroke-width", 0.5);
        K.ticks.forEach(([t, lab]) => txt(bx + t * K.len, by + 33, lab, {anchor: t === 0 ? "start" : t === 1 ? "end" : "middle"}));
      } else {
        K.colors.forEach((c, i) => {
          g.append("rect").attr("x", bx + i * K.cell).attr("y", by).attr("width", K.cell - 2).attr("height", 14).attr("fill", c);
          if (K.edgeLabels) { if (i) txt(bx + i * K.cell - 1, by + 34, K.edges[i - 1], {anchor: "middle"}); }
          else txt(bx + i * K.cell + (K.cell - 2) / 2, by + 34, K.labels[i], {anchor: "middle"});
        });
      }
    }
  }

  function noteLines(C) {
    if (C._noteLines) return C._noteLines;
    const text = C.spec.note || "";
    C._noteLines = text ? wrap(text, C.W - 2 * PAD, FS.min, fm("note"), 3) : [];
    return C._noteLines;
  }
  const srcRow = C => Math.max(C.spec.source ? 24 : 0, C.logo && !C.logo.top ? C.logo.h + 8 : 0);
  function footH(C) {
    let h = 0;
    if (C.leg && C.leg.pos === "bottom") h += C.leg.h + 8;
    const nl = noteLines(C).length;
    if (nl) h += nl * 17 + 4;
    h += C.ctlH || 0;
    const row = srcRow(C);
    if (row) h += row;
    return h ? h + 6 : 0;
  }

  function drawFoot(C) {
    const {root, W, spec} = C;
    C._noteLines = null;
    const total = footH(C);
    let y = H - total + 6;
    if (C.leg) {
      if (C.leg.pos === "top") drawLegend(C, PAD, C.leg.y, true);
      else if (isSide(C.leg.pos) && C.pb) {
        const x = C.leg.pos === "right" ? C.W - PAD - C.leg.w : PAD;
        drawLegend(C, x, C.pb.top + Math.max(0, (C.pb.ih - C.leg.h) / 2), false);
      } else if (C.leg.pos === "bottom") { drawLegend(C, PAD, y, true); y += C.leg.h + 8; }
    }
    const nl = noteLines(C);
    nl.forEach((l, i) => root.append("text").attr("class", "qv-note").attr("x", PAD).attr("y", y + i * 17 + 12).attr("font-size", FS.min)
      .call(face, "note").attr("fill", MUTED).attr("font-family", FONT).text(l));
    if (nl.length) y += nl.length * 17 + 4;
    C.ctlY = y;
    y += C.ctlH || 0;
    const row = srcRow(C), lg = C.logo && !C.logo.top ? C.logo : null, room = lg ? lg.w + lg.gap : 0;
    if (lg) lg.y = Math.round(y + (row - lg.h) / 2 - 2);
    if (spec.source) {
      const t = root.append("text").attr("class", "qv-source").attr("x", PAD + (lg && !lg.right ? room : 0)).attr("y", y + 15 + (row - 24) / 2).attr("font-size", FS.tick)
        .call(face, "source").attr("fill", INK).attr("font-family", FONT);
      t.append("tspan").text("Source: ");
      const sf = fm("source"), name = clip(spec.source, W - 2 * PAD - room - tw("Source: ", FS.tick, sf), FS.tick, sf);
      if (spec.sourceUrl && /^https?:\/\//.test(spec.sourceUrl)) {
        const a = root.append("a").attr("href", spec.sourceUrl).attr("target", "_blank").attr("rel", "noopener");
        a.node().appendChild(t.node());
        t.append("tspan").attr("fill", GREEN).attr("text-decoration", "underline").text(name);
      } else t.append("tspan").text(name);
    }
  }

  function tileShare(n) {
    if (!isFinite(n)) return "N/A";
    const len = n.toString().split(".")[0].replace("-", "").length;
    const v = n === 0 ? "0" : len >= 3 ? (Math.abs(n) < 1000 ? d3.format(".3r")(n) : d3.format(".3~s")(n)) : n < 1 && n > -1 ? d3.format(".2g")(n) : d3.format(".3g")(n);
    return v.replace(/\u2212/g, "-").replace(/(\.[0]*[1-9]*)[0]*$/, "$1").replace(/\.[0]*$/, "") + "%";
  }

  const TILE_SPLIT = new RegExp("[\\-;:&|\u2013\u2014]*[^\\s\\-;:&|\u2013\u2014]*[\\-;:&|\u2013\u2014]*", "g");

  function tileFit(text, bw, bh) {
    const {pad: P, min: lo, max: hi, font} = T.tile;
    const iw = bw - 2 * P, ih = bh - 2 * P;
    if (!(iw > lo && ih > lo * 1.2)) return null;
    const words = (text.match(TILE_SPLIT) || []).filter(x => x.length);
    if (!words.length) return null;
    const width = (s, fs) => tw(s, fs, fm("valueLabels"), font);
    const lay = fs => {
      const lh = fs * 1.2, space = width(" ", fs), lines = [];
      let prog = "", wp = 0, line = 1, cut = false;
      for (let i = 0; i < words.length; i++) {
        const ww = width(words[i], fs);
        const word = words[i] + text.slice(prog.length + words[i].length).match(/^( |\n)*/)[0];
        if (prog.slice(-1) === "\n" || wp + ww > iw) {
          if (!i) { cut = true; break; }
          if (lines.length >= line) lines[line - 1] = lines[line - 1].trimEnd();
          line++;
          if (lh * line > ih || ww > iw) { cut = true; break; }
          wp = 0;
          lines.push(word);
        } else if (!i) lines[0] = word;
        else lines[line - 1] += word;
        prog += word;
        wp += ww + (word.match(/\s*$/)[0].length) * space;
      }
      return {lines: lines.filter(l => l !== ""), cut};
    };
    const sizes = words.map(x => width(x, hi)), widest = Math.max(...sizes);
    const area = d3.sum(sizes) * hi * 1.2 * (1.165 + iw / ih * 0.1);
    let fs = hi;
    if (widest > iw || area > iw * ih) fs = Math.floor(fs * Math.min(Math.sqrt(iw * ih / area), iw / widest));
    fs = Math.min(fs, Math.floor(ih * 0.8));
    for (;;) {
      fs = Math.min(hi, Math.max(lo, fs));
      const r = lay(fs);
      if (!r.cut) return {fs, lines: r.lines};
      if (fs - 1 < lo) {
        const L = r.lines.slice();
        if (!L.length) L.push("");
        else L[L.length - 1] = L[L.length - 1].replace(/\.|,$/g, "") + "...";
        return {fs: lo, lines: L};
      }
      fs--;
    }
  }

  function tileLabel(C, g, e, fill) {
    const spec = C.spec, t = T.tile, P = t.pad;
    const w = e.x1 - e.x0, h = e.y1 - e.y0, total = e.parent ? d3.sum(e.parent.leaves(), l => l.value) : e.value;
    const c = d3.color(fill), yiq = c ? (c.rgb().r * 299 + c.rgb().g * 587 + c.rgb().b * 114) / 1000 : 0;
    const ink = yiq >= t.yiq ? t.dark : t.ink;
    const name = String(e.data.cat) + (spec.valueLabels === "on" ? "\n" + fmtShort(e.value, spec.unit) : "");
    const share = spec.valueLabels === "off" ? "" : spec.unit === "%" ? tileShare(e.value) : tileShare(e.value / total * 100);
    let sh = share ? Math.min(t.max, (h - 2 * P) * 0.5) : 0;
    if (sh < t.min) sh = 0;
    const put = (box, top, mid, cls) => {
      if (!box) return;
      const lh = box.fs * 1.2, n = box.lines.length, ih = (mid ? sh + 2 * P : h - sh) - 2 * P;
      const y0 = top + P + (mid ? ih - n * lh : 0) - lh * 0.1;
      const el = g.append("text").attr("class", cls).attr("font-family", t.font).attr("font-size", box.fs).call(face, "valueLabels").attr("fill", ink)
        .attr("text-anchor", mid ? "middle" : "start");
      box.lines.forEach((l, i) => el.append("tspan").attr("x", mid ? w / 2 : P).attr("y", y0 + (i + 1) * lh - (lh - box.fs)).text(l.trimEnd()));
    };
    put(tileFit(name, w, h - sh), 0, false, "qv-tile");
    if (sh) put(tileFit(share, w, sh + 2 * P), h - sh - 2 * P, true, "qv-val");
  }

  function grow(C, need) { if (need > H) H = Math.ceil(Math.min(need, Math.max(H, C.space || Infinity))); }

  function fitRows(C, n, fixed) {
    const room = (C.space || Infinity) - fixed;
    C.fit = {n, cap: Math.max(1, Math.floor(room / ROW_MIN))};
    const hard = Math.max(1, Math.floor(room / ROW_FLOOR));
    if (n <= hard) return n;
    C.note = `Showing the first ${hard} of ${n}, to fit the screen.`;
    return hard;
  }

  function box(C, top, m) {
    const foot = footH(C);
    let left = m.left, right = m.right ?? PAD;
    const bottom = m.bottom;
    C.shift = 0;
    if (C.leg && isSide(C.leg.pos)) {
      if (C.leg.pos === "right") right += C.leg.w + 20;
      else { left += C.leg.w + 20; C.shift = C.leg.w + 20; }
    }
    C.plotBottom = H - foot;
    const iw = Math.max(40, C.W - left - right), ih = Math.max(40, C.plotBottom - top - bottom);
    const g = C.root.append("g").attr("class", "qv-plot").attr("transform", `translate(${left},${top})`);
    C.pb = {top, ih};
    return {g, iw, ih, left, top, right, bottom};
  }

  const dropFractionTicks = sel => { if (WHOLE) sel.selectAll(".tick").filter(d => typeof d === "number" && !Number.isInteger(d)).remove(); };
  function styleAxis(sel, font = FS.tick) {
    dropFractionTicks(sel);
    sel.attr("class", "axis").selectAll("path,line").attr("stroke", RULE);
    sel.selectAll("text").attr("fill", MUTED).call(face, "tickLabels").attr("font-size", font).attr("font-family", FONT);
    return sel;
  }
  const xTicks = (iw, want) => Math.max(2, Math.min(want, Math.floor(iw / 64)));
  let NT = null;
  const nt = d => { mark("ticks"); return NT || d; };
  const isN = v => typeof v === "number" && Number.isFinite(v);
  function tv(scale, n) {
    if (!scale.isLog) return scale.ticks(n);
    const lead = v => Math.round(v / Math.pow(10, Math.floor(Math.log10(v))));
    let t = scale.ticks().filter(v => [1, 2, 5].includes(lead(v)));
    if (t.length > n + 2) t = t.filter(v => lead(v) === 1);
    return t.length >= 2 ? t : scale.domain();
  }
  function vScale(C, lo, hi, o = {}) {
    const s = C.spec, x = o.axis === "x";
    const mn = x ? s.xMin : s.valueMin, mx = x ? s.xMax : s.valueMax, lg = o.noLog ? false : x ? s.xLog : s.valueLog;
    const n = o.ticks || 5;
    let sc;
    if (lg && !o.noLog) {
      const dMin = o.dataMin ?? lo, dMax = o.dataMax ?? hi;
      if (dMin > 0 && (!isN(mn) || mn > 0)) {
        sc = d3.scaleLog().domain([isN(mn) ? mn : dMin, isN(mx) ? mx : dMax]);
        if (!isN(mn) || !isN(mx)) { sc.nice(); const [a, b] = sc.domain(); sc.domain([isN(mn) ? mn : a, isN(mx) ? mx : b]); }
        sc.isLog = true;
      } else C.logNote = "A log scale needs every value above zero, so the axis stays linear.";
    }
    if (!sc) {
      let a = isN(mn) ? mn : lo, b = isN(mx) ? mx : hi;
      if (!(b > a)) { a = lo; b = hi; }
      sc = d3.scaleLinear().domain([a, b]);
      if (o.nice !== false) sc.nice(nt(n));
      const [na, nb] = sc.domain();
      sc.domain([isN(mn) ? mn : na, isN(mx) ? mx : nb]);
    }
    if (isN(mn) || isN(mx)) sc.clamp(true);
    sc.base0 = sc.isLog ? sc.domain()[0] : Math.max(Math.min(0, sc.domain()[1]), sc.domain()[0]);
    return sc;
  }
  const gridMode = C => C.spec.grid || "auto";
  function grid(g, scale, iw, ih, dir, ticks = 5, C) {
    if (C && gridMode(C) === "off") return null;
    const tvals = Array.isArray(ticks) ? ticks : tv(scale, ticks);
    const ax = dir === "y" ? d3.axisLeft(scale).tickValues(tvals).tickSize(-iw).tickFormat("") : d3.axisBottom(scale).tickValues(tvals).tickSize(-ih).tickFormat("");
    const gl = g.append("g").attr("class", "grid-lines");
    if (dir === "x") gl.attr("transform", `translate(0,${ih})`);
    gl.call(ax);
    dropFractionTicks(gl);
    gl.select(".domain").remove();
    gl.selectAll("line").attr("stroke", GRID).attr("stroke-dasharray", DASH);
    return gl;
  }
  function otherGrid(C, g, pos, iw, ih, dir) {
    if (gridMode(C) !== "both") return;
    const gl = g.insert("g", ":first-child").attr("class", "grid-lines");
    gl.selectAll("line").data(pos).join("line").attr("x1", p => (dir === "x" ? p : 0)).attr("x2", p => (dir === "x" ? p : iw))
      .attr("y1", p => (dir === "x" ? 0 : p)).attr("y2", p => (dir === "x" ? ih : p)).attr("stroke", GRID).attr("stroke-dasharray", DASH);
  }
  function refLine(C, b, sc, dir) {
    const v = C.spec.refLine;
    if (!isN(v)) return;
    const [d0, d1] = sc.domain();
    if (v < Math.min(d0, d1) || v > Math.max(d0, d1)) return;
    const p = sc(v), g = b.g.append("g").attr("class", "qv-ref");
    const label = C.spec.refLabel || fmtShort(v, C.spec.unit);
    const ln = g.append("line").attr("stroke", INK).attr("stroke-width", 1.4).attr("stroke-dasharray", "5 4");
    const t = g.append("text").attr("font-size", FS.tick).attr("font-weight", 700).attr("fill", INK).attr("font-family", FONT).text(label);
    if (dir === "h") { ln.attr("x2", b.iw).attr("y1", p).attr("y2", p); t.attr("x", b.iw - 2).attr("y", p - 6).attr("text-anchor", "end"); }
    else { ln.attr("x1", p).attr("x2", p).attr("y2", b.ih); t.attr("x", p + 5).attr("y", 12).attr("text-anchor", "start"); }
  }
  function shadeAt(dom, v, last) {
    if (v == null || v === "") return last ? dom.length - 1 : 0;
    const key = s => String(s).trim().toLowerCase();
    const hit = dom.findIndex(d => key(d) === key(v));
    if (hit >= 0) return hit;
    const n = typeof v === "number" ? v : parseFloat(v), at = d => parseFloat(d);
    if (!isN(n)) return -1;
    if (last) return dom.reduce((k, d, i) => (at(d) <= n ? i : k), -1);
    return dom.findIndex(d => at(d) >= n);
  }
  function shade(C, b, sc, dir) {
    const list = (Array.isArray(C.spec.shade) ? C.spec.shade : [C.spec.shade]).filter(o => o && typeof o === "object").slice(0, 3);
    if (!list.length) return;
    const dom = sc.domain(), len = dir === "h" ? b.ih : b.iw, step = sc.step(), bw = sc.bandwidth();
    const g = b.g.append("g").attr("class", "qv-shade").attr("pointer-events", "none");
    list.forEach(o => {
      const i0 = shadeAt(dom, o.from, false), i1 = shadeAt(dom, o.to, true);
      if (i0 < 0 || i1 < 0 || i0 > i1) return;
      const gap = bw ? (step - bw) / 2 : 0;
      const a = i0 === 0 ? 0 : Math.max(0, sc(dom[i0]) - gap), z = i1 === dom.length - 1 ? len : Math.min(len, sc(dom[i1]) + bw + gap);
      if (!(z > a)) return;
      const op = isN(o.opacity) ? Math.max(0.1, Math.min(0.9, o.opacity)) : 0.55;
      const r = g.append("rect").attr("class", "qv-shade-band").attr("fill", PAPER).attr("fill-opacity", op);
      if (dir === "h") r.attr("x", 0).attr("width", b.iw).attr("y", a).attr("height", z - a);
      else r.attr("x", a).attr("width", z - a).attr("y", 0).attr("height", b.ih);
      const room = dir === "h" ? b.iw - 12 : z - a - 12;
      const text = o.label ? clip(String(o.label), room, FS.min, 700) : "";
      if (!text || room < 24) return;
      const t = g.append("text").attr("class", "qv-shade-label").attr("font-size", FS.min).attr("font-weight", 700).attr("fill", MUTED)
        .attr("font-family", FONT).text(text);
      if (dir === "h") t.attr("x", b.iw - 6).attr("y", a + FS.min + 2).attr("text-anchor", "end");
      else t.attr("x", a + 6).attr("y", FS.min + 4).attr("text-anchor", "start");
    });
  }
  const ang = C => (isN(C.spec.tickAngle) ? Math.max(0, Math.min(90, C.spec.tickAngle)) : null);
  const rad = a => a * Math.PI / 180;
  const rotExtra = (widest, a, maxW) => (a ? Math.min(maxW, widest) * Math.sin(rad(a)) + FS.tick * Math.cos(rad(a)) * 0.6 - 2 : 0);
  function tilt(t, a) {
    t.attr("transform", `rotate(-${a})`).attr("text-anchor", "end").attr("dx", a >= 75 ? "-0.6em" : "-0.4em").attr("dy", a >= 75 ? "-0.1em" : "0.5em");
  }
  function axisTitles(C, b, xT, yT) {
    if (C.spec.axisTitles === "off") return;
    if (yT) {
      C.root.append("text").attr("class", "qv-axis-title").attr("transform", `translate(${PAD + (C.shift || 0)},${b.top + b.ih / 2}) rotate(-90)`)
        .attr("text-anchor", "middle").attr("dy", "0.75em").attr("font-size", FS.axis).call(face, "axisTitle", 700).attr("fill", INK)
        .attr("font-family", FONT).text(clip(yT, b.ih, FS.axis, fm("axisTitle", 700)));
    }
    if (xT) {
      C.root.append("text").attr("class", "qv-axis-title").attr("x", b.left + b.iw / 2).attr("y", C.plotBottom - 6).attr("text-anchor", "middle")
        .attr("font-size", FS.axis).call(face, "axisTitle", 700).attr("fill", INK).attr("font-family", FONT).text(clip(xT, b.iw, FS.axis, fm("axisTitle", 700)));
    }
  }
  function yTickW(scale, fmt, ticks = 5) { return d3.max(tv(scale, nt(ticks)), t => tw(fmt(t), FS.tick, fm("tickLabels"))) || 20; }
  const leftFor = (C, w) => PAD + (C.spec.yLabel ? 30 : 0) + w + 10;
  const bottomFor = (C, extra = 0) => 30 + extra + (C.spec.xLabel ? 30 : 0);

  const tickF = (C, d) => fm("tickLabels", 400, isHl(C, d) || isEU(d));
  function dimOf(C, names) {
    const hl = new Set((C.spec.highlight || []).map(String));
    if (!hl.size || !names.some(n => hl.has(String(n)))) return null;
    const v = C.spec.dimSize;
    if (v !== "small" && !isN(v)) return null;
    return (n, size) => (hl.has(String(n)) || isEU(n) ? size : v === "small" ? Math.max(9, size - 3) : Math.max(9, Math.min(24, Math.round(v))));
  }
  const sizeAt = (dm, n, size) => (dm ? dm(n, size) : size);
  function catLabels(C, sel) {
    sel.attr("fill", d => (isHl(C, d) ? (C.hlFill ? C.hlFill(d) : FOCUS) : INK)).call(face, "tickLabels", 400, d => isHl(C, d) || isEU(d));
  }

  function bandBottomAxis(C, g, x, ih, labels, maxW = 140, flagW = 0) {
    const bw = x.step ? x.step() : x.bandwidth();
    const drop = flagW ? flagW * 0.75 + 4 : 0;
    const dm = dimOf(C, labels);
    const widest = d3.max(labels, l => tw(l, sizeAt(dm, l, FS.tick), tickF(C, l))) || 0;
    const a = ang(C), deg = a ?? 35;
    const rotate = a != null ? a > 0 : widest > bw - 6;
    const ax = g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).tickSizeOuter(0));
    styleAxis(ax);
    const every = rotate ? Math.max(1, Math.ceil(FS.tick * 1.1 / bw)) : 1;
    ax.selectAll(".tick").each(function (d, i) {
      const t = d3.select(this).select("text"), k = flagW && flagKey(d);
      if (k) flagAt(C, d3.select(this), k, -flagW / 2, 8 + flagW * 0.375, FS.tick, flagW);
      t.append("title").text(d);
      if (i % every) { t.remove(); return; }
      t.attr("font-size", sizeAt(dm, d, FS.tick)).text(clip(d, rotate ? maxW : bw - 4, sizeAt(dm, d, FS.tick), tickF(C, d)));
      if (rotate) tilt(t, deg);
      if (drop) t.attr("transform", `translate(0,${drop})` + (rotate ? ` rotate(-${deg})` : ""));
    });
    catLabels(C, ax.selectAll(".tick text"));
    return rotate ? rotExtra(widest, deg, maxW) : 0;
  }
  function rotatedBottom(C, labels, bw, maxW) {
    const dm = dimOf(C, labels);
    const widest = d3.max(labels, l => tw(l, sizeAt(dm, l, FS.tick), tickF(C, l))) || 0;
    const a = ang(C);
    if (a != null) return rotExtra(widest, a, maxW);
    return widest > bw - 6 ? rotExtra(widest, 35, maxW) : 0;
  }
  const pointExtra = (C, labels) => rotExtra(d3.max(labels, l => tw(l, FS.tick, fm("tickLabels"))) || 0, ang(C) || 0, 140);
  function pointBottomAxis(C, g, x, ih, labels, iw) {
    const a = ang(C) || 0;
    const wide = (d3.max(labels, l => tw(l, FS.tick, fm("tickLabels"))) || 10) + 14;
    const widest = a ? Math.min(wide, FS.tick * 1.5 / Math.sin(rad(a))) : wide;
    const every = Math.max(1, Math.ceil(widest * labels.length / iw));
    const ax = g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).tickSizeOuter(0));
    styleAxis(ax);
    ax.selectAll(".tick").each(function (d, i) {
      if (i % every && i !== labels.length - 1) d3.select(this).select("text").remove();
      else if (i !== labels.length - 1 && (labels.length - 1 - i) < every && (labels.length - 1) % every) d3.select(this).select("text").remove();
      else if (a) tilt(d3.select(this).select("text").text(clip(d, 140, FS.tick, fm("tickLabels"))), a);
    });
    return ax;
  }
  function bandLeftAxis(C, g, y, labels, maxW, size = FS.label, fl = false) {
    const ax = g.append("g").call(d3.axisLeft(y).tickSizeOuter(0).tickSize(0).tickPadding(8));
    styleAxis(ax, size);
    ax.select(".domain").remove();
    const dm = dimOf(C, labels);
    ax.selectAll(".tick text").each(function (d) {
      const k = fl && flagKey(d), s = sizeAt(dm, d, size);
      d3.select(this).attr("font-size", s).text(clip(d, maxW - (k ? flagRoom(fl, s) : 0), s, tickF(C, d))).append("title").text(d);
      if (k) flagEnd(C, this, k, s);
    });
    catLabels(C, ax.selectAll(".tick text"));
    return ax;
  }
  const labelWidth = (labels, cap, size = FS.label, fl = false, dm = null) => Math.min(cap, d3.max(labels, l => tw(l, sizeAt(dm, l, size), fm("tickLabels", 700, true)) + (fl && flagKey(l) ? flagRoom(true, sizeAt(dm, l, size)) : 0)) || 0);

  function empty(C, msg) {
    C.blank = true;
    C.root.append("text").attr("class", "qv-empty").attr("x", C.W / 2).attr("y", H / 2).attr("text-anchor", "middle").attr("fill", MUTED)
      .attr("font-size", FS.label).attr("font-family", FONT).text(msg || "No numbers to draw");
  }

  function sumBy(rows, key) {
    const m = new Map();
    rows.forEach(r => m.set(key(r), (m.get(key(r)) || 0) + r.v));
    return m;
  }
  function catValues(rows, maxN, positiveOnly, rate) {
    let rs = rows.filter(r => Number.isFinite(r.v) && r.cat !== "");
    if (positiveOnly) rs = rs.filter(r => r.v > 0);
    const m = sumBy(rs, r => r.cat);
    let d = [...m].map(([cat, v]) => ({cat, v}));
    if (d.length > maxN + 1) {
      const order = new Map(d.map((e, i) => [e.cat, i]));
      d.sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
      const rest = d.slice(maxN);
      d = d.slice(0, maxN).sort((a, b) => order.get(a.cat) - order.get(b.cat));
      if (rate) d.cut = rest.length;
      else d.push({cat: OTHER, v: d3.sum(rest, e => e.v), n: rest.length});
    }
    return d;
  }
  function pivot(rows, rowKey, colKey) {
    const m = new Map();
    rows.forEach(r => {
      const k = rowKey(r) + "\u0000" + colKey(r);
      m.set(k, (m.get(k) || 0) + r.v);
    });
    return (a, b) => m.get(a + "\u0000" + b);
  }
  function capByTotal(names, totals, max) {
    if (names.length <= max) return {keep: names, other: false};
    const sorted = names.slice().sort((a, b) => (totals.get(b) || 0) - (totals.get(a) || 0));
    const top = new Set(sorted.slice(0, max));
    return {keep: names.filter(n => top.has(n)), other: true};
  }
  function lump(rows, field, max) {
    const names = uniq(rows.map(r => r[field]));
    const {keep, other} = capByTotal(names, sumBy(rows, r => Math.abs(r[field] === undefined ? 0 : 1) && r[field]), max);
    if (!other) return {rows, names};
    const k = new Set(keep);
    return {rows: rows.map(r => (k.has(r[field]) ? r : {...r, [field]: OTHER})), names: [...keep, OTHER], dropped: names.length - keep.length};
  }

  const GEO_ALIAS = {"716":["zimbabwe","republic of zimbabwe","zimb","zimbabue","simbabwe","zw","zwe"],"894":["zambia","republic of zambia","zambie","sambia","zm","zmb"],"887":["yemen","republic of yemen","yemen rep","yem","jemen","ye"],"704":["vietnam","socialist republic of vietnam","viet","viet nam","vn","vnm"],"862":["venezuela","bolivarian republic of venezuela","venezuela rb","ven","ve"],"336":["vatican","vatican city","state of the vatican city","vatican holy see","vat","ciudad del vaticano","cite du vatican","vatikanstadt","va"],"548":["vanuatu","republic of vanuatu","van","vu","vut"],"860":["uzbekistan","republic of uzbekistan","uzb","ouzbekistan","usbekistan","uz"],"858":["uruguay","oriental republic of uruguay","ury","uy"],"583":["micronesia","federated states of micronesia","micronesia federated states of","f s m","estados federados de micronesia","etats federes de micronesie","foderierte staaten von mikronesien","fm","fsm"],"584":["marshall is","marshall islands","republic of the marshall islands","m is","islas marshall","iles marshall","marshallinseln","mh","mhl"],"580":["n mariana is","northern mariana islands","commonwealth of the northern mariana islands","n m i","islas marianas del norte","iles mariannes du nord","nordliche marianen","mp","mnp"],"850":["u s virgin is","united states virgin islands","virgin islands of the united states","virgin islands u s","v i u s","islas virgenes de los estados unidos","iles vierges des etats unis","amerikanische jungferninseln","vi","vir"],"316":["guam","territory of guam","gu","gum"],"016":["american samoa","am samoa","samoa estadounidense","samoa americaines","amerikanisch samoa","as","asm"],"630":["puerto rico","commonwealth of puerto rico","p r","porto rico","pr","pri"],"840":["united states of america","united states","u s a","estados unidos","etats unis","vereinigte staaten","us","usa","u s","america"],"239":["s geo and the is","south georgia and the islands","south georgia and the south sandwich islands","s g is","islas georgias del sur y sandwich del sur","georgie du sud et les iles sandwich du sud","sudgeorgien und die sudlichen sandwichinseln","gs","sgs"],"086":["br indian ocean ter","british indian ocean territory","i o t","territorio britanico del oceano indico","territoire britannique de locean indien","britisches territorium im indischen ozean","io","iot"],"654":["saint helena","st helena","st h","isla santa elena","sainte helene","sh","shn"],"612":["pitcairn is","pitcairn islands","pitcairn henderson ducie and oeno islands","pit is","islas pitcairn","iles pitcairn","pitcairninseln","pn","pcn"],"660":["anguilla","anguila","ai","aia"],"238":["falkland is","falkland islands malvinas","falkland islands","flk is","islas malvinas","iles malouines","falklandinseln","fk","flk"],"136":["cayman is","cayman islands","cym is","islas caiman","iles caimans","ky","cym"],"060":["bermuda","bermudas or somers isles","berm","bermudas","bermudes","bm","bmu"],"092":["british virgin is","british virgin islands","v i br","islas virgenes britanicas","iles vierges britanniques","britische jungferninseln","vg","vgb"],"796":["turks and caicos is","turks and caicos islands","t c is","islas turcas y caicos","iles turques et caiques","turks und caicosinseln","tc","tca"],"500":["montserrat","monts","ms","msr"],"832":["jersey","bailiwick of jersey","jey","je"],"831":["guernsey","bailiwick of guernsey","guern","guernesey","gg","ggy"],"833":["isle of man","ioman","isla de man","ile de man","im","imn"],"826":["united kingdom","united kingdom of great britain and northern ireland","u k","reino unido","royaume uni","vereinigtes konigreich","gb","gbr","uk","great britain","britain","england","scotland","wales"],"784":["united arab emirates","u a e","emiratos arabes unidos","emirats arabes unis","vereinigte arabische emirate","ae","are","uae","emirates"],"804":["ukraine","ukr","ucrania","ua"],"800":["uganda","republic of uganda","uga","ouganda","ug"],"795":["turkmenistan","turkm","tm","tkm"],"792":["turkey","republic of turkey","tur","turquia","turquie","turkei","tr","turkiye"],"788":["tunisia","republic of tunisia","tun","tunez","tunisie","tunesien","tn"],"780":["trinidad and tobago","republic of trinidad and tobago","tr t","trinidad y tobago","trinite et tobago","trinidad und tobago","tt","tto"],"776":["tonga","kingdom of tonga","tongo","to","ton"],"768":["togo","togolese republic","tg","tgo"],"626":["timor leste","east timor","democratic republic of timor leste","t l","timor oriental","osttimor","tl","tls"],"764":["thailand","kingdom of thailand","thai","tailandia","thailande","th","tha"],"834":["tanzania","united republic of tanzania","tanz","tanzanie","tansania","tz","tza"],"762":["tajikistan","republic of tajikistan","tjk","tayikistan","tadjikistan","tadschikistan","tj"],"158":["taiwan","republica de china","republik china","cn tw","twn","tw"],"760":["syria","syrian arab republic","siria","syrie","syrien","sy","syr"],"756":["switzerland","swiss confederation","switz","suiza","suisse","schweiz","ch","che"],"752":["sweden","kingdom of sweden","swe","suecia","suede","schweden","se"],"748":["eswatini","kingdom of eswatini","esw","suazilandia","sz","swz"],"740":["suriname","republic of suriname","sur","surinam","sr"],"728":["s sudan","south sudan","republic of south sudan","s sud","sudan del sur","soudan du sud","sudsudan","ss","ssd","sds"],"729":["sudan","republic of the sudan","soudan","sd","sdn"],"144":["sri lanka","democratic socialist republic of sri lanka","sri l","lk","lka"],"724":["spain","kingdom of spain","sp","espana","espagne","spanien","es","esp"],"410":["south korea","republic of korea","korea rep","s k","corea del sur","coree du sud","sudkorea","kr","kor","korea"],"710":["south africa","republic of south africa","s af","sudafrica","afrique du sud","sudafrika","za","zaf"],"706":["somalia","federal republic of somalia","som","somalie","so"],"090":["solomon is","solomon islands","s is","islas salomon","iles salomon","salomonen","sb","slb"],"703":["slovakia","slovak republic","svk","eslovaquia","slovaquie","slowakei","sk"],"705":["slovenia","republic of slovenia","slo","eslovenia","slovenie","slowenien","si","svn"],"702":["singapore","republic of singapore","sing","singapur","singapour","sg","sgp"],"694":["sierra leone","republic of sierra leone","sierra leona","sl","sle"],"690":["seychelles","republic of seychelles","syc","seychellen","sc"],"688":["serbia","republic of serbia","serb","serbie","serbien","rs","srb"],"686":["senegal","republic of senegal","sen","sn"],"682":["saudi arabia","kingdom of saudi arabia","saud","arabia saudita","arabie saoudite","saudi arabien","sa","sau"],"678":["sao tome and principe","democratic republic of sao tome and principe","s t p","santo tome y principe","sao tome et principe","sao tome und principe","st","stp"],"674":["san marino","republic of san marino","s m","saint marin","sm","smr"],"882":["samoa","independent state of samoa","ws","wsm"],"670":["st vin and gren","saint vincent and the grenadines","st vincent and the grenadines","st v g","san vicente y las granadinas","saint vincent et les grenadines","st vincent und die grenadinen","vc","vct"],"662":["saint lucia","st lucia","santa lucia","sainte lucie","lc","lca"],"659":["st kitts and nevis","saint kitts and nevis","federation of saint kitts and nevis","st k n","san cristobal y nieves","saint christophe et nieves","st kitts und nevis","kn","kna"],"646":["rwanda","republic of rwanda","rwa","ruanda","rw"],"643":["russia","russian federation","rus","rusia","russie","russland","ru"],"642":["romania","rom","rumania","roumanie","rumanien","ro","rou"],"634":["qatar","state of qatar","catar","katar","qa","qat"],"620":["portugal","portuguese republic","port","pt","prt"],"616":["poland","republic of poland","pol","polonia","pologne","polen","pl"],"608":["philippines","republic of the philippines","phil","filipinas","philippinen","ph","phl"],"604":["peru","republic of peru","perou","pe","per"],"600":["paraguay","republic of paraguay","para","py","pry"],"598":["papua new guinea","independent state of papua new guinea","p n g","papua nueva guinea","papouasie nouvelle guinee","papua neuguinea","pg","png"],"591":["panama","republic of panama","pan","pa"],"585":["palau","republic of palau","palaos","pw","plw"],"586":["pakistan","islamic republic of pakistan","pak","pk"],"512":["oman","sultanate of oman","om","omn"],"578":["norway","kingdom of norway","nor","noruega","norvege","norwegen","no"],"408":["north korea","dem rep korea","democratic people s republic of korea","korea dem rep","n k","corea del norte","coree du nord","nordkorea","kp","prk"],"566":["nigeria","federal republic of nigeria","ng","nga"],"562":["niger","republic of niger","ne","ner"],"558":["nicaragua","republic of nicaragua","nic","ni"],"554":["new zealand","n z","nueva zelanda","nouvelle zelande","neuseeland","nz","nzl"],"570":["niue","nu","niu"],"184":["cook is","cook islands","islas cook","iles cook","cookinseln","ck","cok"],"528":["netherlands","kingdom of the netherlands","neth","paises bajos","pays bas","niederlande","nl","nld","holland"],"533":["aruba","aw","abw"],"531":["curacao","cur","curazao","cw","cuw"],"524":["nepal","np","npl"],"520":["nauru","republic of nauru","nr","nru"],"516":["namibia","republic of namibia","nam","namibie","na"],"508":["mozambique","republic of mozambique","moz","mosambik","mz"],"504":["morocco","kingdom of morocco","mor","marruecos","maroc","marokko","ma","mar"],"732":["w sahara","western sahara","sahrawi arab democratic republic","w sah","sahara occidental","westsahara","eh","esh","sah"],"499":["montenegro","mont","me","mne"],"496":["mongolia","mong","mongolie","mongolei","mn","mng"],"498":["moldova","republic of moldova","mda","moldavia","moldavie","republik moldau","md"],"492":["monaco","principality of monaco","mco","mc"],"484":["mexico","united mexican states","mex","mexique","mexiko","mx"],"480":["mauritius","republic of mauritius","mus","mauricio","maurice","mu"],"478":["mauritania","islamic republic of mauritania","mrt","mauritanie","mauretanien","mr"],"470":["malta","republic of malta","malte","mt","mlt"],"466":["mali","republic of mali","ml","mli"],"462":["maldives","republic of maldives","mald","maldivas","malediven","mv","mdv"],"458":["malaysia","malay","malasia","malaisie","my","mys"],"454":["malawi","republic of malawi","mal","malaui","mw","mwi"],"450":["madagascar","republic of madagascar","mad","madagaskar","mg","mdg"],"807":["macedonia","north macedonia","republic of north macedonia","n mac","macedonia del norte","macedoine du nord","nordmazedonien","mk","mkd"],"442":["luxembourg","grand duchy of luxembourg","lux","luxemburgo","luxemburg","lu"],"440":["lithuania","republic of lithuania","lith","lituania","lituanie","litauen","lt","ltu"],"438":["liechtenstein","principality of liechtenstein","liech","li","lie"],"434":["libya","libia","libye","libyen","ly","lby"],"430":["liberia","republic of liberia","lr","lbr"],"426":["lesotho","kingdom of lesotho","les","lesoto","ls","lso"],"422":["lebanon","lebanese republic","leb","libano","liban","libanon","lb","lbn"],"428":["latvia","republic of latvia","lat","letonia","lettonie","lettland","lv","lva"],"418":["laos","lao pdr","lao people s democratic republic","la","lao"],"417":["kyrgyzstan","kyrgyz republic","kgz","kirguistan","kirghizistan","kirgisistan","kg"],"414":["kuwait","state of kuwait","kwt","koweit","kw"],"296":["kiribati","republic of kiribati","kir","ki"],"404":["kenya","republic of kenya","ken","kenia","ke"],"398":["kazakhstan","republic of kazakhstan","kaz","kazajistan","kasachstan","kz"],"400":["jordan","hashemite kingdom of jordan","jord","jordania","jordanie","jordanien","jo","jor"],"392":["japan","japon","jp","jpn"],"388":["jamaica","jam","jamaique","jamaika","jm"],"380":["italy","italian republic","italia","italie","italien","it","ita"],"376":["israel","state of israel","isr","il"],"275":["palestine","west bank and gaza","palestine west bank and gaza","pal","palestina","palastina","ps","pse","psx"],"372":["ireland","ire","irlanda","irlande","irland","ie","irl"],"368":["iraq","republic of iraq","irak","iq","irq"],"364":["iran","islamic republic of iran","iran islamic rep","ir","irn"],"360":["indonesia","republic of indonesia","indo","indonesie","indonesien","id","idn"],"356":["india","republic of india","inde","indien","in","ind"],"352":["iceland","republic of iceland","islandia","islande","island","is","isl"],"348":["hungary","republic of hungary","hun","hungria","hongrie","ungarn","hu"],"340":["honduras","republic of honduras","hond","hn","hnd"],"332":["haiti","republic of haiti","ht","hti"],"328":["guyana","co operative republic of guyana","guy","gy"],"624":["guinea bissau","republic of guinea bissau","gnb","guinea bisau","guinee bissau","gw"],"324":["guinea","republic of guinea","gin","guinee","gn"],"320":["guatemala","republic of guatemala","guat","gt","gtm"],"308":["grenada","gren","granada","grenade","gd","grd"],"300":["greece","hellenic republic","grecia","grece","griechenland","gr","grc","hellas","el","ellada"],"288":["ghana","republic of ghana","gh","gha"],"276":["germany","federal republic of germany","ger","alemania","allemagne","deutschland","de","deu"],"268":["georgia","geo","georgie","georgien","ge"],"270":["gambia","republic of the gambia","gambia the","gambie","gm","gmb"],"266":["gabon","gabonese republic","gabun","ga","gab"],"250":["france","french republic","fr","francia","frankreich","fra"],"666":["st pierre and miquelon","saint pierre and miquelon","st p m","san pedro y miquelon","saint pierre et miquelon","saint pierre und miquelon","pm","spm"],"876":["wallis and futuna is","wallis and futuna islands","wallis and futuna","wlf","wallis y futuna","wallis et futuna","wallis und futuna","wf"],"663":["st martin","saint martin","saint martin french part","st martin french part","mf","maf"],"652":["st barthelemy","saint barthelemy","st b","san bartolome","bl","blm"],"258":["fr polynesia","french polynesia","fr poly","polinesia francesa","polynesie francaise","franzosisch polynesien","pf","pyf"],"540":["new caledonia","new c","nueva caledonia","nouvelle caledonie","neukaledonien","nc","ncl"],"260":["fr s antarctic lands","french southern and antarctic lands","fr s and antarctic lands","territory of the french southern and antarctic lands","fr s a l","tierras australes y antarticas francesas","terres australes et antarctiques francaises","franzosische sud und antarktisgebiete","tf","atf"],"248":["aland","aland islands","ax","ala","ald"],"246":["finland","republic of finland","fin","finlandia","finlande","finnland","fi"],"242":["fiji","republic of fiji","fiyi","fidji","fidschi","fj","fji"],"231":["ethiopia","federal democratic republic of ethiopia","eth","etiopia","ethiopie","athiopien","et"],"233":["estonia","republic of estonia","est","estonie","estland","ee"],"232":["eritrea","state of eritrea","erit","erythree","er","eri"],"226":["eq guinea","equatorial guinea","republic of equatorial guinea","eq g","guinea ecuatorial","guinee equatoriale","aquatorialguinea","gq","gnq"],"222":["el salvador","republic of el salvador","el s","salvador","sv","slv"],"818":["egypt","arab republic of egypt","egypt arab rep","egipto","egypte","agypten","eg","egy"],"218":["ecuador","republic of ecuador","ecu","equateur","ec"],"214":["dominican rep","dominican republic","dom rep","republica dominicana","republique dominicaine","dominikanische republik","do","dom"],"212":["dominica","commonwealth of dominica","d inca","dominique","dm","dma"],"262":["djibouti","republic of djibouti","dji","yibuti","dschibuti","dj"],"304":["greenland","grlnd","groenlandia","groenland","gronland","gl","grl"],"234":["faeroe is","faeroe islands","faroe islands","froyar is faeroe is","islas feroe","iles feroe","faroer","fo","fro"],"208":["denmark","kingdom of denmark","den","dinamarca","danemark","dk","dnk"],"203":["czechia","czech republic","cz","republica checa","tchequie","tschechien","cze"],"196":["cyprus","republic of cyprus","cyp","chipre","chypre","republik zypern","cy"],"192":["cuba","republic of cuba","kuba","cu","cub"],"191":["croatia","republic of croatia","cro","croacia","croatie","kroatien","hr","hrv"],"384":["cote d ivoire","ivory coast","republic of ivory coast","i c","costa de marfil","elfenbeinkuste","ci","civ"],"188":["costa rica","republic of costa rica","c r","cr","cri"],"180":["dem rep congo","democratic republic of the congo","congo dem rep","d r c","republica democratica del congo","republique democratique du congo","demokratische republik kongo","cd","cod","drc","dr congo","congo kinshasa"],"178":["congo","republic of the congo","congo rep","rep congo","republica del congo","republique du congo","republik kongo","cg","cog","congo brazzaville"],"174":["comoros","union of the comoros","com","comoras","comores","komoren","km"],"170":["colombia","republic of colombia","col","colombie","kolumbien","co"],"156":["china","people s republic of china","republique populaire de chine","volksrepublik china","cn","chn","prc","mainland china"],"446":["macao","macao s a r","macau","macao special administrative region prc","macao sar china","mac","mo"],"344":["hong kong","hong kong s a r","hong kong special administrative region prc","hong kong sar china","h k","hongkong","hk","hkg"],"152":["chile","republic of chile","chili","cl","chl"],"148":["chad","republic of chad","tchad","tschad","td","tcd"],"140":["central african rep","central african republic","c a r","republica centroafricana","republique centrafricaine","zentralafrikanische republik","cf","caf"],"132":["cabo verde","republic of cabo verde","cape verde","c vd","cap vert","kap verde","cv","cpv"],"124":["canada","can","kanada","ca"],"120":["cameroon","republic of cameroon","cam","camerun","cameroun","kamerun","cm","cmr"],"116":["cambodia","kingdom of cambodia","camb","camboya","cambodge","kambodscha","kh","khm"],"104":["myanmar","republic of the union of myanmar","myan","birmania","birmanie","mm","mmr"],"108":["burundi","republic of burundi","bur","bi","bdi"],"854":["burkina faso","b f","bf","bfa"],"100":["bulgaria","republic of bulgaria","bulg","bulgarie","bulgarien","bg","bgr"],"096":["brunei","brunei darussalam","negara brunei darussalam","bn","brn"],"076":["brazil","federative republic of brazil","brasil","bresil","brasilien","br","bra"],"072":["botswana","republic of botswana","bwa","botsuana","bw"],"070":["bosnia and herz","bosnia and herzegovina","b h","bosnia y herzegovina","bosnie herzegovine","bosnien und herzegowina","ba","bih"],"068":["bolivia","plurinational state of bolivia","bolivie","bolivien","bo","bol"],"064":["bhutan","kingdom of bhutan","butan","bhoutan","bt","btn"],"204":["benin","republic of benin","bj","ben"],"084":["belize","belice","bz","blz"],"056":["belgium","kingdom of belgium","belg","belgica","belgique","belgien","be","bel"],"112":["belarus","republic of belarus","bela","bielorrusia","bielorussie","by","blr"],"052":["barbados","barb","barbade","bb","brb"],"050":["bangladesh","people s republic of bangladesh","bang","banglades","bangladesch","bd","bgd"],"048":["bahrain","kingdom of bahrain","bahr","barein","bahrein","bh","bhr"],"044":["bahamas","commonwealth of the bahamas","bahamas the","bhs","bs"],"031":["azerbaijan","republic of azerbaijan","aze","azerbaiyan","azerbaidjan","aserbaidschan","az"],"040":["austria","republic of austria","aust","autriche","osterreich","at","aut"],"036":["ashmore and cartier is","australia","commonwealth of australia","auz","australie","australien","au","aus","indian ocean ter","indian ocean territories","australian indian ocean territories","ind oc ter","territorios australianos del oceano indico","territoires exterieurs australiens de l ocean indien","australische territorien im indischen ozean","ioa","ashmore and cartier islands","territory of ashmore and cartier islands","a c is","islas ashmore y cartier","iles ashmore et cartier","ashmore und cartierinseln","atc"],"334":["heard i and mcdonald is","heard i and mcdonald islands","heard island and mcdonald islands","territory of heard island and mcdonald islands","h m is","islas heard y mcdonald","iles heard et macdonald","heard und mcdonaldinseln","hm","hmd"],"574":["norfolk island","territory of norfolk island","nfk i","isla norfolk","ile norfolk","norfolkinsel","nf","nfk"],"051":["armenia","republic of armenia","arm","armenie","armenien","am"],"032":["argentina","argentine republic","arg","argentine","argentinien","ar"],"028":["antigua and barb","antigua and barbuda","ant b","antigua y barbuda","antigua et barbuda","antigua und barbuda","ag","atg"],"024":["angola","people s republic of angola","ao","ago"],"020":["andorra","principality of andorra","and","andorre","ad"],"012":["algeria","people s democratic republic of algeria","alg","argelia","algerie","algerien","dz","dza"],"008":["albania","republic of albania","alb","albanie","albanien","al"],"004":["afghanistan","islamic state of afghanistan","afg","afganistan","af"],"010":["antarctica","ant","antartida","antarctique","antarktika","aq","ata"],"534":["sint maarten","sint maarten dutch part","st maarten dutch part","sx","sxm"]};
  const normName = s => String(s).normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().replace(/^the /, "");
  const NAME_TO_ID = new Map();
  for (const [id, names] of Object.entries(GEO_ALIAS)) for (const n of names) NAME_TO_ID.set(n, id);
  const countryId = name => NAME_TO_ID.get(normName(name)) || null;
  const FLAGS = window.QV_FLAGS || (window.QV_FLAGS = {});
  const nameKey = n => (n == null || n === "" ? null : isEU(n) ? "eu" : countryId(n));
  const flagKey = n => { const k = nameKey(n); return k && Object.hasOwn(FLAGS, k) ? k : null; };
  const flagBox = size => { const h = Math.round(size * 1.5) / 2; return {h, w: h * 4 / 3, gap: Math.round(size * 0.35)}; };
  const flagRoom = (fl, size) => (fl ? flagBox(size).w + flagBox(size).gap : 0);
  function flagsOn(C, names) {
    const list = (names || []).map(String).filter(n => n !== OTHER);
    if (!list.some(flagKey)) return false;
    const mode = C.spec.flags;
    if (mode === "off") return false;
    return mode === "on" || countryShareOf(list) >= 0.8;
  }
  function flagSym(C, key) {
    const id = `qvf-${T.name}-${key}`;
    if (!C.flagDefs) { C.flagDefs = C.root.insert("defs", ":first-child"); C.flagSet = new Set(); }
    if (!C.flagSet.has(key)) {
      C.flagSet.add(key);
      const sw = 640 / flagBox(FS.label).w * 0.75;
      const s = C.flagDefs.append("symbol").attr("id", id).attr("viewBox", "0 0 640 480").attr("preserveAspectRatio", "none");
      s.html(FLAGS[key]);
      s.append("rect").attr("x", sw / 2).attr("y", sw / 2).attr("width", 640 - sw).attr("height", 480 - sw).attr("fill", "none").attr("stroke", RULE).attr("stroke-width", sw);
    }
    return id;
  }
  function flagAt(C, sel, key, x, cy, size, w) {
    const fw = w || flagBox(size).w, fh = fw * 3 / 4;
    return sel.append("use").attr("class", "qv-flag").attr("href", "#" + flagSym(C, key)).attr("x", x).attr("y", cy - fh / 2).attr("width", fw).attr("height", fh);
  }
  function flagEnd(C, el, key, size) { (C.flagEnds || (C.flagEnds = [])).push({el, key, size}); }
  function placeFlags(C) {
    (C.flagEnds || []).forEach(({el, key, size}) => {
      const node = el.firstChild;
      if (!node || node.nodeType !== 3 || !el.parentNode) return;
      const f = flagBox(size), x = +(el.getAttribute("x") || 0), y = +(el.getAttribute("y") || 0);
      flagAt(C, d3.select(el.parentNode), key, x - tw(node.nodeValue, size, (el.getAttribute("font-style") === "italic" ? "italic " : "") + (+el.getAttribute("font-weight") || 400)) - f.gap - f.w, y, size);
    });
  }
  function flagKeys(spec) {
    if (!spec) return [];
    const out = new Set();
    const add = rows => (Array.isArray(rows) ? rows : []).forEach(r => r && [r.cat, r.series].forEach(n => { const k = nameKey(n); if (k) out.add(k); }));
    add(spec.rows);
    Object.values(spec.variants || {}).forEach(v => v && add(v.rows));
    return [...out];
  }

  const INLINE = window.QV_GEO_INLINE || null;
  let geoFeatures = null, geoLoading = null;
  const geoWaiting = new Set();
  function loadScript(src) {
    return new Promise((ok, no) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
  }
  function redrawWaiting(set) {
    set.forEach(el => { const s = el.__qv; if (s && s.spec && s.spec.kind === "map") render(el, s.spec, s.fixedW ? {width: s.fixedW} : undefined); });
  }
  function loadGeo() {
    if (geoLoading) return geoLoading;
    geoLoading = (async () => {
      if (!window.topojson) await loadScript(BASE + "vendor/topojson-client.min.js");
      const world = INLINE && INLINE.world ? INLINE.world : await getJSON(BASE + "vendor/countries-50m.json");
      geoFeatures = topojson.feature(world, world.objects.countries).features.filter(f => f.id);
      redrawWaiting(geoWaiting);
      geoWaiting.clear();
    })().catch(e => { geoLoading = null; throw e; });
    return geoLoading;
  }
  if (INLINE && INLINE.world && window.topojson) {
    geoFeatures = topojson.feature(INLINE.world, INLINE.world.objects.countries).features.filter(f => f.id);
    geoLoading = Promise.resolve();
  }
  function mainland(f) {
    if (f.geometry.type !== "MultiPolygon") return f;
    const polys = f.geometry.coordinates.map(p => ({p, a: d3.geoArea({type: "Polygon", coordinates: p})}));
    const big = d3.max(polys, e => e.a);
    return {type: "Feature", geometry: {type: "MultiPolygon", coordinates: polys.filter(e => e.a >= big * 0.25).map(e => e.p)}};
  }

  const normRegion = s => normName(s).replace(/^(region de la|region del|region de|region|provincia de|province of|state of|estado de|community of|comunidad de|comunitat) |( community)$/g, "");
  const geoCache = new Map(), geoWait = new Map();
  const INDEX_URL = () => BASE + "geo/regions/index.json";
  if (INLINE) {
    if (INLINE.index) geoCache.set(INDEX_URL(), INLINE.index);
    Object.entries(INLINE.regions || {}).forEach(([a3, topo]) => geoCache.set(BASE + "geo/regions/" + a3 + ".json", topo));
  }
  const indexReady = [];
  function geoJSON(url, svgEl) {
    if (geoCache.has(url)) return geoCache.get(url);
    if (svgEl) { if (!geoWait.has(url)) geoWait.set(url, new Set()); geoWait.get(url).add(svgEl); }
    if (!geoWait.get(url)?.loading) {
      const w = geoWait.get(url) || new Set(); w.loading = true; geoWait.set(url, w);
      getJSON(url).catch(() => null).then(j => {
        geoCache.set(url, j);
        const els = geoWait.get(url); geoWait.delete(url);
        if (els) redrawWaiting(els);
        if (url === INDEX_URL()) { indexReady.forEach(f => f()); indexReady.length = 0; }
      });
    }
    return undefined;
  }
  function loadRegionIndex() {
    const have = geoJSON(INDEX_URL());
    return have !== undefined ? Promise.resolve(have) : new Promise(ok => indexReady.push(() => ok(geoCache.get(INDEX_URL()))));
  }
  function regionMatch(names) {
    const idx = geoCache.get(INDEX_URL());
    if (!idx || !names.length) return null;
    const votes = {};
    names.forEach(n => { const hit = idx[normRegion(n)]; if (hit) [].concat(hit).forEach(a => votes[a] = (votes[a] || 0) + 1); });
    const best = Object.entries(votes).sort((a, b) => b[1] - a[1])[0];
    return best && best[1] >= Math.max(2, names.length * 0.5) ? {a3: best[0], n: best[1]} : null;
  }
  function regionCountry(names) { const m = regionMatch(names); return m ? m.a3 : null; }

  function barLabelFits(text, room, size = FS.label) { return tw(text, size, fm("valueLabels")) <= room; }

  const R = {
    bar(C) {
      const {spec} = C;
      let d = catValues(C.rows, 40, false, spec.rate);
      if (!d.length) return empty(C);
      if (d.some(e => e.cat === OTHER && e.n)) C.note = `Top 40 shown, ${d.at(-1).n} more in Other.`;
      if (d.cut) C.note = `Top 40 shown, ${d.cut} more left out.`;
      const names = d.map(e => e.cat);
      const color = palette(C, names, {single: GREEN, hlSame: true, rest: GREY});
      const anyHl = color.hl.size > 0;
      const fill = e => (!anyHl && !(spec.colors || {})[e.cat] && e.v < 0 && !isEU(e.cat) ? RED : color(e.cat));
      const fl = flagsOn(C, names);
      C.legFlags = fl;
      if (anyHl) {
        const country = countryShareOf(names) >= 0.5;
        const hlNames = names.filter(n => color.hl.has(n));
        const eu = names.filter(n => isEU(n) && !color.hl.has(n));
        legend(C, [], null, [...hlNames.map(n => ({name: n, color: color(n)})), ...eu.map(n => ({name: n, color: NAVY})),
          ...(names.length > hlNames.length + eu.length ? [{name: country ? "Other countries" : "Others", color: GREY}] : [])]);
      } else legend(C, [], null);
      const top = C.top + 4;
      const lo = Math.min(0, d3.min(d, e => e.v)), hi = Math.max(0, d3.max(d, e => e.v));
      const fmt = v => fmtShort(v, spec.unit), fmtT = v => fmtTick(v, spec.unit);
      const showLabels = spec.valueLabels !== "off";
      const y0 = vScale(C, lo * 1.1, hi * 1.12 || 1, {dataMin: d3.min(d, e => e.v), dataMax: d3.max(d, e => e.v)}).range([300, 0]);
      const left = leftFor(C, yTickW(y0, fmtT));
      const step = (C.W - left - PAD - (C.leg && isSide(C.leg.pos) ? C.leg.w + 20 : 0)) / d.length;
      const pin = Math.max(d.length > 12 ? 0.3 : 0.38, 1 - 96 / Math.max(1, step));
      const slot = step * d.length / Math.max(1, d.length - (spec.barGap ?? Math.min(0.75, pin)) + 0.28);
      const dm = dimOf(C, names), vfs = n => sizeAt(dm, n, FS.label);
      const flat = (d3.max(d, e => tw(e.cat, sizeAt(dm, e.cat, FS.tick), tickF(C, e.cat))) || 0) <= slot - 6;
      const timeCats = d.length > 1 && d.every(e => TIME_CAT.test(String(e.cat).trim()));
      const horizontal = spec.orientation === "horizontal" || (spec.orientation !== "vertical" && !timeCats && (d.length > 30 || !flat && !(ang(C) > 0)));
      C.hlFill = n => color(n);
      C.orient = horizontal ? "horizontal" : "vertical";
      if (horizontal) {
        const hb = (extra = 0) => 30 + extra + (spec.yLabel ? 30 : 0);
        const rowH = 26;
        const k = fitRows(C, d.length, top + hb() + footH(C) + 10);
        if (k < d.length) d = d.slice(0, k);
        grow(C, top + d.length * rowH + hb() + footH(C) + 10);
        const lw = labelWidth(d.map(e => e.cat), Math.min(240, C.W * 0.32), FS.label, fl, dm);
        const valW = showLabels ? d3.max(d, e => tw(fmt(e.v), vfs(e.cat), fm("valueLabels", 400, isHl(C, e.cat)))) + 12 : 0;
        const x0 = vScale(C, lo, hi || 1, {dataMin: d3.min(d, e => e.v), dataMax: d3.max(d, e => e.v)});
        const xa = rotatedBottom(C, tv(x0, nt(5)).map(fmtT), 1e9, 80);
        const b = box(C, top, {left: PAD + (spec.xLabel ? 30 : 0) + lw + 10, bottom: hb(xa), right: PAD + Math.max(16, valW)});
        const x = x0.range([0, b.iw]), y = d3.scaleBand(d.map(e => e.cat), [0, b.ih]).padding(spec.barGap ?? 0.28);
        const base = x.base0, xt = tv(x, nt(xTicks(b.iw, 5)));
        grid(b.g, x, b.iw, b.ih, "x", xt, C);
        otherGrid(C, b.g, d.map(e => y(e.cat) + y.bandwidth() / 2), b.iw, b.ih, "y");
        const xax = styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).tickValues(xt).tickFormat(fmtT).tickSizeOuter(0)));
        if (ang(C)) xax.selectAll(".tick text").each(function () { tilt(d3.select(this), ang(C)); });
        const bars = b.g.selectAll("rect.bar").data(d).join("rect").attr("class", "bar").attr("fill", fill).attr("y", e => y(e.cat))
          .attr("height", y.bandwidth()).attr("x", x(base)).attr("width", 0);
        bars.append("title").text(e => `${e.cat}: ${fmtFull(e.v, spec.unit)}`);
        (C.anim ? bars.transition().duration(700).ease(d3.easeCubicOut) : bars).attr("x", e => Math.min(x(base), x(e.v))).attr("width", e => Math.abs(x(e.v) - x(base)));
        shade(C, b, y, "h");
        if (showLabels && (spec.valueLabels === "on" || y.bandwidth() >= FS.label * 0.8)) {
          b.g.selectAll("text.bar-label").data(d).join("text").attr("class", "bar-label").attr("font-size", e => vfs(e.cat)).attr("fill", INK)
            .call(face, "valueLabels", 400, e => isHl(C, e.cat)).attr("font-family", FONT).attr("y", e => y(e.cat) + y.bandwidth() / 2).attr("dy", "0.35em")
            .attr("x", e => x(e.v) + (e.v < 0 ? -6 : 6)).attr("text-anchor", e => (e.v < 0 ? "end" : "start")).text(e => fmt(e.v));
        }
        bandLeftAxis(C, b.g, y, d.map(e => e.cat), lw, FS.label, fl);
        b.g.append("line").attr("x1", x(base)).attr("x2", x(base)).attr("y2", b.ih).attr("stroke", FAINT);
        refLine(C, b, x, "v");
        axisTitles(C, b, spec.yLabel, spec.xLabel);
      } else {
        const rot = rotatedBottom(C, d.map(e => e.cat), step, Math.min(170, H * 0.3));
        const fv = fl ? Math.min(flagBox(FS.tick).w, step - 4) : 0, flagW = fv >= 8 ? fv : 0;
        const b = box(C, top, {left, bottom: bottomFor(C, rot + (flagW ? flagW * 0.75 + 4 : 0))});
        const x = d3.scaleBand(d.map(e => e.cat), [0, b.iw]).paddingInner(spec.barGap ?? Math.min(0.75, pin)).paddingOuter(0.14);
        const y = y0.range([b.ih, 0]), base = y.base0, yt = tv(y, nt(5));
        grid(b.g, y, b.iw, b.ih, "y", yt, C);
        otherGrid(C, b.g, d.map(e => x(e.cat) + x.bandwidth() / 2), b.iw, b.ih, "x");
        styleAxis(b.g.append("g").call(d3.axisLeft(y).tickValues(yt).tickFormat(fmtT).tickSizeOuter(0))).select(".domain").remove();
        const bars = b.g.selectAll("rect.bar").data(d).join("rect").attr("class", "bar").attr("fill", fill).attr("x", e => x(e.cat))
          .attr("width", x.bandwidth()).attr("y", y(base)).attr("height", 0);
        bars.append("title").text(e => `${e.cat}: ${fmtFull(e.v, spec.unit)}`);
        (C.anim ? bars.transition().duration(700).ease(d3.easeCubicOut) : bars).attr("y", e => Math.min(y(base), y(e.v))).attr("height", e => Math.abs(y(e.v) - y(base)));
        shade(C, b, x, "v");
        const fits = d.every(e => barLabelFits(fmt(e.v), x.step() - 2, vfs(e.cat)));
        if (showLabels && (spec.valueLabels === "on" || fits)) {
          b.g.selectAll("text.bar-label").data(d).join("text").attr("class", "bar-label").attr("font-size", e => vfs(e.cat)).attr("fill", INK)
            .call(face, "valueLabels", 400, e => isHl(C, e.cat)).attr("font-family", FONT).attr("text-anchor", "middle").attr("x", e => x(e.cat) + x.bandwidth() / 2)
            .attr("y", e => (e.v < 0 ? y(e.v) + vfs(e.cat) + 3 : y(e.v) - 6)).text(e => fmt(e.v));
        }
        bandBottomAxis(C, b.g, x, b.ih, d.map(e => e.cat), Math.min(170, H * 0.3), flagW);
        b.g.append("line").attr("x2", b.iw).attr("y1", y(base)).attr("y2", y(base)).attr("stroke", FAINT);
        refLine(C, b, y, "h");
        axisTitles(C, b, spec.xLabel, spec.yLabel);
      }
    },

    line(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.t !== "").map(r => ({...r, series: r.series || spec.yLabel || "Value"}));
      if (!rows.length) return empty(C);
      const ts = uniq(rows.map(r => r.t));
      let names = uniq(rows.map(r => r.series));
      const cap = color0 => color0;
      if (names.length > 10) {
        const {keep} = capByTotal(names, sumBy(rows, r => r.series), 10);
        const hl = new Set(spec.highlight || []);
        const keepSet = new Set([...keep, ...names.filter(n => hl.has(n))]);
        C.note = `${keepSet.size} of ${names.length} series shown.`;
        names = names.filter(n => keepSet.has(n));
      }
      const get = pivot(rows, r => r.series, r => r.t);
      const color = palette(C, names, {rest: FAINT});
      const anyHl = color.hl.size > 0;
      const strong = n => !anyHl || color.hl.has(n) || isEU(n);
      const series = names.map(s => ({s, pts: ts.map(t => ({t, v: get(s, t)}))})).sort((a, b) => strong(a.s) - strong(b.s));
      const all = series.flatMap(e => e.pts.map(p => p.v)).filter(v => v !== undefined);
      const lastV = new Map(series.map(e => [e.s, (e.pts.filter(p => p.v !== undefined).at(-1) || {}).v]));
      C.legFlags = flagsOn(C, names);
      if (names.length > 1 || spec.legend === "on" || C.toggle) legend(C, names, color, null, lastV); else legend(C, [], null);
      const top = C.top + 4;
      const [mn, mx] = d3.extent(all);
      const pad = (mx - mn) * 0.05 || Math.abs(mx) * 0.1 || 1;
      const fmtT = v => fmtTick(v, spec.unit);
      const y0 = vScale(C, mn >= 0 && mn < (mx - mn) * 0.6 ? 0 : mn - pad, mx + pad, {dataMin: mn, dataMax: mx}).range([300, 0]);
      const b = box(C, top, {left: leftFor(C, yTickW(y0, fmtT)), bottom: bottomFor(C, pointExtra(C, ts)), right: Math.max(PAD + 10, tw(ts.at(-1), FS.tick, fm("tickLabels")) / 2 + 6)});
      const x = d3.scalePoint(ts, [0, b.iw]).padding(0.1), y = y0.range([b.ih, 0]), yt = tv(y, nt(5));
      grid(b.g, y, b.iw, b.ih, "y", yt, C);
      otherGrid(C, b.g, ts.map(t => x(t)), b.iw, b.ih, "x");
      styleAxis(b.g.append("g").call(d3.axisLeft(y).tickValues(yt).tickFormat(fmtT).tickSizeOuter(0))).select(".domain").remove();
      pointBottomAxis(C, b.g, x, b.ih, ts, b.iw);
      if (!y.isLog && y.domain()[0] < 0) b.g.append("line").attr("x2", b.iw).attr("y1", y(0)).attr("y2", y(0)).attr("stroke", FAINT);
      refLine(C, b, y, "h");
      const line = d3.line().defined(p => p.v !== undefined && (!y.isLog || p.v > 0)).x(p => x(p.t)).y(p => y(p.v)).curve(curveOf(spec));
      const dotR = spec.markers === "off" ? 0 : spec.markers === "on" ? (ts.length > 40 ? 2 : 3.5) : ts.length > 16 ? 0 : 3.5;
      const lwid = isN(spec.lineWidth) ? Math.max(1, Math.min(6, spec.lineWidth)) : 2.6;
      series.forEach(e => {
        const w = strong(e.s) ? lwid : Math.max(1, lwid * 0.6);
        const dash = dashOf(spec, e.s);
        const path = b.g.append("path").attr("class", "qv-line").datum(e.pts).attr("fill", "none").attr("stroke", color(e.s)).attr("stroke-width", w)
          .attr("stroke-linejoin", "round").attr("stroke-linecap", dash === "1.5 4" ? "round" : null).attr("stroke-dasharray", dash).attr("d", line);
        path.append("title").text(e.s);
        if (C.anim && !dash) {
          const L = path.node().getTotalLength();
          path.attr("stroke-dasharray", `${L} ${L}`).attr("stroke-dashoffset", L).transition().duration(800).ease(d3.easeCubicOut)
            .attr("stroke-dashoffset", 0).on("end", function () { d3.select(this).attr("stroke-dasharray", null); });
        }
        if (dotR && strong(e.s)) dots(b.g, e.pts.filter(p => p.v !== undefined && (!y.isLog || p.v > 0)), spec.markerShape, dotR, p => x(p.t), p => y(p.v))
          .attr("fill", color(e.s)).attr("stroke", PAPER).attr("stroke-width", 1)
          .append("title").text(p => `${e.s}, ${p.t}: ${fmtFull(p.v, spec.unit)}`);
      });
      shade(C, b, x, "v");
      if (spec.valueLabels === "on" || (anyHl && spec.valueLabels !== "off")) {
        const strongS = series.filter(e => strong(e.s));
        const every = spec.valueLabels === "on" && strongS.length <= 3 ? Math.max(1, Math.ceil(ts.length * 34 / b.iw)) : 0;
        strongS.forEach(e => {
          const pts = e.pts.filter(p => p.v !== undefined);
          const pick = every ? pts.filter((p, i) => i % every === 0 || i === pts.length - 1) : pts.slice(-1);
          pick.forEach(p => b.g.append("text").attr("x", x(p.t)).attr("y", y(p.v) - 8).attr("text-anchor", "middle").attr("font-size", FS.min)
            .call(face, "valueLabels", 700).attr("fill", color(e.s)).attr("font-family", FONT).text(fmtShort(p.v, spec.unit)));
        });
      }
      axisTitles(C, b, spec.xLabel, spec.yLabel);
    },

    stacked_area(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.t !== "").map(r => ({...r, series: r.series || spec.yLabel || "Value"}));
      if (!rows.length) return empty(C);
      const ts = uniq(rows.map(r => r.t));
      const L = lump(rows, "series", 8);
      rows = L.rows;
      const names = L.names, get = pivot(rows, r => r.series, r => r.t);
      const table = ts.map(t => Object.fromEntries([["t", t], ...names.map(s => [s, get(s, t) || 0])]));
      const stack = d3.stack().keys(names).offset(d3.stackOffsetDiverging)(table);
      const color = palette(C, names, {rest: FAINT});
      C.legFlags = flagsOn(C, names);
      legend(C, names, color, null, sumBy(rows, r => r.series));
      const top = C.top + 4;
      const fmtT = v => fmtTick(v, spec.unit);
      const lo = d3.min(stack, s => d3.min(s, p => p[0])), hi = d3.max(stack, s => d3.max(s, p => p[1]));
      const y0 = vScale(C, Math.min(0, lo), hi * 1.05 || 1, {noLog: true}).range([300, 0]);
      const b = box(C, top, {left: leftFor(C, yTickW(y0, fmtT)), bottom: bottomFor(C, pointExtra(C, ts)), right: Math.max(PAD + 10, tw(ts.at(-1), FS.tick, fm("tickLabels")) / 2 + 6)});
      const x = d3.scalePoint(ts, [0, b.iw]), y = y0.range([b.ih, 0]), yt = tv(y, nt(5));
      grid(b.g, y, b.iw, b.ih, "y", yt, C);
      const area = d3.area().x(p => x(p.data.t)).y0(p => y(p[0])).y1(p => y(p[1])).curve(curveOf(spec));
      const paths = b.g.selectAll("path.area").data(stack).join("path").attr("class", "area").attr("fill", s => color(s.key))
        .attr("stroke", PAPER).attr("stroke-width", 1).attr("d", area);
      paths.append("title").text(s => s.key);
      if (C.anim) {
        const flat = d3.area().x(p => x(p.data.t)).y0(y(0)).y1(y(0)).curve(curveOf(spec));
        paths.attr("d", flat).transition().duration(700).ease(d3.easeCubicOut).attr("d", area);
      }
      otherGrid(C, b.g, ts.map(t => x(t)), b.iw, b.ih, "x");
      styleAxis(b.g.append("g").call(d3.axisLeft(y).tickValues(yt).tickFormat(fmtT).tickSizeOuter(0))).select(".domain").remove();
      pointBottomAxis(C, b.g, x, b.ih, ts, b.iw);
      refLine(C, b, y, "h");
      shade(C, b, x, "v");
      if (spec.valueLabels === "on") {
        const lastT = ts.at(-1);
        stack.forEach(sr => {
          const p = sr.find(q => q.data.t === lastT);
          if (p && y(p[0]) - y(p[1]) > FS.min + 2) b.g.append("text").attr("x", x(lastT) - 4).attr("y", (y(p[0]) + y(p[1])) / 2).attr("dy", "0.35em")
            .attr("text-anchor", "end").attr("font-size", FS.min).call(face, "valueLabels", 700).attr("fill", textOn(color(sr.key))).attr("font-family", FONT)
            .text(fmtShort(p[1] - p[0], spec.unit));
        });
      }
      axisTitles(C, b, spec.xLabel, spec.yLabel);
    },

    stacked_bar(C) {
      const {spec} = C;
      const pct = spec.stack !== "absolute";
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.v > 0 && r.cat !== "").map(r => ({...r, series: r.series || "Value"}));
      if (!rows.length) return empty(C);
      const LS = lump(rows, "series", 8);
      rows = LS.rows;
      const LC = lump(rows, "cat", 30);
      rows = LC.rows;
      if (LC.dropped) C.note = `Top 30 shown, ${LC.dropped} more in Other.`;
      const names = LS.names, get = pivot(rows, r => r.cat, r => r.series);
      let cats = LC.names;
      let table = cats.map(c => {
        const o = {cat: c}, tot = d3.sum(names, s => get(c, s) || 0) || 1;
        names.forEach(s => (o[s] = pct ? (get(c, s) || 0) / tot * 100 : (get(c, s) || 0)));
        o.__tot = tot;
        return o;
      });
      let stack = d3.stack().keys(names)(table);
      const color = palette(C, names, {rest: FAINT});
      const fl = flagsOn(C, cats);
      C.legFlags = flagsOn(C, names);
      legend(C, names, color, null, sumBy(rows, r => r.series));
      const top = C.top + 4;
      const unitFmt = v => (pct ? Math.round(v) + "%" : fmtShort(v, spec.unit));
      const valT = v => (pct ? v + "%" : fmtTick(v, spec.unit));
      const valTitle = pct && spec.yLabel ? "Share of " + spec.yLabel.replace(/^share of /i, "").replace(/^./, c => c.toLowerCase()) : spec.yLabel;
      const tip = p => `${p.data.cat}, ${p.key}: ${pct ? NF.format(".1f")(p[1] - p[0]) + "% (" + fmtFull((p[1] - p[0]) / 100 * p.data.__tot, spec.unit) + ")" : fmtFull(p[1] - p[0], spec.unit)}`;
      C.orient = spec.orientation === "vertical" ? "vertical" : "horizontal";
      if (C.orient === "vertical") {
        const tots = !pct && spec.valueLabels !== "off";
        const y0 = (pct ? d3.scaleLinear().domain([0, 100]) : vScale(C, 0, d3.max(table, o => o.__tot) || 1, {noLog: true})).range([300, 0]);
        const left = leftFor(C, yTickW(y0, valT));
        const step = (C.W - left - PAD - (C.leg && isSide(C.leg.pos) ? C.leg.w + 20 : 0)) / cats.length;
        const rot = rotatedBottom(C, cats, step, Math.min(170, H * 0.3));
        const fv = fl ? Math.min(flagBox(FS.tick).w, step - 4) : 0, flagW = fv >= 8 ? fv : 0;
        const b = box(C, top + (tots ? FS.label + 6 : 0), {left, bottom: bottomFor(C, rot + (flagW ? flagW * 0.75 + 4 : 0))});
        const x = d3.scaleBand(cats, [0, b.iw]).paddingInner(spec.barGap ?? Math.min(0.75, Math.max(0.24, 1 - 96 / Math.max(1, b.iw / cats.length)))).paddingOuter(0.14);
        const y = y0.range([b.ih, 0]), yt = tv(y, nt(5));
        grid(b.g, y, b.iw, b.ih, "y", yt, C);
        styleAxis(b.g.append("g").call(d3.axisLeft(y).tickValues(yt).tickFormat(valT).tickSizeOuter(0))).select(".domain").remove();
        const segs = b.g.selectAll("g.s").data(stack).join("g").attr("class", "s").attr("fill", s => color(s.key))
          .selectAll("rect").data(s => s.map(p => ((p.key = s.key), p))).join("rect").attr("x", p => x(p.data.cat)).attr("width", x.bandwidth())
          .attr("stroke", PAPER).attr("stroke-width", 1);
        segs.append("title").text(tip);
        (C.anim ? segs.attr("y", b.ih).attr("height", 0).transition().duration(700).ease(d3.easeCubicOut) : segs)
          .attr("y", p => y(p[1])).attr("height", p => Math.max(0, y(p[0]) - y(p[1])));
        shade(C, b, x, "v");
        if (spec.valueLabels !== "off") {
          b.g.selectAll("text.seg").data(stack.flatMap(s => s.filter(p => y(p[0]) - y(p[1]) >= FS.min + 2 && x.bandwidth() >= tw(unitFmt(p[1] - p[0]), FS.min, fm("valueLabels", 700)) + 4))).join("text").attr("class", "seg")
            .attr("x", p => x(p.data.cat) + x.bandwidth() / 2).attr("y", p => (y(p[0]) + y(p[1])) / 2).attr("dy", "0.35em").attr("text-anchor", "middle")
            .attr("font-size", FS.min).call(face, "valueLabels", 700).attr("fill", p => textOn(color(p.key))).attr("font-family", FONT).text(p => unitFmt(p[1] - p[0]));
        }
        if (tots && (spec.valueLabels === "on" || table.every(o => barLabelFits(fmtShort(o.__tot, spec.unit), x.step() - 2)))) {
          b.g.selectAll("text.tot").data(table).join("text").attr("class", "tot").attr("x", o => x(o.cat) + x.bandwidth() / 2).attr("y", o => y(o.__tot) - 6)
            .attr("text-anchor", "middle").attr("font-size", FS.label).call(face, "valueLabels").attr("fill", INK).attr("font-family", FONT).text(o => fmtShort(o.__tot, spec.unit));
        }
        bandBottomAxis(C, b.g, x, b.ih, cats, Math.min(170, H * 0.3), flagW);
        if (!pct) refLine(C, b, y, "h");
        axisTitles(C, b, spec.xLabel, valTitle);
        return;
      }
      const k = fitRows(C, cats.length, top + 40 + (spec.yLabel ? 30 : 0) + footH(C));
      if (k < cats.length) { cats = cats.slice(0, k); table = table.slice(0, k); stack = d3.stack().keys(names)(table); }
      grow(C, top + cats.length * 30 + 40 + (spec.yLabel ? 30 : 0) + footH(C));
      const lw = labelWidth(cats, Math.min(240, C.W * 0.3), FS.label, fl, dimOf(C, cats));
      const totW = pct ? 0 : d3.max(table, o => tw(fmtShort(o.__tot, spec.unit), FS.label, fm("valueLabels"))) + 12;
      const b = box(C, top, {left: PAD + (spec.xLabel ? 30 : 0) + lw + 10, bottom: 30 + (spec.yLabel ? 30 : 0) + (ang(C) ? 24 : 0), right: PAD + Math.max(10, totW)});
      const y = d3.scaleBand(cats, [0, b.ih]).padding(spec.barGap ?? 0.24);
      const x = pct ? d3.scaleLinear([0, 100], [0, b.iw]) : vScale(C, 0, d3.max(table, o => o.__tot) || 1, {noLog: true}).range([0, b.iw]);
      const xt = tv(x, nt(xTicks(b.iw, 5)));
      grid(b.g, x, b.iw, b.ih, "x", xt, C);
      const sax = styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).tickValues(xt).tickFormat(valT).tickSizeOuter(0)));
      if (ang(C)) sax.selectAll(".tick text").each(function () { tilt(d3.select(this), ang(C)); });
      const segs = b.g.selectAll("g.s").data(stack).join("g").attr("class", "s").attr("fill", s => color(s.key))
        .selectAll("rect").data(s => s.map(p => ((p.key = s.key), p))).join("rect").attr("y", p => y(p.data.cat)).attr("height", y.bandwidth())
        .attr("stroke", PAPER).attr("stroke-width", 1);
      segs.append("title").text(tip);
      (C.anim ? segs.attr("x", 0).attr("width", 0).transition().duration(700).ease(d3.easeCubicOut) : segs)
        .attr("x", p => x(p[0])).attr("width", p => Math.max(0, x(p[1]) - x(p[0])));
      shade(C, b, y, "h");
      if (spec.valueLabels !== "off" && y.bandwidth() >= FS.min + 2) {
        b.g.selectAll("text.seg").data(stack.flatMap(s => s.filter(p => x(p[1]) - x(p[0]) > tw(unitFmt(p[1] - p[0]), FS.min, fm("valueLabels", 700)) + 8))).join("text").attr("class", "seg")
          .attr("x", p => (x(p[0]) + x(p[1])) / 2).attr("y", p => y(p.data.cat) + y.bandwidth() / 2).attr("dy", "0.35em").attr("text-anchor", "middle")
          .attr("font-size", FS.min).call(face, "valueLabels", 700).attr("fill", p => textOn(color(p.key))).attr("font-family", FONT).text(p => unitFmt(p[1] - p[0]));
      }
      if (!pct && spec.valueLabels !== "off") {
        b.g.selectAll("text.tot").data(table).join("text").attr("class", "tot").attr("x", o => x(o.__tot) + 6).attr("y", o => y(o.cat) + y.bandwidth() / 2)
          .attr("dy", "0.35em").attr("font-size", FS.label).call(face, "valueLabels").attr("fill", INK).attr("font-family", FONT).text(o => fmtShort(o.__tot, spec.unit));
      }
      bandLeftAxis(C, b.g, y, cats, lw, FS.label, fl);
      if (!pct) refLine(C, b, x, "v");
      axisTitles(C, b, valTitle, spec.xLabel);
    },

    scatter(C) {
      const {spec} = C;
      let rows = C.rows.map(r => ({...r, v2: num(r.v2)})).filter(r => Number.isFinite(r.v) && Number.isFinite(r.v2));
      if (!rows.length) return empty(C);
      const hasSeries = rows.some(r => r.series);
      const byCountry = !hasSeries && countryShareOf(uniq(rows.map(r => r.cat).filter(Boolean))) >= 0.5;
      rows = rows.map(r => ({...r, series: r.series || "Items"}));
      const counts = new Map();
      rows.forEach(r => counts.set(r.series, (counts.get(r.series) || 0) + 1));
      const names0 = uniq(rows.map(r => r.series)), cp = capByTotal(names0, counts, 8);
      if (cp.other) { const k = new Set(cp.keep); rows = rows.map(r => (k.has(r.series) ? r : {...r, series: OTHER})); }
      const names = cp.other ? [...cp.keep, OTHER] : names0;
      const color = palette(C, names, {rest: FAINT});
      const hl = new Set((spec.highlight || []).map(String));
      const catHl = rows.some(e => hl.has(e.cat));
      const dotColor = e => {
        if (paint((spec.colors || {})[e.cat])) return paint(spec.colors[e.cat]);
        if (catHl) return hl.has(e.cat) ? FOCUS : isEU(e.cat) ? NAVY : FAINT;
        if (hasSeries) return color(e.series);
        if (hl.has(e.cat)) return FOCUS;
        if (isEU(e.cat)) return NAVY;
        return hl.size ? FAINT : (byCountry && hl.size ? GREY : GREEN);
      };
      if (hasSeries && !catHl) { C.legFlags = flagsOn(C, names); legend(C, names, color, null, counts); } else legend(C, [], null);
      const top = C.top + 4;
      const ext = (a, f) => { const [lo, hi] = d3.extent(a, f), p = (hi - lo) * 0.05 || Math.abs(hi) * 0.1 || 1; return [lo - p, hi + p]; };
      const fy = v => fmtTick(v, spec.unit);
      const [y2lo, y2hi] = d3.extent(rows, r => r.v2), [xlo, xhi] = d3.extent(rows, r => r.v);
      const y0 = vScale(C, ...ext(rows, r => r.v2), {dataMin: y2lo, dataMax: y2hi}).range([300, 0]);
      const x0 = vScale(C, ...ext(rows, r => r.v), {axis: "x", dataMin: xlo, dataMax: xhi});
      const b = box(C, top, {left: leftFor(C, yTickW(y0, tickShort)), bottom: bottomFor(C, ang(C) ? rotExtra(60, ang(C), 80) : 0), right: PAD + 10});
      const x = x0.range([0, b.iw]), y = y0.range([b.ih, 0]);
      if (x.isLog) rows = rows.filter(e => e.v > 0);
      if (y.isLog) rows = rows.filter(e => e.v2 > 0);
      const yt = tv(y, nt(5)), xt = tv(x, nt(xTicks(b.iw, 6)));
      grid(b.g, y, b.iw, b.ih, "y", yt, C);
      if (gridMode(C) === "auto" || gridMode(C) === "both") grid(b.g, x, b.iw, b.ih, "x", xt, C);
      const xax = styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).tickValues(xt).tickFormat(fy).tickSizeOuter(0)));
      if (ang(C)) xax.selectAll(".tick text").each(function () { tilt(d3.select(this), ang(C)); });
      styleAxis(b.g.append("g").call(d3.axisLeft(y).tickValues(yt).tickFormat(tickShort).tickSizeOuter(0))).select(".domain").remove();
      refLine(C, b, y, "h");
      if (spec.trendline && rows.length >= 3) {
        const tx = e => (x.isLog ? Math.log10(e.v) : e.v), ty = e => (y.isLog ? Math.log10(e.v2) : e.v2);
        const mxv = d3.mean(rows, tx), myv = d3.mean(rows, ty);
        const sxx = d3.sum(rows, e => (tx(e) - mxv) ** 2), sxy = d3.sum(rows, e => (tx(e) - mxv) * (ty(e) - myv));
        if (sxx > 0) {
          const k = sxy / sxx, c0 = myv - k * mxv;
          const [d0, d1] = x.domain();
          const pts = d3.range(0, 1.0001, 0.05).map(t => {
            const xv = x.isLog ? Math.pow(10, Math.log10(d0) + t * (Math.log10(d1) - Math.log10(d0))) : d0 + t * (d1 - d0);
            const yl = k * (x.isLog ? Math.log10(xv) : xv) + c0;
            return [x(xv), y(y.isLog ? Math.pow(10, yl) : yl)];
          }).filter(p => Number.isFinite(p[1]));
          b.g.append("path").attr("class", "qv-trend").attr("d", d3.line()(pts)).attr("fill", "none").attr("stroke", INK).attr("stroke-width", 1.6)
            .attr("stroke-dasharray", "6 4").append("title").text("Linear trend");
        }
      }
      const r = (rows.length > 600 ? 2.4 : rows.length > 150 ? 3.6 : 5.5) * ({small: 0.65, large: 1.45}[spec.pointSize] || 1);
      const order = rows.slice().sort((a, c) => (hl.has(a.cat) || isEU(a.cat)) - (hl.has(c.cat) || isEU(c.cat)));
      const pts = dots(b.g.append("g"), order, spec.markerShape, r, e => x(e.v), e => y(e.v2))
        .attr("fill", dotColor).attr("fill-opacity", 0.9).attr("stroke", PAPER).attr("stroke-width", rows.length > 600 ? 0 : 1);
      pts.append("title").text(e => `${e.cat ? e.cat + ": " : ""}${hasSeries ? e.series + ", " : ""}${fmtFull(e.v, spec.unit)}, ${full(e.v2)}`);
      if (!symbolOf(spec.markerShape, r)) (C.anim ? pts.attr("r", 0).transition().duration(500).delay((e, i) => Math.min(400, i * 4)) : pts).attr("r", r);
      const named = rows.filter(e => e.cat);
      const labelAll = named.length && named.length <= 24 && spec.valueLabels !== "off";
      const toLabel = named.filter(e => labelAll || hl.has(e.cat) || spec.valueLabels === "on");
      const placed = [], dm = dimOf(C, named.map(e => e.cat));
      toLabel.sort((a, c) => hl.has(c.cat) - hl.has(a.cat)).forEach(e => {
        const fs = sizeAt(dm, e.cat, FS.min), w = tw(e.cat, fs, fm("valueLabels", 400, hl.has(e.cat))), cx = x(e.v), cy = y(e.v2);
        const left = cx + r + 4 + w > b.iw;
        const bx = left ? cx - r - 4 - w : cx + r + 4, by = cy - 7;
        if (placed.some(p => bx < p.x + p.w && bx + w > p.x && by < p.y + 14 && by + 14 > p.y)) return;
        placed.push({x: bx, y: by, w});
        b.g.append("text").attr("x", bx).attr("y", cy).attr("dy", "0.35em").attr("font-size", fs).attr("font-family", FONT)
          .call(face, "valueLabels", 400, hl.has(e.cat)).attr("fill", hl.has(e.cat) ? FOCUS : INK).text(e.cat).style("pointer-events", "none");
      });
      axisTitles(C, b, spec.xLabel, spec.yLabel);
    },

    histogram(C) {
      const {spec} = C;
      let vals = C.rows.map(r => r.v).filter(Number.isFinite);
      if (!vals.length) return empty(C);
      const [lo, hi] = d3.extent(vals);
      const x0 = vScale(C, lo === hi ? lo - 1 : lo, lo === hi ? hi + 1 : hi, {axis: "x", noLog: true});
      const [dlo, dhi] = x0.domain();
      vals = vals.filter(v => v >= dlo && v <= dhi);
      const nb = Math.max(6, Math.min(30, Math.ceil(Math.log2(Math.max(2, vals.length)) + 1) * 2));
      const bins = d3.bin().domain(x0.domain()).thresholds(x0.ticks(nb))(vals);
      legend(C, [], null);
      const top = C.top + 4;
      const y0 = vScale(C, 0, (d3.max(bins, e => e.length) || 1) * 1.1, {noLog: true}).range([300, 0]);
      const b = box(C, top, {left: leftFor(C, yTickW(y0, tickShort)), bottom: bottomFor(C, ang(C) ? rotExtra(60, ang(C), 80) : 0), right: PAD + 10});
      const x = x0.range([0, b.iw]), y = y0.range([b.ih, 0]);
      if (gridMode(C) !== "off") b.g.append("g").attr("class", "grid-lines").selectAll("line").data(y.ticks(nt(5)).filter(Number.isInteger)).join("line").attr("x2", b.iw)
        .attr("y1", y).attr("y2", y).attr("stroke", GRID).attr("stroke-dasharray", DASH);
      otherGrid(C, b.g, x.ticks(nt(xTicks(b.iw, 10))).map(x), b.iw, b.ih, "x");
      const gap = e => (isN(spec.barGap) ? (x(e.x1) - x(e.x0)) * spec.barGap : 1);
      const bars = b.g.selectAll("rect.bar").data(bins).join("rect").attr("class", "bar").attr("x", e => x(e.x0) + gap(e) / 2).attr("width", e => Math.max(0, x(e.x1) - x(e.x0) - gap(e)))
        .attr("fill", (spec.colors && paint(Object.values(spec.colors)[0])) || GREEN).attr("y", y(0)).attr("height", 0);
      bars.append("title").text(e => `${fmtFull(e.x0, spec.unit)} to ${fmtFull(e.x1, spec.unit)}: ${e.length}`);
      (C.anim ? bars.transition().duration(700).ease(d3.easeCubicOut) : bars).attr("y", e => y(e.length)).attr("height", e => y(0) - y(e.length));
      const hax = styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).ticks(nt(xTicks(b.iw, 10))).tickFormat(v => fmtTick(v, spec.unit)).tickSizeOuter(0)));
      if (ang(C)) hax.selectAll(".tick text").each(function () { tilt(d3.select(this), ang(C)); });
      styleAxis(b.g.append("g").call(d3.axisLeft(y).tickValues(y.ticks(nt(5)).filter(Number.isInteger)).tickFormat(tickShort).tickSizeOuter(0))).select(".domain").remove();
      if (spec.valueLabels === "on") b.g.selectAll("text.hl").data(bins.filter(e => e.length)).join("text").attr("class", "hl").attr("x", e => (x(e.x0) + x(e.x1)) / 2)
        .attr("y", e => y(e.length) - 5).attr("text-anchor", "middle").attr("font-size", FS.min).call(face, "valueLabels").attr("fill", INK).attr("font-family", FONT).text(e => e.length);
      axisTitles(C, b, spec.xLabel, spec.yLabel || "Count");
    },

    map(C) {
      const {spec} = C;
      const d = catValues(C.rows, 100000, false);
      if (!d.length) return empty(C, "Maps need a place column and numbers");
      let geo = spec.geo && spec.geo !== "world" ? spec.geo : null;
      const names = d.map(e => e.cat), share = countryShareOf(names);
      if (!geo && spec.geo !== "world" && share < 1) {
        const idx = geoJSON(INDEX_URL(), C.svgEl);
        if (idx === undefined) return empty(C, "Loading map…");
        const rm = regionMatch(names);
        if (rm && rm.n > share * names.length) geo = rm.a3;
      }
      let features, idOf, mercator = false;
      if (geo) {
        const topo = geoJSON(BASE + "geo/regions/" + geo + ".json", C.svgEl);
        if (topo === undefined) return empty(C, "Loading map…");
        if (!topo) return empty(C, "No region outlines for this country");
        if (!window.topojson) { geoWaiting.add(C.svgEl); loadGeo(); return empty(C, "Loading map…"); }
        let best = null;
        for (const key of Object.keys(topo.objects)) {
          const fs = topojson.feature(topo, topo.objects[key]).features;
          fs.forEach((f, i) => f.id = key + i);
          const byAlias = new Map();
          fs.forEach(f => (f.properties.aliases || []).concat(normRegion(f.properties.name)).forEach(a => byAlias.set(a, f.id)));
          const n = d.filter(e => byAlias.has(normRegion(e.cat))).length;
          if (!best || n > best.n) best = {fs, byAlias, n};
        }
        features = best.fs;
        idOf = n => best.byAlias.get(normRegion(n)) || null;
        mercator = true;
      } else {
        if (!geoFeatures) {
          geoWaiting.add(C.svgEl);
          loadGeo().catch(() => empty(C, "Could not load the map outlines"));
          return empty(C, "Loading map…");
        }
        features = geoFeatures; idOf = countryId;
      }
      C.svgEl.__qv.geoUsed = geo || "world";
      const byId = new Map(), missing = [];
      d.forEach(e => { const id = idOf(e.cat); if (id) byId.set(id, {cat: e.cat, v: (byId.get(id)?.v || 0) + e.v}); else if (!isEU(e.cat)) missing.push(e.cat); });
      if (!byId.size) return empty(C, geo ? "No region names matched" : "No country or region names found in this data");
      if (missing.length) C.note = `Not on the map: ${missing.slice(0, 4).join(", ")}${missing.length > 4 ? ` and ${missing.length - 4} more` : ""}.`;
      const vs = [...byId.values()].map(e => e.v);
      const [mn, mx] = d3.extent(vs);
      const diverging = mn < 0 && mx > 0;
      let breaks = d3.ticks(mn, mx, 5).filter(t => t > mn && t < mx);
      if (breaks.length > 5) breaks = breaks.filter((t, i) => i % 2 === 0);
      if (!breaks.length) breaks = mx > mn ? [(mn + mx) / 2] : [];
      const n = breaks.length + 1;
      const colors = diverging ? d3.quantize(d3.interpolateRgbBasis(DIV), n) : n === SEQ.length ? SEQ.slice() : n === 1 ? [SEQ[3]] : d3.quantize(d3.interpolateRgbBasis(SEQ.slice(1)), n);
      const classOf = v => d3.bisectRight(breaks, v);
      legend(C, [], null);
      const fmtB = v => fmtTick(v, spec.unit);
      const labels = colors.map((c, i) => i === 0 ? `< ${fmtB(breaks[0])}` : i === n - 1 ? `${fmtB(breaks[n - 2])}+` : `${fmtB(breaks[i - 1])}–${fmtB(breaks[i])}`);
      if (n === 1) labels[0] = fmtB(mn);
      const K = keyMeasure(C, {type: "class", labels, colors, edges: breaks.map(fmtB), title: spec.legendTitle || spec.yLabel || spec.xLabel || ""});
      const km = keyMargins(K);
      const top0 = C.top + 4, top = top0 + km.top;
      const b = box(C, top, {left: PAD + km.left, bottom: km.bottom + 4, right: PAD + km.right});
      let hit = geo ? features : features.filter(f => byId.has(f.id));
      if (geo && hit.length > 3) {
        const cs = hit.map(f => d3.geoCentroid(f)), mx0 = d3.median(cs, c => c[0]), my0 = d3.median(cs, c => c[1]);
        const near = hit.filter((f, i) => Math.hypot(cs[i][0] - mx0, cs[i][1] - my0) < 25);
        if (near.length >= hit.length * 0.6) hit = near;
      }
      const europe = !geo && hit.length && hit.every(f => { const c = d3.geoCentroid(mainland(f)); return c[0] > -32 && c[0] < 45 && c[1] > 33 && c[1] < 72; });
      const base = geo === "USA" ? d3.geoAlbersUsa() : mercator || europe ? d3.geoMercator() : d3.geoNaturalEarth1();
      const proj = base.fitExtent([[4, 4], [b.iw - 4, b.ih - 4]], {type: "FeatureCollection", features: geo === "USA" ? features : hit.map(mainland)});
      const path = d3.geoPath(proj);
      const cid = "qvclip" + Math.random().toString(36).slice(2, 8);
      C.root.append("defs").append("clipPath").attr("id", cid).append("rect").attr("width", b.iw).attr("height", b.ih);
      if (WATER) b.g.append("path").attr("class", "qv-water").attr("clip-path", `url(#${cid})`).attr("fill", WATER)
        .attr("d", geo === "USA" || mercator || europe ? `M0,0H${b.iw}V${b.ih}H0Z` : path({type: "Sphere"}));
      const g = b.g.append("g").attr("clip-path", `url(#${cid})`);
      const shapes = g.selectAll("path").data(features.filter(f => f.id !== "010" || byId.has(f.id))).join("path")
        .attr("class", f => (byId.has(f.id) ? "qv-shape" : null)).attr("d", path).attr("stroke", f => (byId.has(f.id) ? PAPER : RULE)).attr("stroke-width", f => (byId.has(f.id) ? 0.7 : 0.5))
        .attr("fill", f => (byId.has(f.id) ? colors[classOf(byId.get(f.id).v)] : geo ? NODATA : CONTEXT));
      shapes.filter(f => byId.has(f.id)).append("title").text(f => { const e = byId.get(f.id); return `${e.cat}: ${fmtFull(e.v, spec.unit)}`; });
      const hl = new Set((spec.highlight || []).map(String));
      if (hl.size) shapes.filter(f => byId.has(f.id) && hl.has(byId.get(f.id).cat)).raise().attr("stroke", INK).attr("stroke-width", 1.2);
      if (C.anim) shapes.filter(f => byId.has(f.id)).attr("opacity", 0).transition().duration(500).delay((f, i) => i * 12).attr("opacity", 1);
      drawKey(C, K, b, top0);
    },

    heatmap(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.cat !== "" && str(r.series) !== "");
      if (!rows.length) return empty(C);
      let cats = uniq(rows.map(r => r.cat)), cols = uniq(rows.map(r => r.series));
      const note = [];
      if (cats.length > 30) { note.push(`first 30 of ${cats.length} rows`); cats = cats.slice(0, 30); }
      if (cols.length > 36) { note.push(`first 36 of ${cols.length} columns`); cols = cols.slice(0, 36); }
      if (note.length) C.note = "Showing " + note.join(", ") + ".";
      const get = pivot(rows, r => r.cat, r => r.series);
      const cells = cats.flatMap(c => cols.map(s => ({c, s, v: get(c, s)})));
      const vs = cells.map(e => e.v).filter(v => v !== undefined);
      const [mn, mx] = d3.extent(vs);
      const diverging = mn < 0 && mx > 0;
      let scale, tOf;
      if (diverging) {
        const m = Math.max(-mn, mx);
        tOf = v => (v + m) / (2 * m);
        const ramp = d3.interpolateRgbBasis([DIVLO, MID, DIVHI]);
        scale = v => ramp(tOf(v));
      } else {
        const ramp = d3.interpolateRgbBasis(HEAT);
        tOf = v => (mx === mn ? 0.6 : (v - mn) / (mx - mn));
        scale = v => ramp(0.06 + 0.94 * tOf(v));
      }
      legend(C, [], null);
      const fmtK = v => fmtShort(v, spec.unit);
      const K = keyMeasure(C, {type: "grad", title: spec.legendTitle || spec.yLabel || "",
        labels: [fmtK(mn), fmtK(mx), fmtK((mn + mx) / 2)],
        stops: d3.range(0, 1.0001, 0.05).map(t => [t, scale(mn + t * (mx - mn))]),
        ticks: keyPlace(C).dir === "vertical" && mx > mn ? [[0, fmtK(mn)], [0.5, fmtK((mn + mx) / 2)], [1, fmtK(mx)]] : [[0, fmtK(mn)], [1, fmtK(mx)]]});
      const km = keyMargins(K);
      const top0 = C.top + 4, top = top0 + km.top;
      const colW = d3.max(cols, s => tw(s, FS.tick, fm("tickLabels"))) || 0;
      const gapH = isN(spec.barGap) ? Math.min(0.5, spec.barGap) : 0.04;
      const legH = km.bottom, xT = spec.xLabel ? 30 : 0;
      const a = ang(C), angFor = w => a ?? (w >= 28 ? 35 : w >= 19 ? 60 : 90), rotMax = Math.round(Math.max(110, Math.min(170, ((C.space || H) - top - cats.length * 24) * 0.35)));
      const fs = FS.min;
      const numStep = spec.valueLabels === "off" ? 0 : Math.max(fs + 4, (d3.max(cells, e => e.v === undefined ? 0 : tw(short(e.v), fs, fm("valueLabels"))) || 0) + 6) / (1 - gapH);
      const lwCap = Math.min(220, Math.max(C.W * 0.28, C.W - 10 - 2 * PAD - km.left - km.right - (cols.length + gapH) * Math.max(fs + 4, numStep)));
      const fl = flagsOn(C, cats);
      const lw0 = labelWidth(cats, lwCap, FS.tick, fl, dimOf(C, cats));
      const estX0 = Math.min((C.W - lw0 - 10 - 2 * PAD - km.left - km.right) / (cols.length + gapH), ROW_MIN);
      const rot0 = a != null ? a > 0 : colW > estX0 - 4;
      const kept = fitRows(C, cats.length, top + 24 + xT + legH + footH(C) + (rot0 ? rotExtra(colW, angFor(estX0), rotMax) - 2 : 0));
      if (kept < cats.length) { cats = cats.slice(0, kept); cells.splice(0, cells.length, ...cells.filter(e => cats.includes(e.c))); }
      grow(C, top + cats.length * 24 + 70 + km.bottom + footH(C));
      const lw = labelWidth(cats, lwCap, FS.tick, fl, dimOf(C, cats));
      const iw0 = C.W - lw - 10 - 2 * PAD - km.left - km.right, ih0 = H - footH(C) - top - 24 - xT - legH;
      const wStep = iw0 / (cols.length + gapH);
      const free = !C.fitMode && !isN(spec.height);
      const room = (Math.max(H, SPACE_MAX) - footH(C) - top - 24 - xT - legH) / (cats.length + gapH);
      const est = free ? Math.min(wStep, Math.max(numStep, Math.min(72, room))) : Math.min(wStep, ih0 / (cats.length + gapH));
      const rot = a != null ? a > 0 : colW > est - 4;
      const deg = angFor(est);
      const bottom = 24 + (rot ? rotExtra(colW, deg, rotMax) - 2 : 0) + xT + legH;
      if (free) grow(C, Math.min(Math.max(H, 900), Math.ceil(top + est * (cats.length + gapH) + bottom + footH(C))));
      const b = box(C, top, {left: PAD + km.left + lw + 10, bottom, right: PAD + km.right});
      const step = Math.min(b.iw / (cols.length + gapH), b.ih / (cats.length + gapH));
      const gw = step * (cols.length + gapH), gh = step * (cats.length + gapH);
      const need = Math.max(gh, K && K.side ? K.h - b.bottom + 8 : 0);
      if (need < b.ih - 0.5 && !isN(spec.height)) {
        const cut = Math.floor(b.ih - need);
        H -= cut; C.plotBottom -= cut; b.ih -= cut; C.pb.ih = b.ih;
      }
      const lead = rot ? Math.cos(rad(deg)) * Math.min(rotMax, tw(cols[0], FS.tick, fm("tickLabels"))) - step / 2 - b.left + 4 : 0;
      const dx = Math.min(Math.max(0, b.iw - gw), Math.max((b.iw - gw) / 2, lead));
      b.left += dx; b.iw = gw;
      b.g.attr("transform", `translate(${b.left},${b.top})`);
      const x = d3.scaleBand(cols, [0, gw]).padding(gapH), y = d3.scaleBand(cats, [0, gh]).padding(gapH);
      const rects = b.g.selectAll("rect.cell").data(cells).join("rect").attr("class", "cell").attr("x", e => x(e.s)).attr("y", e => y(e.c))
        .attr("width", x.bandwidth()).attr("height", y.bandwidth()).attr("fill", e => (e.v === undefined ? NODATA : scale(e.v)));
      rects.append("title").text(e => `${e.c}, ${e.s}: ${e.v === undefined ? "no data" : fmtFull(e.v, spec.unit)}`);
      if (C.anim) rects.attr("opacity", 0).transition().duration(500).delay((e, i) => (i % cols.length) * 12).attr("opacity", 1);
      if (spec.valueLabels !== "off" && y.bandwidth() >= fs + 4 && cells.every(e => e.v === undefined || tw(short(e.v), fs, fm("valueLabels")) + 6 <= x.bandwidth())) {
        b.g.selectAll("text.cv").data(cells.filter(e => e.v !== undefined)).join("text").attr("class", "cv")
          .attr("x", e => x(e.s) + x.bandwidth() / 2).attr("y", e => y(e.c) + y.bandwidth() / 2).attr("dy", "0.35em").attr("text-anchor", "middle")
          .attr("font-size", fs).call(face, "valueLabels").attr("font-family", FONT)
          .attr("fill", e => { const L = hexLum(d3.color(scale(e.v)).formatHex()); return 1.05 / (L + 0.05) > (L + 0.05) / (hexLum(T.ink) + 0.05) ? WHITE : T.ink; }).text(e => short(e.v)).style("pointer-events", "none");
      }
      bandLeftAxis(C, b.g, y, cats, lw, FS.tick, fl);
      const ax = b.g.append("g").attr("transform", `translate(0,${gh})`).call(d3.axisBottom(x).tickSize(0).tickPadding(6));
      styleAxis(ax).select(".domain").remove();
      ax.selectAll(".tick text").each(function (dd) {
        const t = d3.select(this).text(clip(dd, rot ? rotMax : x.bandwidth(), FS.tick, fm("tickLabels")));
        t.append("title").text(dd);
        if (rot) tilt(t, deg);
      });
      mark("axisTitles");
      if (spec.xLabel) C.root.append("text").attr("class", "qv-axis-title").attr("x", b.left + b.iw / 2).attr("y", C.plotBottom - legH - 6).attr("text-anchor", "middle").attr("font-size", FS.axis)
        .call(face, "axisTitle", 700).attr("fill", INK).attr("font-family", FONT).text(clip(spec.xLabel, Math.max(b.iw, 2 * Math.min(b.left + b.iw / 2 - PAD, C.W - PAD - b.left - b.iw / 2)), FS.axis, fm("axisTitle", 700)));
      drawKey(C, K, {...b, ih: gh, grid: true, lw}, top0);
    },

    treemap(C) {
      const {spec} = C;
      const d = catValues(C.rows, 16, true);
      if (!d.length) return empty(C, "Treemaps need positive numbers");
      if (d.some(e => e.cat === OTHER && e.n)) C.note = `Top 16 shown, ${d.at(-1).n} more in Other.`;
      const root = d3.hierarchy({children: d}).sum(e => e.v || 0).sort((a, b2) => (a.data.cat === OTHER) - (b2.data.cat === OTHER) || b2.value - a.value);
      const leafNames = root.leaves().map(l => l.data.cat);
      const color = palette(C, leafNames, T.tile ? {rest: RULE, single: T.primary} : {rest: RULE});
      legend(C, spec.legend === "on" ? leafNames : [], color, null, new Map(d.map(e => [e.cat, e.v])));
      const top = C.top + 4;
      const b = box(C, top, {left: PAD, bottom: 8, right: PAD});
      const o = T.tile ? 2 : 0;
      (o ? d3.treemap().size([Math.floor(b.iw) + 2 * o, Math.floor(b.ih) + 2 * o]).padding(o) : d3.treemap().size([b.iw, b.ih]).paddingInner(2)).round(true)(root);
      const total = root.value;
      const n = b.g.selectAll("g.leaf").data(root.leaves()).join("g").attr("class", "leaf").attr("transform", e => `translate(${e.x0 - o},${e.y0 - o})`);
      n.append("title").text(e => `${e.data.cat}: ${fmtFull(e.value, spec.unit)} (${NF.format(".1%")(e.value / total)})`);
      n.append("rect").attr("width", e => e.x1 - e.x0).attr("height", e => e.y1 - e.y0).attr("fill", e => color(e.data.cat));
      if (T.tile) n.each(function (e) { tileLabel(C, d3.select(this), e, color(e.data.cat)); });
      else n.each(function (e) {
        const w = e.x1 - e.x0, h = e.y1 - e.y0, g = d3.select(this);
        const fs = Math.max(FS.min, Math.min(24, Math.sqrt(w * h) / 9));
        const name = String(e.data.cat);
        const nf = fm("valueLabels", 700);
        if (w < 40 || h < fs + 12 || tw(name, fs, nf) > w - 14) {
          const fs2 = FS.min;
          if (w < 40 || h < fs2 + 12 || tw(name, fs2, nf) > w - 14) {
            const only = fmtShort(e.value, spec.unit);
            if (spec.valueLabels === "on" && h >= fs2 + 6 && tw(only, fs2, nf) <= w - 6) g.append("text").attr("class", "qv-val").attr("x", w / 2).attr("y", h / 2).attr("dy", "0.35em")
              .attr("text-anchor", "middle").attr("font-size", fs2).call(face, "valueLabels", 700).attr("fill", textOn(color(e.data.cat))).attr("font-family", FONT).text(only);
            return;
          }
          return draw(fs2);
        }
        draw(fs);
        function draw(size) {
          const ink = textOn(color(e.data.cat));
          g.append("text").attr("x", 7).attr("y", 6 + size).attr("font-size", size).call(face, "valueLabels", 700).attr("fill", ink).attr("font-family", FONT).text(name);
          const val = spec.unit === "%" ? fmtShort(e.value, "%") : `${fmtShort(e.value, spec.unit)} / ${NF.format(".0%")(e.value / total)}`;
          const vs = Math.max(FS.min, size * 0.8);
          if (spec.valueLabels !== "off" && h > size + vs + 18 && tw(val, vs, fm("valueLabels")) <= w - 14) g.append("text").attr("x", 7).attr("y", 10 + size + vs * 1.15).attr("font-size", vs).call(face, "valueLabels")
            .attr("fill", ink).attr("font-family", FONT).text(val);
        }
      });
      if (C.anim) n.attr("opacity", 0).transition().duration(450).delay((e, i) => i * 30).attr("opacity", 1);
    },

    donut(C) {
      const {spec} = C;
      const d = catValues(C.rows, 6, true);
      if (!d.length) return empty(C, "Donuts need positive numbers");
      if (d.some(e => e.cat === OTHER && e.n)) C.note = `Top 6 shown, ${d.at(-1).n} more in Other.`;
      legend(C, [], null);
      const top = C.top + 4;
      if (C.W < 560) grow(C, top + C.W * 0.62 + Math.ceil(d.length / 2) * 40 + 30 + footH(C));
      const b = box(C, top, {left: PAD, bottom: 8, right: PAD});
      const total = d3.sum(d, e => e.v), color = palette(C, d.map(e => e.cat), {rest: RULE});
      const showLeg = spec.legend !== "off", lp = legPos(C, "right");
      const below = showLeg && (b.iw < 520 || lp === "bottom" || lp === "top");
      const listH = Math.ceil(d.length / 2) * 40;
      const rad = !showLeg ? Math.min(b.ih / 2, b.iw / 2) - 4 : below ? Math.max(40, Math.min((b.ih - listH - 24) / 2, b.iw * 0.32)) : Math.min(b.ih / 2, b.iw * 0.28);
      const flip = showLeg && !below && lp === "left";
      const cx = !showLeg || below ? b.iw / 2 : flip ? b.iw - Math.min(b.iw * 0.32, rad + 30) : Math.min(b.iw * 0.32, rad + 30);
      const cy = !showLeg ? b.ih / 2 : below ? (lp === "top" ? listH + 20 + rad : rad + 4) : b.ih / 2;
      const narrow = below;
      const hole = isN(spec.donutHole) ? Math.max(0, Math.min(0.8, spec.donutHole)) : 0.58;
      const arcs = d3.pie().value(e => e.v).sort(null).padAngle(hole ? 0.006 : 0.004)(d);
      const arc = d3.arc().innerRadius(rad * hole).outerRadius(rad);
      const c = b.g.append("g").attr("transform", `translate(${cx},${cy})`);
      const paths = c.selectAll("path").data(arcs).join("path").attr("class", "qv-arc").attr("fill", a => color(a.data.cat)).attr("d", arc).attr("stroke", PAPER).attr("stroke-width", 1);
      paths.append("title").text(a => `${a.data.cat}: ${fmtFull(a.data.v, spec.unit)} (${NF.format(".1%")(a.data.v / total)})`);
      if (C.anim) paths.transition().duration(700).ease(d3.easeCubicOut).attrTween("d", a => { const i = d3.interpolate({startAngle: a.startAngle, endAngle: a.startAngle}, a); return t => arc(i(t)); });
      const pct = spec.unit === "%", whole = pct && Math.abs(total - 100) < 0.6;
      if ((!pct || whole) && hole >= 0.45) {
        c.append("text").attr("text-anchor", "middle").attr("dy", "0.1em").attr("font-family", FONT).attr("font-size", Math.max(FS.big, rad * 0.24))
          .attr("font-weight", 700).attr("fill", INK).text(whole ? "100%" : fmtFull(total, spec.unit));
        c.append("text").attr("text-anchor", "middle").attr("dy", "1.9em").attr("font-size", FS.tick).attr("fill", MUTED)
          .attr("font-family", FONT).text(clip(spec.yLabel ? "Total " + spec.yLabel.replace(/^./, s => s.toLowerCase()) : "Total", rad * 1.1, FS.tick));
      }
      const share = e => (pct ? fmtShort(e.v, "%") : NF.format(".1%")(e.v / total));
      const ringIn = rad * Math.max(hole, 0.5), ringMid = (ringIn + rad) / 2;
      const fitsIn = (a, s) => (a.endAngle - a.startAngle) * ringMid >= tw(s, FS.min, fm("valueLabels", 700)) + 8 && rad - ringIn >= FS.min + 4;
      const inLabel = (a, s, dy) => {
        const [px, py] = d3.arc().innerRadius(ringIn).outerRadius(rad).centroid(a);
        c.append("text").attr("class", "qv-pct").attr("x", px).attr("y", py).attr("dy", dy).attr("text-anchor", "middle").attr("font-size", FS.min).call(face, "valueLabels", 700)
          .attr("fill", textOn(color(a.data.cat))).attr("font-family", FONT).text(s);
      };
      if (!showLeg) {
        if (spec.valueLabels !== "off") arcs.forEach(a => {
          const big = a.endAngle - a.startAngle > 0.3, name = clip(a.data.cat, rad * 0.6, FS.min, fm("valueLabels", 700)), s = share(a.data);
          if (spec.valueLabels === "on" && big && rad - ringIn >= 2 * FS.min + 8) { inLabel(a, name, "-0.25em"); inLabel(a, s, "1.05em"); }
          else if (big) inLabel(a, name, "0.35em");
          else if (spec.valueLabels === "on" && fitsIn(a, s)) inLabel(a, s, "0.35em");
        });
        return;
      }
      if (spec.valueLabels === "on") arcs.filter(a => fitsIn(a, share(a.data))).forEach(a => inLabel(a, share(a.data), "0.35em"));
      const sorted = sortLegend(C, d.map(e => ({...e, name: e.cat})), new Map(d.map(e => [e.cat, e.v])));
      const lx = narrow ? 0 : flip ? 0 : cx + rad + 40, rowH = narrow ? 40 : Math.min(48, b.ih / d.length);
      const lwAvail = narrow ? b.iw / 2 - 8 : flip ? cx - rad - 50 : b.iw - lx - 10;
      const ly = narrow ? (lp === "top" ? 0 : 2 * rad + 20) : cy - (rowH * d.length) / 2;
      const lg = b.g.append("g").attr("transform", `translate(${lx},${ly})`);
      sorted.forEach((e, i) => {
        const it = lg.append("g").attr("transform", narrow ? `translate(${(i % 2) * b.iw / 2},${Math.floor(i / 2) * rowH})` : `translate(0,${i * rowH})`);
        it.append("title").text(e.cat);
        it.append("rect").attr("y", 3).attr("width", 14).attr("height", 14).attr("fill", color(e.cat));
        it.append("text").attr("x", 22).attr("y", 15).attr("font-size", FS.label).call(face, "legend", 400, isHl(C, e.cat)).attr("fill", INK).attr("font-family", FONT)
          .text(clip(e.cat, lwAvail - 22, FS.label, fm("legend", 400, isHl(C, e.cat))));
        if (spec.valueLabels !== "off") it.append("text").attr("x", 22).attr("y", 33).attr("font-size", FS.tick).call(face, "legend").attr("fill", MUTED).attr("font-family", FONT)
          .text(pct ? fmtShort(e.v, "%") : `${NF.format(".1%")(e.v / total)} / ${fmtShort(e.v, spec.unit)}`);
      });
    },

    sankey(C) {
      const {spec} = C;
      if (!d3.sankey) return empty(C, "Sankey library did not load");
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.v > 0 && r.cat !== "" && str(r.series) !== "");
      if (!rows.length) return empty(C);
      rows = lump(rows, "cat", 12).rows;
      rows = lump(rows, "series", 12).rows;
      const agg = pivot(rows, r => r.cat, r => r.series);
      const pairs = uniq(rows.map(r => r.cat + "\u0000" + r.series)).map(k => { const [s, t] = k.split("\u0000"); return {s, t, v: agg(s, t)}; });
      legend(C, [], null);
      const top = C.top + 8;
      const srcNames = uniq(pairs.map(p => p.s)), dstNames = uniq(pairs.map(p => p.t));
      grow(C, top + Math.max(srcNames.length, dstNames.length) * 30 + 30 + footH(C));
      const showV = spec.valueLabels === "on";
      const valW = side0 => (showV ? d3.max([...sumBy(pairs.map(p => ({k: p[side0], v: p.v})), r => r.k).values()], v => tw(fmtShort(v, spec.unit), FS.tick, fm("valueLabels"))) + 8 : 0);
      const vwL = valW("s"), vwR = valW("t");
      const lwL = labelWidth(srcNames, Math.min(190, C.W * 0.27)) + 10 + vwL, lwR = labelWidth(dstNames, Math.min(190, C.W * 0.27)) + 10 + vwR;
      const b = box(C, top, {left: PAD + lwL, bottom: 10, right: PAD + lwR});
      function layout(shared) {
        const id = (side, n) => (shared ? n : side + n);
        const names = uniq(pairs.flatMap(p => [id("s:", p.s), id("t:", p.t)]));
        const idx = new Map(names.map((n, i) => [n, i]));
        const links = pairs.filter(p => !shared || p.s !== p.t).map(p => ({source: idx.get(id("s:", p.s)), target: idx.get(id("t:", p.t)), value: p.v}));
        const nodes = names.map(n => ({id: n, name: shared ? n : n.slice(2)}));
        const n = Math.max(srcNames.length, dstNames.length);
        return d3.sankey().nodeWidth(14).nodePadding(Math.max(6, Math.min(16, b.ih / n / 3))).nodeSort(null)
          .extent([[0, 0], [b.iw, b.ih]])({nodes, links});
      }
      const overlap = srcNames.some(n => dstNames.includes(n));
      let sk;
      if (overlap) { try { sk = layout(true); } catch (e) { sk = null; } }
      if (!sk) sk = layout(false);
      const color = palette(C, sk.nodes.filter(n => n.sourceLinks.length).map(n => n.name), {rest: FAINT});
      const nodeColor = n => (n.sourceLinks.length ? color(n.name) : (paint((C.spec.colors || {})[n.name]) ? paint(C.spec.colors[n.name]) : isHl(C, n.name) ? FOCUS : GREY));
      const links = b.g.append("g").attr("fill", "none").selectAll("path").data(sk.links).join("path").attr("d", d3.sankeyLinkHorizontal())
        .attr("stroke", l => color(l.source.name)).attr("stroke-opacity", 0.35).attr("stroke-width", l => Math.max(1, l.width));
      links.append("title").text(l => `${l.source.name} to ${l.target.name}: ${fmtFull(l.value, spec.unit)}`);
      if (C.anim) links.attr("stroke-opacity", 0).transition().duration(600).delay(150).attr("stroke-opacity", 0.35);
      const nodes = b.g.selectAll("rect.node").data(sk.nodes).join("rect").attr("class", "node").attr("x", n => n.x0).attr("y", n => n.y0)
        .attr("width", n => n.x1 - n.x0).attr("height", n => Math.max(1, n.y1 - n.y0)).attr("fill", nodeColor);
      nodes.append("title").text(n => `${n.name}: ${fmtFull(n.value, spec.unit)}`);
      const show = sk.nodes.filter(n => n.y1 - n.y0 >= 6 || sk.nodes.length < 16);
      const side = n => (n.x0 < 1 ? "L" : "R");
      ["L", "R"].forEach(sd => {
        const items = show.filter(n => side(n) === sd).sort((a, c) => (a.y0 + a.y1) - (c.y0 + c.y1));
        const ys = declump(items.map(n => (n.y0 + n.y1) / 2), 0, b.ih, FS.label + 2);
        items.forEach((n, i) => {
          const t = b.g.append("text").attr("x", sd === "L" ? n.x0 - 6 : n.x1 + 6).attr("y", ys[i]).attr("dy", "0.35em")
            .attr("text-anchor", sd === "L" ? "end" : "start").attr("font-size", FS.label).call(face, "tickLabels", 400, isHl(C, n.name)).attr("fill", INK)
            .attr("font-family", FONT).text(clip(n.name, sd === "L" ? lwL - 8 - vwL : lwR - 8 - vwR, FS.label, tickF(C, n.name)));
          if (showV) t.append("tspan").attr("class", "qv-node-value").attr("font-size", FS.tick).call(face, "valueLabels").attr("font-style", fi("valueLabels") || (fi("tickLabels") ? "normal" : null))
            .attr("fill", INK).text("  " + fmtShort(n.value, spec.unit));
        });
      });
    },

    bump(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.t !== "" && r.cat !== "");
      if (!rows.length) return empty(C);
      const ts = uniq(rows.map(r => r.t));
      let cats = uniq(rows.map(r => r.cat));
      if (cats.length > 10) {
        const mean = d3.rollup(rows, g => d3.mean(g, r => r.v), r => r.cat);
        const keep = new Set(cats.slice().sort((a, b) => mean.get(a) - mean.get(b)).slice(0, 10));
        C.note = `Top 10 of ${cats.length} by average rank.`;
        cats = cats.filter(c => keep.has(c));
      }
      const get = new Map(rows.map(r => [r.cat + "\u0000" + r.t, r.v]));
      const color = palette(C, cats, {rest: RULE});
      const anyHl = color.hl.size > 0;
      const series = cats.map(c => ({c, pts: ts.map(t => ({t, v: get.get(c + "\u0000" + t)}))})).sort((a, b) => color.hl.has(a.c) - color.hl.has(b.c));
      const maxRank = Math.max(cats.length, Math.ceil(d3.max(series.flatMap(s => s.pts), p => (p.v === undefined || p.v > 25 ? NaN : p.v)) || 1));
      legend(C, [], null);
      const top = C.top + 12;
      const lastOf = s => s.pts.filter(p => p.v !== undefined).at(-1), firstOf = s => s.pts.find(p => p.v !== undefined);
      const fl = flagsOn(C, cats);
      const dm = dimOf(C, cats);
      const lwR = labelWidth(cats, Math.min(170, C.W * 0.2), FS.tick, fl, dm) + 14, lwL = labelWidth(cats, Math.min(140, C.W * 0.16), FS.tick, fl, dm) + 14;
      const b = box(C, top, {left: PAD + (spec.yLabel ? 30 : 0) + 30 + lwL, bottom: bottomFor(C, pointExtra(C, ts)), right: PAD + lwR});
      const x = d3.scalePoint(ts, [0, b.iw]).padding(0.15), y = d3.scaleLinear([1, maxRank], [0, b.ih]);
      const dens = cats.length > 7 ? 0.8 : 1;
      otherGrid(C, b.g, ts.map(t => x(t)), b.iw, b.ih, "x");
      if (gridMode(C) !== "off") d3.range(1, maxRank + 1).forEach(k => b.g.append("line").attr("x2", b.iw).attr("y1", y(k)).attr("y2", y(k)).attr("stroke", GRID).attr("stroke-dasharray", DASH));
      const ay = b.g.append("g").attr("transform", `translate(${-lwL},0)`).call(d3.axisLeft(y).tickValues(d3.range(1, maxRank + 1, maxRank > 15 ? 2 : 1)).tickFormat(k => String(k)).tickSize(0).tickPadding(8));
      styleAxis(ay).select(".domain").remove();
      const ax = pointBottomAxis(C, b.g, x, b.ih + 10, ts, b.iw);
      ax.select(".domain").remove();
      series.forEach(s => {
        const g = b.g.append("g");
        g.append("title").text(s.c);
        const vis = s.pts.filter(p => p.v !== undefined && p.v <= maxRank);
        const lw0 = isN(spec.lineWidth) ? Math.max(1, Math.min(6, spec.lineWidth)) : 3.5 * dens;
        const w = !anyHl || color.hl.has(s.c) ? lw0 : Math.max(1, lw0 * 0.63);
        const dash = dashOf(spec, s.c);
        const path = g.append("path").attr("class", "qv-line").datum(s.pts).attr("fill", "none").attr("stroke", color(s.c)).attr("stroke-width", w)
          .attr("stroke-dasharray", dash).attr("stroke-linecap", dash === "1.5 4" ? "round" : null)
          .attr("d", d3.line().defined(p => p.v !== undefined && p.v <= maxRank).x(p => x(p.t)).y(p => y(p.v)).curve(d3.curveBumpX));
        if (C.anim && !dash) {
          const L = path.node().getTotalLength();
          path.attr("stroke-dasharray", `${L} ${L}`).attr("stroke-dashoffset", L).transition().duration(900).ease(d3.easeCubicOut)
            .attr("stroke-dashoffset", 0).on("end", function () { d3.select(this).attr("stroke-dasharray", null); });
        }
        if (spec.markers !== "off") dots(g, vis, spec.markerShape, 5 * dens, p => x(p.t), p => y(p.v)).attr("fill", color(s.c))
          .attr("stroke", PAPER).attr("stroke-width", 1.2).append("title").text(p => `${s.c}, ${p.t}: ${p.v}`);
      });
      const sideLabels = (pick, xOff, anchor) => {
        const items = series.map(s => ({s, p: pick(s)})).filter(e => e.p && e.p.v <= maxRank).sort((a, b2) => a.p.v - b2.p.v);
        const ys = declump(items.map(e => y(e.p.v)), 0, b.ih, FS.tick + 1);
        items.forEach((e, i) => {
          const k = fl && flagKey(e.s.c), x0 = x(e.p.t) + xOff, start = anchor === "start", fs = sizeAt(dm, e.s.c, FS.tick), fr = flagRoom(fl, fs);
          if (k && start) flagAt(C, b.g, k, x0, ys[i], fs);
          const t = b.g.append("text").attr("x", x0 + (k && start ? fr : 0)).attr("y", ys[i]).attr("dy", "0.35em").attr("text-anchor", anchor)
            .attr("font-size", fs).call(face, "tickLabels", 400, color.hl.has(e.s.c)).attr("fill", anyHl && !color.hl.has(e.s.c) ? MUTED : INK)
            .attr("font-family", FONT).text(clip(e.s.c, (start ? lwR : lwL) - 14 - (k ? fr : 0), fs, fm("tickLabels", 400, color.hl.has(e.s.c))));
          if (k && !start) flagEnd(C, t.node(), k, fs);
        });
      };
      sideLabels(lastOf, 12, "start");
      sideLabels(firstOf, -12, "end");
      axisTitles(C, b, spec.xLabel, spec.yLabel || "Rank");
    },

    dot_range(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.cat !== "");
      if (!rows.length) return empty(C);
      const S = uniq(rows.map(r => str(r.series) || "Value")).slice(0, 2);
      rows = rows.filter(r => S.includes(str(r.series) || "Value"));
      let cats = uniq(rows.map(r => r.cat));
      if (cats.length > 30) { C.note = `First 30 of ${cats.length} shown.`; cats = cats.slice(0, 30); }
      const get = pivot(rows, r => r.cat, r => str(r.series) || "Value");
      const d = cats.map(c => ({c, a: get(c, S[0]), b: get(c, S[1])}));
      const timeish = S.every(s => /^\d{4}/.test(s));
      const over = spec.colors || {};
      const cA = paint(over[S[0]]) || (timeish ? T.dot.aTime : T.dot.a), cB = paint(over[S[1]]) || (timeish ? T.dot.bTime : T.dot.b);
      const color = n => (n === S[0] ? cA : cB);
      const fl = flagsOn(C, cats);
      C.legFlags = flagsOn(C, S);
      legend(C, S, color);
      const top = C.top + 4;
      const k = fitRows(C, cats.length, top + 40 + (spec.yLabel ? 30 : 0) + footH(C));
      if (k < cats.length) { cats = cats.slice(0, k); d.splice(k); }
      grow(C, top + cats.length * 28 + 40 + (spec.yLabel ? 30 : 0) + footH(C));
      const labelsOn = spec.valueLabels === "on";
      const vals = d.flatMap(e => [e.a, e.b]).filter(v => v !== undefined);
      const [lo, hi] = d3.extent(vals), p = (hi - lo) * 0.06 || Math.abs(hi) * 0.1 || 1;
      const dm = dimOf(C, cats), vfs = n => sizeAt(dm, n, FS.min);
      const lw = labelWidth(cats, Math.min(240, C.W * 0.3), FS.label, fl, dm);
      const b = box(C, top, {left: PAD + (spec.xLabel ? 30 : 0) + lw + 10, bottom: 30 + (spec.yLabel ? 30 : 0) + (ang(C) ? 24 : 0), right: PAD + 14 + (labelsOn ? 40 : 0)});
      const x = vScale(C, lo >= 0 ? Math.max(0, lo - p) : lo - p, hi + p, {dataMin: lo, dataMax: hi}).range([0, b.iw]), y = d3.scaleBand(cats, [0, b.ih]).padding(0.5);
      const r = Math.max(4, Math.min(7, y.step() * 0.28));
      if (labelsOn) {
        const low = d.filter(e => e.a !== undefined && e.b !== undefined).map(e => [Math.min(e.a, e.b), e.c]);
        const need = d3.max(low, ([v, c]) => { const w = tw(fmtShort(v, spec.unit), vfs(c), fm("valueLabels", 700)) + r + 10; return x(v) < w ? w : 0; }) || 0;
        if (need > 0) x.range([Math.min(need, b.iw * 0.3), b.iw]);
      }
      const xt = tv(x, nt(xTicks(b.iw, 6)));
      grid(b.g, x, b.iw, b.ih, "x", xt, C);
      otherGrid(C, b.g, cats.map(c => y(c) + y.bandwidth() / 2), b.iw, b.ih, "y");
      const dax = styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).tickValues(xt).tickFormat(v => fmtTick(v, spec.unit)).tickSizeOuter(0)));
      if (ang(C)) dax.selectAll(".tick text").each(function () { tilt(d3.select(this), ang(C)); });
      const row = b.g.selectAll("g.r").data(d).join("g").attr("class", "r").attr("transform", e => `translate(0,${y(e.c) + y.bandwidth() / 2})`);
      row.append("title").text(e => `${e.c}: ${S[0]} ${e.a === undefined ? "n/a" : fmtFull(e.a, spec.unit)}, ${S[1] || ""} ${e.b === undefined ? "n/a" : fmtFull(e.b, spec.unit)}`);
      const both = e => e.a !== undefined && e.b !== undefined;
      const lines = row.filter(both).append("line").attr("stroke", RULE).attr("stroke-width", Math.max(2, r * 0.6));
      const sym = symbolOf(spec.markerShape, r);
      const dot = (sel, fill) => (sym ? sel.append("path").attr("class", "qv-mark").attr("d", sym) : sel.append("circle").attr("r", r)).attr("fill", fill);
      const ca = dot(row.filter(e => e.a !== undefined), cA);
      const cb = dot(row.filter(e => e.b !== undefined), cB);
      if (sym) {
        lines.attr("x1", e => x(e.a)).attr("x2", e => x(e.b));
        ca.attr("transform", e => `translate(${x(e.a)},0)`); cb.attr("transform", e => `translate(${x(e.b)},0)`);
      } else if (C.anim) {
        const mid = e => x(both(e) ? (e.a + e.b) / 2 : e.a ?? e.b);
        lines.attr("x1", mid).attr("x2", mid); ca.attr("cx", mid); cb.attr("cx", mid);
        lines.transition().duration(700).ease(d3.easeCubicOut).attr("x1", e => x(e.a)).attr("x2", e => x(e.b));
        ca.transition().duration(700).ease(d3.easeCubicOut).attr("cx", e => x(e.a));
        cb.transition().duration(700).ease(d3.easeCubicOut).attr("cx", e => x(e.b));
      } else {
        lines.attr("x1", e => x(e.a)).attr("x2", e => x(e.b)); ca.attr("cx", e => x(e.a)); cb.attr("cx", e => x(e.b));
      }
      if (labelsOn) row.each(function (e) {
        const g = d3.select(this), lohi = [[e.a, cA], [e.b, cB]].filter(q => q[0] !== undefined).sort((m, n2) => m[0] - n2[0]);
        lohi.forEach(([v, c], i) => g.append("text").attr("x", x(v) + (i === 0 && lohi.length > 1 ? -(r + 4) : r + 4)).attr("dy", "0.35em")
          .attr("text-anchor", i === 0 && lohi.length > 1 ? "end" : "start").attr("font-size", vfs(e.c)).call(face, "valueLabels", 700).attr("fill", c)
          .attr("font-family", FONT).text(fmtShort(v, spec.unit)));
      });
      bandLeftAxis(C, b.g, y, cats, lw, FS.label, fl);
      refLine(C, b, x, "v");
      axisTitles(C, b, spec.yLabel, spec.xLabel);
    },
  };

  function dashOf(spec, name) {
    if ((spec.dashed || []).map(String).includes(String(name)) || spec.lineStyle === "dashed") return "7 5";
    return spec.lineStyle === "dotted" ? "1.5 4" : null;
  }
  function symbolOf(shape, r) {
    return SYM[shape] && d3[SYM[shape]] ? d3.symbol(d3[SYM[shape]], Math.PI * r * r * (shape === "triangle" ? 1.35 : 1)) : null;
  }
  function dots(g, data, shape, r, cx, cy) {
    const sym = symbolOf(shape, r);
    if (!sym) return g.selectAll(null).data(data).join("circle").attr("cx", cx).attr("cy", cy).attr("r", r);
    return g.selectAll(null).data(data).join("path").attr("class", "qv-mark").attr("transform", d => `translate(${cx(d)},${cy(d)})`).attr("d", sym);
  }
  function curveOf(spec) { return spec.curve === "straight" ? d3.curveLinear : spec.curve === "step" ? d3.curveStepAfter : d3.curveMonotoneX; }

  function declump(ys, lo, hi, pitch) {
    const n = ys.length, out = ys.slice();
    if (!n) return out;
    const p = Math.min(pitch, (hi - lo) / Math.max(1, n - 1));
    out[0] = Math.max(lo, out[0]);
    for (let i = 1; i < n; i++) out[i] = Math.max(out[i], out[i - 1] + p);
    out[n - 1] = Math.min(out[n - 1], hi);
    for (let i = n - 2; i >= 0; i--) out[i] = Math.min(out[i], out[i + 1] - p);
    return out;
  }

  function autoDecimals(rows) {
    const vs = rows.map(r => r.v).filter(Number.isFinite);
    if (!vs.length) return null;
    if (vs.every(v => Number.isInteger(v))) return 0;
    const m = d3.max(vs, v => Math.abs(v));
    if (m >= 1e5) return null;
    if (m >= 100) return 0;
    if (m >= 1) return 1;
    return null;
  }

  function cleanRows(rows) {
    if (!Array.isArray(rows)) return [];
    return rows.filter(r => r && typeof r === "object").map(r => ({
      ...r,
      cat: str(r.cat).trim(),
      series: r.series == null ? "" : str(r.series).trim(),
      t: str(r.t).trim(),
      v: num(r.v),
    }));
  }

  const MIN_W = 320;
  const EXPORT_W = 760;
  function widthOf(svgEl) {
    const host = svgEl.parentNode;
    const w = (host && host.clientWidth) || svgEl.getBoundingClientRect().width || 900;
    return Math.max(MIN_W, Math.round(w));
  }

  const ctlCss = (t, c = t.ctl, r = c.radius + "px") => `.qv-ctl{position:absolute;top:0;left:0;box-sizing:border-box;display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:8px 20px;padding:4px 16px 6px;background:none;color:${c.ink};font:400 15px/1.3 ${t.font};color-scheme:light}
.qv-c{display:flex;flex-wrap:wrap;justify-content:center;align-items:center;gap:6px 10px;min-width:0;margin:0;padding:0;border:0}
.qv-l,.qv-c>legend{float:left;padding:0;color:${c.label};font-size:14px;font-weight:400}
.qv-ctl button,.qv-ctl select,.qv-ctl input{font:inherit;color:inherit}
.qv-seg{position:relative;display:inline-flex;flex-wrap:wrap;justify-content:center;max-width:100%}
.qv-pill{display:none}
${c.pill ? `.qv-seg{gap:2px;padding:3px;border:${c.border};border-radius:${r};background:${c.btnBg}}
.qv-pill{display:block;position:absolute;top:0;left:0;z-index:0;border-radius:${r};background:${c.accent};pointer-events:none;transition:transform .28s cubic-bezier(.4,0,.2,1),width .28s cubic-bezier(.4,0,.2,1),height .28s}
.qv-seg button{position:relative;z-index:1;min-height:28px;padding:3px 12px;border:0;border-radius:${r};background:transparent;color:${c.btnInk};font-size:14px;font-weight:${c.weight};white-space:nowrap;cursor:pointer;transition:color .2s}
.qv-seg button:hover{color:${c.ink}}
.qv-seg button[aria-pressed="true"]{color:${c.onAccent}}` : `.qv-seg button{min-height:30px;margin:0 -1px 0 0;padding:3px 11px;border:${c.border};border-radius:${r};background:${c.btnBg};color:${c.btnInk};font-size:14px;cursor:pointer}
.qv-seg button:hover{border-color:${c.accent};color:${c.accent}}
.qv-seg button[aria-pressed="true"]{position:relative;z-index:1;border-color:${c.accent};background:${c.accent};color:${c.onAccent};font-weight:700}`}
.qv-sw{display:inline-flex;align-items:center;gap:8px;min-height:30px;padding:0;border:0;background:none;color:${c.label};font-size:14px;font-weight:${c.weight};cursor:pointer}
.qv-sw .on{color:${c.ink};font-weight:700}
.qv-track{position:relative;flex:none;width:38px;height:20px;border-radius:${c.trackRadius}px;background:${c.track};transition:background-color .2s}
.qv-track::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:${c.accent};transition:transform .2s}
.qv-sw[aria-checked="true"] .qv-track::after{transform:translateX(18px)}
.qv-ctl select{min-height:30px;max-width:100%;padding:3px 8px;border:${c.border};border-radius:${r};background:${c.btnBg};color:${c.btnInk};font-size:14px;font-weight:${c.weight}}
.qv-checks label{display:inline-flex;align-items:center;gap:5px;color:${c.checkInk};font-size:14px;font-weight:${c.weight};cursor:pointer}
.qv-checks input{width:15px;height:15px;margin:0;accent-color:${c.accent};cursor:pointer}
.qv-slider{flex:1 1 280px}
.qv-slider input[type=range]{flex:1 1 140px;min-width:110px;margin:0;accent-color:${c.accent};cursor:pointer}
.qv-slider output{min-width:3.6em;color:${c.ink};font-weight:700;font-variant-numeric:tabular-nums}
.qv-play{display:inline-grid;flex:none;place-items:center;width:30px;height:30px;padding:0;border:${c.playBorder};border-radius:${r};background:${c.playBg};color:${c.playInk};cursor:pointer}
.qv-play svg{width:12px;height:12px;fill:currentColor}
.qv-all{padding:0;border:0;background:none;color:${c.accent};font-size:14px;font-weight:${c.weight};text-decoration:underline;cursor:pointer}
.qv-ctl :focus-visible{outline:${c.focus};outline-offset:2px}
svg .qv-toggle{cursor:pointer}
svg .qv-toggle:focus{outline:none}
svg .qv-toggle:focus-visible text{text-decoration:underline}
@media (prefers-reduced-motion:reduce){.qv-track,.qv-track::after,.qv-pill{transition:none}}`;
  const PLAY = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 1l9 5-9 5z"/></svg>';
  const PAUSE = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 1h3v10H2zM7 1h3v10H7z"/></svg>';

  const ctlSig = spec => JSON.stringify((spec.controls || []).map(c => [c.type, c.label, c.options, c.items, c.field, c.position, c.style, c.play]));
  function ctlState(st, spec) {
    const sig = ctlSig(spec);
    if (st.ctlSig === sig && st.cv) return st.cv;
    if (st.cv && st.cv.timer) clearInterval(st.cv.timer);
    const init = st.ctlSig === undefined && spec.ctlInit ? spec.ctlInit : null;
    st.ctlSig = sig;
    const data = (spec.controls || []).filter(c => c.options);
    const idx = [];
    data.forEach(c => { const v = init && init.idx ? init.idx[c.data] : null; idx[c.data] = Number.isInteger(v) && v < c.options.length ? v : c.initial || 0; });
    st.cv = {idx, off: {series: new Set(init && init.off ? init.off.series : []), cat: new Set(init && init.off ? init.off.cat : [])}, timer: null};
    if (st.box) { st.box.forEach(b => b.remove()); st.box = null; }
    return st.cv;
  }
  function viewSpec(spec, cv) {
    let v = spec;
    const data = (spec.controls || []).filter(c => c.options).sort((a, b) => a.data - b.data);
    if (data.length && spec.variants) {
      const p = spec.variants[data.map(c => cv.idx[c.data] || 0).join("-")];
      if (p) v = {...spec, ...p};
    }
    const os = cv.off.series, oc = cv.off.cat;
    if (os.size || oc.size) v = {...v, rows: (v.rows || []).filter(r => !os.has(str(r.series)) && !oc.has(str(r.cat)))};
    return v;
  }
  function rerender(svgEl) {
    const st = svgEl.__qv;
    if (!st || !st.spec) return;
    render(svgEl, st.spec, {still: true, width: st.fixedW || undefined});
    (st.upd || []).forEach(f => f());
  }
  function controlEl(svgEl, st, c) {
    const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
    const cv = () => svgEl.__qv.cv;
    const upd = f => { st.upd.push(f); f(); };
    if (c.type === "checkbox") {
      const fs = el("fieldset", "qv-c qv-checks");
      fs.appendChild(el("legend", null, c.label || "Show"));
      c.items.forEach(name => {
        const lb = el("label"), cb = el("input");
        cb.type = "checkbox";
        cb.onchange = () => {
          const off = cv().off[c.field];
          if (!cb.checked && c.items.filter(n => !off.has(n)).length <= 1) { cb.checked = true; return; }
          if (cb.checked) off.delete(name); else off.add(name);
          rerender(svgEl);
        };
        upd(() => { cb.checked = !cv().off[c.field].has(name); });
        lb.append(cb, document.createTextNode(name));
        fs.appendChild(lb);
      });
      const all = el("button", "qv-all", "Show all");
      all.type = "button";
      all.onclick = () => { cv().off[c.field].clear(); rerender(svgEl); };
      fs.appendChild(all);
      return fs;
    }
    const k = c.data, n = c.options.length;
    const pick = j => { cv().idx[k] = j; rerender(svgEl); };
    const seg2 = c.type === "switch" && T.ctl.twoWay === "buttons";
    const box = el("div", "qv-c qv-" + (seg2 ? "select" : c.type));
    if (c.label) box.appendChild(el("span", "qv-l", c.label));
    if (c.type === "slider") {
      let play = null;
      const stop = () => { if (cv().timer) { clearInterval(cv().timer); cv().timer = null; } if (play) { play.innerHTML = PLAY; play.setAttribute("aria-label", "Play"); } };
      if (c.play) {
        play = el("button", "qv-play");
        play.type = "button";
        play.innerHTML = PLAY;
        play.setAttribute("aria-label", "Play");
        play.onclick = () => {
          if (cv().timer) { stop(); return; }
          if (cv().idx[k] >= n - 1) pick(0);
          play.innerHTML = PAUSE;
          play.setAttribute("aria-label", "Pause");
          cv().timer = setInterval(() => { if (cv().idx[k] >= n - 1) { stop(); return; } pick(cv().idx[k] + 1); if (cv().idx[k] >= n - 1) stop(); }, 1100);
        };
        box.appendChild(play);
      }
      const r = el("input"), out = el("output");
      r.type = "range"; r.min = 0; r.max = n - 1; r.step = 1;
      r.setAttribute("aria-label", c.label || "Step");
      r.oninput = () => { stop(); pick(+r.value); };
      upd(() => { const j = cv().idx[k] || 0; r.value = j; r.setAttribute("aria-valuetext", c.options[j]); out.textContent = c.options[j]; });
      box.append(r, out);
      return box;
    }
    if (c.type === "switch" && !seg2) {
      const b = el("button", "qv-sw"), a = el("span", null, c.options[0]), t = el("span", "qv-track"), z = el("span", null, c.options[1]);
      b.type = "button";
      b.setAttribute("role", "switch");
      b.append(a, t, z);
      b.onclick = () => pick(cv().idx[k] ? 0 : 1);
      upd(() => { const on = !!cv().idx[k]; b.setAttribute("aria-checked", String(on)); b.setAttribute("aria-label", `${c.label ? c.label + ": " : ""}${c.options[on ? 1 : 0]}`); a.classList.toggle("on", !on); z.classList.toggle("on", on); });
      box.appendChild(b);
      return box;
    }
    if (c.style === "buttons" || seg2) {
      const seg = el("div", "qv-seg");
      seg.setAttribute("role", "group");
      if (c.label) seg.setAttribute("aria-label", c.label);
      seg.appendChild(el("span", "qv-pill"));
      const bs = c.options.map((o, j) => { const b = el("button", null, o); b.type = "button"; b.onclick = () => pick(j); seg.appendChild(b); return b; });
      upd(() => { bs.forEach((b, j) => b.setAttribute("aria-pressed", String(j === (cv().idx[k] || 0)))); pill(seg); });
      box.appendChild(seg);
      return box;
    }
    const sel = el("select");
    c.options.forEach((o, j) => sel.appendChild(new Option(o, String(j))));
    if (c.label) sel.setAttribute("aria-label", c.label);
    sel.onchange = () => pick(+sel.value);
    upd(() => { sel.value = String(cv().idx[k] || 0); });
    box.appendChild(sel);
    return box;
  }
  function pill(seg, still) {
    const p = seg.firstChild, b = seg.querySelector('button[aria-pressed="true"]');
    if (!p || !b || !b.offsetWidth) return;
    if (still) p.style.transition = "none";
    p.style.width = b.offsetWidth + "px"; p.style.height = b.offsetHeight + "px";
    p.style.transform = `translate(${b.offsetLeft}px,${b.offsetTop}px)`;
    if (still) { void p.offsetWidth; p.style.transition = ""; }
  }
  function ctlStyle() {
    if (typeof document === "undefined") return;
    let css = document.getElementById("qv-ctl-css");
    if (!css) { css = document.createElement("style"); css.id = "qv-ctl-css"; document.head.appendChild(css); }
    if (css.dataset.style !== T.name) { css.textContent = ctlCss(T); css.dataset.style = T.name; }
  }
  function buildControls(svgEl, st, spec) {
    const host = svgEl.parentNode;
    if (!host || typeof document === "undefined") return;
    ctlStyle();
    st.upd = [];
    st.boxStyle = T.name;
    const row = document.createElement("div");
    row.className = "qv-ctl";
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", "Chart controls");
    spec.controls.filter(c => c.type !== "legend").forEach(c => row.appendChild(controlEl(svgEl, st, c)));
    st.box = row.childNodes.length ? [row] : [];
    if (!row.childNodes.length) return;
    if (getComputedStyle(host).position === "static") host.style.position = "relative";
    host.insertBefore(row, svgEl.nextSibling);
  }
  function placeControls(svgEl, st, C) {
    const row = st.box && st.box[0];
    if (!row) return;
    const host = svgEl.parentNode, hr = host.getBoundingClientRect(), sr = svgEl.getBoundingClientRect(), k = sr.height && H ? sr.height / H : 1;
    row.style.left = sr.left - hr.left - host.clientLeft + "px";
    row.style.width = sr.width + "px";
    row.style.top = sr.top - hr.top - host.clientTop + (C.ctlY || 0) * k + "px";
    row.querySelectorAll(".qv-seg").forEach(g => pill(g, true));
  }

  function numberLocale(spec) {
    const dec = spec.decimalMark === "comma" ? "," : ".";
    const th = {comma: ",", space: "\u00a0", none: ""}[spec.thousands] ?? (dec === "," ? "." : ",");
    if (dec === "." && th === ",") return d3;
    return d3.formatLocale({decimal: dec, thousands: th, grouping: [3], currency: ["", ""], minus: "\u2212"});
  }

  function lookSpec(spec) {
    if (spec.axisTitles !== "off") return spec;
    const o = {...spec, xLabel: "", yLabel: ""};
    if ((spec.kind === "heatmap" || spec.kind === "map") && !spec.legendTitle) o.legendTitle = spec.yLabel || (spec.kind === "map" ? spec.xLabel : "") || "";
    return o;
  }

  const MARKS = ["rect.bar", "g.s rect", "rect.cell", "g.leaf rect", "path.area", "path.qv-line", "circle", "path.qv-mark", "rect.node", "path.qv-arc", "path.qv-shape"].map(q => ".qv-plot " + q).join(",");

  function cutLabels(C) {
    const names = new Set();
    C.rows.forEach(r => [r.cat, r.series, r.t].forEach(v => { if (v) names.add(String(v)); }));
    const list = [...names];
    C.root.selectAll("text").each(function () {
      const node = this.firstChild;
      if (!node || node.nodeType !== 3) return;
      const t = node.nodeValue, base = t.replace(/…$/, "");
      if (base.length <= LMAX) return;
      const full0 = names.has(t) ? t : t.endsWith("…") ? list.find(n => n.startsWith(base)) : null;
      if (!full0) return;
      node.nodeValue = base.slice(0, LMAX).trimEnd() + "…";
      if (!this.querySelector("title")) d3.select(this).append("title").text(full0);
    });
  }

  function finish(C) {
    const s = C.spec, root = C.root;
    if (isN(s.opacity) && s.opacity < 1) root.selectAll(MARKS).style("opacity", Math.max(0.15, s.opacity));
    if (LMAX) cutLabels(C);
    placeFlags(C);
    if (C.raw.textHalo === "on") {
      const halo = SHADES[C.raw.background] || WHITE;
      const haloed = root.selectAll(".qv-plot text, .qv-legend text, .qv-key text").filter(function () { return !/^(#fff(fff)?|white)$/i.test(this.getAttribute("fill") || "") && !this.closest("g.leaf") && !/\b(cv|seg)\b/.test(this.getAttribute("class") || ""); });
      if (!haloed.empty()) mark("textHalo");
      haloed.attr("paint-order", "stroke").attr("stroke", halo).attr("stroke-width", 3.5).attr("stroke-linejoin", "round").attr("stroke-opacity", 0.92);
    }
    if (s.border === "on") root.append("rect").attr("class", "qv-border").attr("x", 0.5).attr("y", 0.5).attr("width", C.W - 1).attr("height", H - 1)
      .attr("fill", "none").attr("stroke", RULE);
  }

  function render(svgEl, spec, opts) {
    if (!svgEl) return;
    spec = spec || {};
    const st = svgEl.__qv || (svgEl.__qv = {});
    st.fixedW = opts && opts.width ? Math.max(MIN_W, Math.round(opts.width)) : null;
    if (opts && "fitH" in opts) st.fitH = isN(opts.fitH) ? opts.fitH : null;
    if (opts && "patches" in opts) setPatches(st, opts.patches);
    const W = st.fixedW || widthOf(svgEl);
    const sig = spec.kind + "|" + (spec.rows ? spec.rows.length : 0);
    const changed = !(opts && opts.still) && st.kind !== spec.kind;
    st.spec = spec; st.kind = spec.kind; st.w = W; st.sig = sig;
    const noCtl = !!(opts && opts.noControls);
    const ctl = Array.isArray(spec.controls) && spec.controls.length ? spec.controls : null;
    const cv = ctl ? ctlState(st, spec) : null;
    tone(svgEl, spec.style);
    if ((!ctl || noCtl || st.boxStyle !== T.name) && st.box) { st.box.forEach(b => b.remove()); st.box = null; }
    if (ctl && !noCtl && !st.box) buildControls(svgEl, st, spec);
    else if (st.box) ctlStyle();
    if (st.box && st.box[0]) st.box[0].style.width = W + "px";
    const ctlH = st.ctlH = st.box ? Math.ceil(st.box.reduce((h, d) => h + d.offsetHeight, 0)) : 0;
    const fitH = st.fixedW || !st.fitH ? null : st.fitH - ctlH;
    H = (isN(spec.height) && spec.height >= 320 ? Math.min(900, Math.round(spec.height)) : fitH ? Math.round(Math.max(FIT_MIN, Math.min(fitH, W * 0.8))) : W < 560 ? NARROW_H : BASE_H) + ctlH;
    const fz = isN(spec.fontSize) ? pxSize(spec.fontSize) : SIZES[spec.fontSize] || SIZES.normal;
    FS.tick = fz.tick; FS.label = fz.label; FS.min = fz.min || T.fs.min; FS.axis = fz.axis || T.fs.title;
    FS.title = isN(spec.titleSize) ? Math.max(12, Math.min(32, Math.round(spec.titleSize))) : T.fs.title;
    PAD = isN(spec.padding) ? Math.max(0, Math.min(48, Math.round(spec.padding))) : 16;
    LMAX = isN(spec.labelMax) ? Math.max(4, Math.round(spec.labelMax)) : null;
    NUMSTYLE = spec.numberStyle || "auto";
    NF = numberLocale(spec);
    NT = Number.isInteger(spec.ticks) ? Math.max(2, Math.min(12, spec.ticks)) : null;
    const ink = spec.textColor === "black" ? T.ink : ["green", "navy", "red", "grey", "teal", "slate"].includes(spec.textColor) ? paint(spec.textColor) : null;
    if (ink) { INK = ink; MUTED = ink; }
    if (SHADES[spec.background]) PAPER = SHADES[spec.background];
    DEC = Number.isInteger(spec.decimals) ? Math.max(0, Math.min(3, spec.decimals)) : null;
    const svg = d3.select(svgEl).attr("xmlns", "http://www.w3.org/2000/svg").attr("font-family", FONT).classed("qv-chart", true);
    svg.selectAll("*").interrupt();
    svg.selectAll("*").remove();
    const root = svg.append("g").attr("class", "qv-root");
    const bg = root.append("rect").attr("class", "qv-bg").attr("width", W).attr("fill", spec.background === "transparent" ? "none" : PAPER);
    const shown = cv ? viewSpec(spec, cv) : spec;
    const draw = lookSpec(shown);
    const used = new Set(["kind", "height", "fontSize", "padding", "textColor", "background", "labelMax", "controls"]);
    USE = used;
    const C = {root, spec: track(draw, used), raw: draw, rows: cleanRows(draw.rows), W, logo: logoBox(spec, W), anim: changed, note: "", svgEl, leg: null, logNote: "", fit: null, fitMode: !!fitH, ctlH,
      space: fitH ? Math.max(FIT_MIN, fitH) + ctlH : isN(spec.height) && spec.height >= 320 ? H : Math.max(H, SPACE_MAX + ctlH)};
    if (cv) {
      const base = cleanRows(spec.rows);
      C.colorOrder = uniq([...base.map(r => r.series), ...base.map(r => r.cat)].filter(Boolean));
      C.offSeries = cv.off.series;
      C.toggle = !noCtl && ctl.some(c => c.type === "legend");
      C.toggleFn = name => {
        const off = cv.off.series;
        if (!off.has(name) && uniq(C.rows.map(r => r.series).filter(Boolean)).filter(n => n !== name).length < 1) return;
        if (off.has(name)) off.delete(name); else off.add(name);
        rerender(svgEl);
        const again = [...svgEl.querySelectorAll(".qv-toggle")].find(e => e.getAttribute("data-name") === name);
        if (again) again.focus();
      };
    }
    FST = C.spec.fontStyle && typeof C.spec.fontStyle === "object" ? C.spec.fontStyle : null;
    AUTO_DEC = autoDecimals(C.rows);
    WHOLE = C.rows.length > 0 && C.rows.every(r => ["v", "v2"].every(k => r[k] == null || Number.isInteger(+r[k])));
    C.top = header(C);
    if (!R[spec.kind]) empty(C, spec.kind ? `Unknown chart type "${spec.kind}"` : "Upload data to see a chart");
    else {
      try { R[spec.kind](C); } catch (e) { console.error("QV.render", spec.kind, e); root.selectAll(".qv-plot").remove(); empty(C, "Could not draw this data"); }
    }
    drawFoot(C);
    finish(C);
    drawLogo(C);
    USE = null;
    st.used = C.blank ? null : [...used];
    st.flagsUsed = C.flagSet ? [...C.flagSet] : [];
    st.fit = C.fit;
    st.orient = C.orient || null;
    bg.attr("height", H);
    svg.attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.style("height", !fitH ? null : Math.min(H, Math.max(FIT_MIN, fitH) + ctlH) + "px");
    placeControls(svgEl, st, C);
    runPatches(svgEl, st, C);
    if (st.patchErr.length && !(opts && opts.again)) {
      const errs = st.patchErr;
      render(svgEl, spec, {...(opts || {}), still: true, again: true});
      st.patchErr = errs;
      if (window.QV_ON_RENDER) window.QV_ON_RENDER(svgEl, st);
      return svgEl;
    }
    if (changed) root.attr("opacity", 0).transition().duration(FADE_MS).ease(d3.easeCubicOut).attr("opacity", 1);
    if (!st.ro && typeof ResizeObserver !== "undefined" && svgEl.parentNode && !(opts && opts.noResize)) {
      let timer;
      st.ro = new ResizeObserver(() => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          const s = svgEl.__qv;
          const row = s && s.box && s.box[0];
          if (s && s.spec && !s.fixedW && (Math.abs(widthOf(svgEl) - s.w) > 3 || (row && Math.ceil(row.offsetHeight) !== s.ctlH))) render(svgEl, s.spec, {still: true});
        }, 120);
      });
      st.ro.observe(svgEl.parentNode);
    }
    if (window.QV_ON_RENDER) window.QV_ON_RENDER(svgEl, st);
    return svgEl;
  }

  function setPatches(st, list) {
    const next = Array.isArray(list) ? list.filter(p => p && typeof p.code === "string" && p.code.trim()).map(p => ({code: p.code, note: String(p.note || "")})) : [];
    const sig = l => (l || []).map(p => p.code).join("\u0000");
    if (st.patches && sig(st.patches) === sig(next)) return;
    st.patches = next;
    st.patchSkip = new Set();
    st.patchErr = [];
  }

  const OUT_ATTRS = ["x", "y", "dx", "dy", "cx", "cy", "r", "x1", "y1", "x2", "y2", "width", "height", "transform", "text-anchor", "fill", "stroke", "stroke-width", "stroke-dasharray", "font-size", "font-weight", "opacity", "fill-opacity", "stroke-opacity", "data-name"];
  const OUT_KEYS = ["cat", "series", "t", "v", "v2", "name", "key", "id", "s", "c", "value", "a", "b", "x0", "x1"];
  function outline(svgEl, maxLen = 6000) {
    if (!svgEl || !svgEl.getScreenCTM) return "";
    const short = (v, n = 28) => { const s = typeof v === "number" ? String(Math.round(v * 100) / 100) : String(v); return s.length > n ? s.slice(0, n) + "…" : s; };
    const rootM = svgEl.getScreenCTM(), inv = rootM && rootM.inverse();
    const box = el => {
      try {
        const b = el.getBBox(), m = el.getScreenCTM();
        if (!m || !inv) return null;
        const t = inv.multiply(m), p = (x, y) => [x * t.a + y * t.c + t.e, x * t.b + y * t.d + t.f];
        const [x0, y0] = p(b.x, b.y), [x1, y1] = p(b.x + b.width, b.y + b.height);
        return [Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)].map(Math.round);
      } catch (e) { return null; }
    };
    const datum = el => {
      let d = el.__data__;
      if (d == null) return "";
      if (typeof d !== "object") return "datum=" + short(d);
      if (d.data && typeof d.data === "object" && !Array.isArray(d.data)) d = d.data;
      if (Array.isArray(d)) return `datum=[${d.length} items]`;
      const keys = OUT_KEYS.filter(k => d[k] != null && typeof d[k] !== "object" && d[k] !== "");
      return keys.length ? "datum{" + keys.map(k => `${k}:${short(d[k], 24)}`).join(", ") + "}" : "";
    };
    const sig = el => el.tagName + (el.getAttribute("class") ? "." + el.getAttribute("class").trim().split(/\s+/).join(".") : "");
    const own = el => (el.tagName === "text" ? el.textContent.trim() : "");
    const dimmed = e => ["opacity", "fill-opacity"].some(a => { const v = e.getAttribute(a) ?? (e.style && e.style.getPropertyValue(a)); return v != null && v !== "" && +v < 1; });
    const faded = el => dimmed(el) || [...el.querySelectorAll("*")].some(dimmed);
    const line = el => {
      const parts = [sig(el)];
      const txt = own(el);
      if (txt) parts.push(JSON.stringify(short(txt, 40)));
      const d = datum(el);
      if (d) parts.push(d);
      OUT_ATTRS.forEach(a => { const v = el.getAttribute(a); if (v != null && v !== "") parts.push(`${a}=${/^-?\d+(\.\d+)?$/.test(v) ? Math.round(+v * 10) / 10 : short(v, 40)}`); });
      ["opacity", "fill-opacity", "fill"].forEach(a => { const v = el.style && el.style.getPropertyValue(a); if (v) parts.push(`style.${a}=${short(v, 40)}`); });
      const b = box(el);
      if (b) parts.push(`box=[${b.join(",")}]`);
      return parts.join(" ");
    };
    const out = [`svg width=${svgEl.getAttribute("width")} height=${svgEl.getAttribute("height")}. box=[x,y,w,h] is in svg pixels from the top left. Other numbers are the element's own attributes.`];
    let len = out[0].length, cut = false;
    const push = s => { if (cut) return; if (len + s.length > maxLen) { cut = true; out.push("… outline cut here"); return; } out.push(s); len += s.length + 1; };
    const skip = el => ["title", "defs", "style", "desc", "clipPath"].includes(el.tagName) || el.classList.contains("qv-flag");
    const walk = (el, depth) => {
      const kids = [...el.children].filter(k => !skip(k));
      const groups = [];
      kids.forEach(k => { const s = sig(k), g = groups.at(-1); if (g && g.sig === s) g.els.push(k); else groups.push({sig: s, els: [k]}); });
      const pad = "  ".repeat(depth);
      for (const g of groups) {
        if (cut) return;
        if (g.els.length === 1) {
          push(pad + line(g.els[0]));
          if (g.els[0].children.length && g.els[0].tagName !== "text") walk(g.els[0], depth + 1);
          continue;
        }
        const first = g.els[0];
        if (first.tagName === "g" && g.els.every(e => e.querySelectorAll("*:not(.qv-flag)").length <= 4)) {
          const texts = g.els.map(e => [...e.querySelectorAll("text")].map(own).join(" ")).filter(Boolean);
          const dim = g.els.filter(faded).map(e => [...e.querySelectorAll("text")].map(own).join(" ") || "?");
          push(pad + `${g.sig} x${g.els.length}` + (texts.length ? " texts: " + texts.slice(0, 20).map(t => JSON.stringify(short(t, 24))).join(", ") + (texts.length > 20 ? ", …" : "") : "") + ` first: ${line(first)}`
            + (dim.length ? ` faded x${dim.length}: ` + dim.slice(0, 20).map(t => JSON.stringify(short(t, 24))).join(", ") : ""));
          continue;
        }
        const many = first.tagName === "text" ? 40 : first.tagName === "g" ? 6 : 14;
        push(pad + `${g.sig} x${g.els.length}`);
        g.els.slice(0, many).forEach(e => { push(pad + "  " + line(e)); if (e.tagName === "g" && e.children.length) walk(e, depth + 2); });
        if (g.els.length > many) push(pad + `  … ${g.els.length - many} more ${g.sig}`);
      }
    };
    walk(svgEl, 0);
    return out.join("\n");
  }

  function guardLoops(code) {
    const n = code.length, idc = /[A-Za-z0-9_$.]/;
    const skipStr = (j, q) => { j++; while (j < n && code[j] !== q) { if (code[j] === "\\") j++; j++; } return j + 1; };
    let out = "", i = 0;
    while (i < n) {
      const c = code[i];
      if (c === '"' || c === "'" || c === "`") { const j = skipStr(i, c); out += code.slice(i, j); i = j; continue; }
      if (c === "/" && code[i + 1] === "/") { let j = code.indexOf("\n", i); if (j < 0) j = n; out += code.slice(i, j); i = j; continue; }
      if (c === "/" && code[i + 1] === "*") { let j = code.indexOf("*/", i + 2); j = j < 0 ? n : j + 2; out += code.slice(i, j); i = j; continue; }
      const m = (c === "f" || c === "w") && !idc.test(code[i - 1] || "") ? /^(for|while)\s*\(/.exec(code.slice(i, i + 12)) : null;
      if (!m) { out += c; i++; continue; }
      let j = i + m[0].length, depth = 1;
      const start = j, semis = [];
      while (j < n && depth) {
        const d = code[j];
        if (d === '"' || d === "'" || d === "`") { j = skipStr(j, d); continue; }
        if ("([{".includes(d)) depth++;
        else if (")]}".includes(d)) depth--;
        else if (d === ";" && depth === 1) semis.push(j);
        j++;
      }
      const inner = code.slice(start, j - 1);
      if (m[1] === "while") out += `while (__qvGuard() && (${guardLoops(inner)}))`;
      else if (semis.length === 2) {
        const a = code.slice(start, semis[0]), b = code.slice(semis[0] + 1, semis[1]), z = code.slice(semis[1] + 1, j - 1);
        out += `for (${guardLoops(a)}; __qvGuard() && (${b.trim() ? guardLoops(b) : "true"}); ${guardLoops(z)})`;
      } else out += `for (${guardLoops(inner)})`;
      i = j;
    }
    return out;
  }

  function runPatches(svgEl, st, C) {
    st.patchErr = [];
    const list = st.patches || [];
    if (!list.length) return;
    st.patchSkip = st.patchSkip || new Set();
    const svg = d3.select(svgEl), size = {width: C.W, height: H};
    list.forEach((p, i) => {
      if (st.patchSkip.has(p.code)) return;
      const t0 = Date.now(), end = t0 + PATCH_MS;
      const guard = () => { if (Date.now() > end) throw new Error(`it ran over the ${PATCH_MS} ms limit`); return true; };
      try {
        new Function("svg", "d3", "data", "size", "__qvGuard", "\"use strict\";\n" + guardLoops(p.code))(svg, d3, C.rows.map(r => ({...r})), {...size}, guard);
        const ms = Date.now() - t0;
        if (ms > PATCH_MS) throw new Error(`it took ${ms} ms, the limit is ${PATCH_MS} ms`);
      } catch (e) {
        st.patchSkip.add(p.code);
        st.patchErr.push({index: i, note: p.note, message: String((e && e.message) || e).slice(0, 300)});
      }
    });
  }

  const ready = (async () => {
    if (!document.fonts || !document.fonts.load) return;
    try {
      const faces = uniq(Object.values(THEMES).filter(t => t && t.webFont).map(t => t.font.split(",")[0].trim()));
      await Promise.all(faces.flatMap(f => [document.fonts.load(`400 15px ${f}`), document.fonts.load(`700 15px ${f}`)]));
      await document.fonts.ready;
    } catch (e) { }
    measureCtx = null;
  })();

  async function b64(url) {
    const buf = await (await fetch(url)).arrayBuffer();
    let bin = "";
    const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  }
  let fontCss = null;
  async function embeddedFonts() {
    if (fontCss) return fontCss;
    if (window.QV_FONT_CSS) return (fontCss = window.QV_FONT_CSS);
    try {
      const css = await (await fetch(BASE + "fonts/carlito.css")).text();
      const urls = [...css.matchAll(/url\("([^"]+)"\)/g)].map(m => m[1]);
      let out = css;
      for (const u of urls) out = out.replace(`url("${u}")`, `url("data:font/woff2;base64,${await b64(BASE + "fonts/" + u)}")`);
      fontCss = out;
    } catch (e) { fontCss = ""; }
    return fontCss;
  }

  const STYLE_PROPS = ["paint-order", "fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
    "opacity", "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dominant-baseline", "letter-spacing", "visibility", "display", "text-decoration"];

  async function svgImage(svgEl) {
    const th = themeOf(svgEl.__qv && svgEl.__qv.spec && svgEl.__qv.spec.style);
    if (th.webFont) await ready;
    const W = +svgEl.getAttribute("width") || widthOf(svgEl), Hh = +svgEl.getAttribute("height") || BASE_H;
    const clone = svgEl.cloneNode(true);
    const src = [svgEl, ...svgEl.querySelectorAll("*")], dst = [clone, ...clone.querySelectorAll("*")];
    src.forEach((el, i) => {
      const cs = getComputedStyle(el), out = dst[i];
      if (!out || !out.style || el.closest("defs")) return;
      STYLE_PROPS.forEach(p => { const v = cs.getPropertyValue(p); if (v) out.style.setProperty(p, v); });
    });
    clone.querySelectorAll(".qv-root").forEach(n => { n.style.opacity = "1"; n.removeAttribute("opacity"); });
    clone.querySelectorAll("title").forEach(n => n.remove());
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", W); clone.setAttribute("height", Hh);
    clone.style.width = W + "px"; clone.style.height = Hh + "px";
    clone.style.position = "static";
    const fonts = th.webFont ? await embeddedFonts() : "";
    if (fonts) {
      const s = document.createElementNS("http://www.w3.org/2000/svg", "style");
      s.textContent = fonts;
      clone.insertBefore(s, clone.firstChild);
    }
    return {markup: new XMLSerializer().serializeToString(clone), W, H: Hh};
  }

  async function exportMarkup(svgEl) {
    if (!svgEl) return null;
    const st = svgEl.__qv;
    let tmp = null;
    if (st && st.spec) {
      const w = EXPORT_W;
      tmp = document.createElement("div");
      tmp.style.cssText = `position:absolute;left:-10000px;top:0;width:${w}px`;
      document.body.appendChild(tmp);
      const s2 = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      tmp.appendChild(s2);
      s2.__qv = {patches: st.patches, patchSkip: st.patchSkip};
      if (st.cv) Object.assign(s2.__qv, {cv: st.cv, ctlSig: st.ctlSig});
      render(s2, st.spec, {width: w, still: true, noResize: true, noControls: true});
      if (st.spec.kind === "map") await new Promise(r => setTimeout(r, 400));
      svgEl = s2;
    }
    try {
      const out = await svgImage(svgEl);
      return {...out, transparent: !!(st && st.spec && st.spec.background === "transparent")};
    } finally { if (tmp) tmp.remove(); }
  }

  async function pngFromMarkup(m, filename, scale = 4) {
    const {markup, W, H: Hh} = m;
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(markup); });
    if (img.decode) { try { await img.decode(); } catch (e) { } }
    await new Promise(r => setTimeout(r, 60));
    const canvas = document.createElement("canvas");
    const k = Math.min(scale, CANVAS_SIDE / Math.max(W, Hh), Math.sqrt(CANVAS_AREA / (W * Hh)));
    canvas.width = Math.floor(W * k); canvas.height = Math.floor(Hh * k);
    const ctx = canvas.getContext("2d");
    ctx.scale(k, k);
    if (!m.transparent) { ctx.fillStyle = WHITE; ctx.fillRect(0, 0, W, Hh); }
    ctx.drawImage(img, 0, 0, W, Hh);
    const blob = await new Promise(res => canvas.toBlob(res, "image/png"));
    if (filename !== false) download(blob, (filename || "chart").replace(/\.png$/i, "") + ".png");
    return blob;
  }

  async function exportPNG(svgEl, filename, scale = 4) {
    const m = await exportMarkup(svgEl);
    return m ? pngFromMarkup(m, filename, scale) : undefined;
  }

  function download(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  async function text(url) { const r = await fetch(url); if (!r.ok) throw new Error("Could not load " + url); return r.text(); }
  const safe = t => String(t).replace(/<\/(script)/gi, "<\\/$1").replace(/<!--/g, "<\\!--");
  const escHtml = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  function fontsFor(css, txt) {
    const cps = [...new Set([...txt].map(c => c.codePointAt(0)))];
    const hit = range => range.split(",").some(r => {
      const [a, z] = r.trim().replace(/^U\+/i, "").split("-");
      const lo = parseInt(a.replace(/\?/g, "0"), 16), hi = z ? parseInt(z, 16) : parseInt(a.replace(/\?/g, "f"), 16);
      return cps.some(c => c >= lo && c <= hi);
    });
    return css.split(/(?=@font-face)/).filter(b => { const m = /unicode-range:\s*([^;}]+)/.exec(b); return !m || hit(m[1]); }).join("").replace(/\s*\n\s*/g, "");
  }

  async function exportHTML(spec, svgEl, extra) {
    const THEME_FILES = {ceps: "export/ceps-theme.min.js", aiw: "export/aiw-theme.min.js", franri: "export/franri-theme.min.js"};
    const ex = extra || {};
    const qv = (svgEl && svgEl.__qv) || {};
    const geoUsed = ex.geoUsed || qv.geoUsed || null;
    const patches = (ex.patches || qv.patches || []).filter(p => p && typeof p.code === "string").map(p => ({code: p.code, note: String(p.note || "")}));
    const style = THEME_FILES[spec.style] ? spec.style : "ceps", th = themeOf(style);
    const parts = await Promise.all([text(BASE + "export/d3.min.js"), spec.kind === "sankey" ? text(BASE + "export/d3-sankey.min.js") : "",
      text(BASE + THEME_FILES[style]), text(BASE + "export/charts.min.js"), th.webFont ? embeddedFonts() : ""]);
    const [d3src, sankeySrc, themeSrc, chartsSrc, allFonts] = parts;
    let geoInline = "", topoSrc = "";
    if (spec.kind === "map") {
      const used = geoUsed || "world";
      topoSrc = await text(BASE + "export/topojson-client.min.js");
      const inline = {};
      if (used === "world") inline.world = JSON.parse(await text(BASE + "export/countries-50m.min.json"));
      else { inline.regions = {[used]: JSON.parse(await text(BASE + "geo/regions/" + used + ".json"))}; inline.index = JSON.parse(await text(BASE + "geo/regions/index.json")); }
      geoInline = `window.QV_GEO_INLINE = ${JSON.stringify(inline)};`;
    }
    const clean = {...spec};
    const cvNow = qv.cv;
    if (ex.ctlInit && spec.controls) clean.ctlInit = ex.ctlInit;
    else if (cvNow && spec.controls) clean.ctlInit = {idx: cvNow.idx.slice(), off: {series: [...cvNow.off.series], cat: [...cvNow.off.cat]}};
    if (spec.kind === "map" && geoUsed && !clean.geo) clean.geo = geoUsed;
    const drawn = Array.isArray(ex.flagsUsed) ? ex.flagsUsed : qv.flagsUsed || [];
    const keys = drawn.length && spec.controls && spec.controls.length ? uniq([...drawn, ...flagKeys(spec)]) : drawn;
    const flagSrc = ex.flagData || FLAGS;
    const flagSet = keys.filter(k => typeof flagSrc[k] === "string");
    const flagInline = flagSet.length ? `window.QV_FLAGS = ${JSON.stringify(Object.fromEntries([["_notice", flagSrc._notice || ""], ...flagSet.map(k => [k, flagSrc[k]])]))};` : "";
    const fonts = allFonts ? fontsFor(allFonts, JSON.stringify(clean) + JSON.stringify(patches)) : "";
    return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="${FRAME_CSP}">
<title>${escHtml(spec.title || "Chart")}</title>
<style>${fonts}
html,body{margin:0;background:${th.paper}}
body{box-sizing:border-box;padding:24px;font-family:${th.font};color:${th.ink}}
.viz{max-width:760px;margin:0 auto}
#chart{display:block;width:100%;height:auto}</style>
</head><body>
<div class="viz"><svg id="chart" role="img" aria-label="${escHtml(spec.title || "Chart")}"></svg></div>
<script>${safe(d3src)}<\/script>
${sankeySrc ? `<script>${safe(sankeySrc)}<\/script>` : ""}
${topoSrc ? `<script>${safe(topoSrc)}<\/script>` : ""}
<script>${safe(themeSrc)}<\/script>
<script>window.QV_BASE = "./";${safe(geoInline)}${safe(flagInline)}<\/script>
<script>${safe(chartsSrc)}<\/script>
<script>
const spec = ${safe(JSON.stringify(clean))};
const patches = ${safe(JSON.stringify(patches))};
const el = document.getElementById("chart");
function fit() {
  const w = Math.max(320, Math.min(760, el.parentNode.clientWidth));
  QV.render(el, spec, {width: w, noResize: true, still: true, patches});
  el.removeAttribute("width"); el.removeAttribute("height");
}
${th.webFont ? "QV.ready.then(fit);" : "fit();"}
let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(fit, 150); });
<\/script>
</body></html>
`;
  }

  window.QV = {EXPORT_W, FRAME_CSP, render, ready, exportPNG, exportMarkup, pngFromMarkup, exportHTML, embeddedFonts, outline, download, flagKeys, countryId, regionCountry, loadRegionIndex, isEU, colors: NAMED, kinds: Object.keys(R)};
})();
