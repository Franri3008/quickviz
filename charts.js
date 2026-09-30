(function () {
  const H = 420;
  const PAD = 18;
  const SERIF = '"Libre Baskerville", "Bodoni 72", Didot, serif';
  const SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  const PALETTE = ["#2756d3", "#E53229", "#f59e0b", "#10b981", "#8b5cf6", "#06b6d4", "#f97316", "#ec4899", "#84cc16", "#64748b"];
  const OTHER = "Other";
  const OTHER_COLOR = "#b6bcc6";
  const INK = "#0f172a", TICK = "#4b5563", AXIS = "#cfd2d7", GRID = "#DBDBDB";
  const FADE_MS = 260;

  let measureCtx = null;
  function tw(s, size = 11, weight = 600) {
    measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
    measureCtx.font = `${weight} ${size}px ${SANS}`;
    return measureCtx.measureText(String(s)).width;
  }
  function clip(s, max, size = 11, weight = 600) {
    s = String(s);
    if (tw(s, size, weight) <= max) return s;
    let lo = 0, hi = s.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (tw(s.slice(0, mid) + "…", size, weight) <= max) lo = mid; else hi = mid - 1;
    }
    return lo ? s.slice(0, lo).trimEnd() + "…" : "…";
  }

  function num(v) {
    if (v == null || v === "") return NaN;
    if (typeof v === "number") return v;
    const n = Number(String(v).replace(/[,\s$€£%]/g, ""));
    return Number.isFinite(n) ? n : NaN;
  }
  const str = v => (v == null ? "" : String(v));

  function unitParts(u) {
    u = str(u).trim();
    if (!u) return ["", ""];
    if (/^[$€£¥₹]$/.test(u) || /^[A-Z]{0,2}\$$/.test(u)) return [u, ""];
    if (u === "%") return ["", "%"];
    return ["", " " + u];
  }
  function withUnit(s, unit) {
    const [p, suf] = unitParts(unit);
    let neg = "";
    s = s.replace(/^[-−]/, m => ((neg = "−"), ""));
    return neg + p + s + suf;
  }
  function short(v) {
    const a = Math.abs(v);
    const f = d3.format(".3~r");
    if (a >= 1e12) return f(v / 1e12) + "T";
    if (a >= 1e9) return f(v / 1e9) + "B";
    if (a >= 1e6) return f(v / 1e6) + "M";
    if (a >= 1e4) return f(v / 1e3) + "k";
    if (a >= 1) return d3.format(",.4~r")(v);
    if (a === 0) return "0";
    return d3.format(".2~r")(v);
  }
  function full(v) {
    const a = Math.abs(v);
    if (a >= 1e6) return short(v);
    if (a >= 100) return d3.format(",.0f")(v);
    if (a >= 1) return d3.format(",.2~f")(v);
    return d3.format(".3~r")(v);
  }
  const fmtShort = (v, unit) => withUnit(short(v), unit);
  const fmtFull = (v, unit) => withUnit(full(v), unit);

  function makeColor(names) {
    const map = new Map();
    let i = 0;
    names.forEach(n => {
      if (map.has(n)) return;
      map.set(n, n === OTHER ? OTHER_COLOR : PALETTE[i++ % PALETTE.length]);
    });
    return n => map.get(n) || OTHER_COLOR;
  }

  function uniq(arr) { return [...new Set(arr)]; }

  function capByTotal(names, totals, max) {
    if (names.length <= max) return {keep: names, other: false};
    const sorted = names.slice().sort((a, b) => (totals.get(b) || 0) - (totals.get(a) || 0));
    const top = new Set(sorted.slice(0, max));
    return {keep: names.filter(n => top.has(n)), other: true};
  }

  function title(sel, text) { if (text) sel.append("title").text(text); return sel; }

  function header(C) {
    const {root, spec, W} = C;
    let right = W - PAD;
    if (spec.mock) {
      const t = "Sample data", w = tw(t, 11, 600) + 16;
      const tag = root.append("g").attr("class", "qv-tag").attr("transform", `translate(${right - w},10)`);
      tag.append("rect").attr("width", w).attr("height", 20).attr("rx", 10).attr("fill", "#fff6dd").attr("stroke", "#f0c36d");
      tag.append("text").attr("x", w / 2).attr("y", 14).attr("text-anchor", "middle").attr("font-size", 11).attr("font-weight", 600)
        .attr("font-family", SANS).attr("fill", "#8a5a00").text(t);
      right -= w + 12;
    }
    if (spec.title) {
      root.append("text").attr("class", "qv-title").attr("x", PAD).attr("y", 26).attr("font-family", SERIF)
        .attr("font-size", 18).attr("font-weight", 700).attr("fill", INK).text(clip(spec.title, right - PAD, 18, 700));
    }
  }

  function legend(C, names, color, shape = "square", y0 = 44) {
    const {root, W} = C;
    const noteW = C.note ? tw(C.note, 10.5, 400) + 16 : 0;
    if (C.note) {
      root.append("text").attr("x", W - PAD).attr("y", y0 + 10).attr("text-anchor", "end").attr("font-size", 10.5)
        .attr("fill", "#6b7280").attr("font-family", SANS).text(C.note);
    }
    if (!names || names.length < 2) return y0 + (C.note ? 18 : 4);
    const g = root.append("g").attr("class", "qv-legend");
    const maxX = W - PAD - noteW, rowH = 18;
    let x = PAD, y = y0, rows = 1;
    names.forEach(n => {
      const label = clip(n, 170, 11.5, 600), w = 14 + tw(label, 11.5, 600) + 16;
      if (x + w > maxX && x > PAD) { x = PAD; y += rowH; rows++; }
      const it = g.append("g").attr("transform", `translate(${x},${y})`);
      title(it, n);
      if (shape === "line") it.append("rect").attr("y", 4).attr("width", 12).attr("height", 3).attr("rx", 1.5).attr("fill", color(n));
      else if (shape === "circle") it.append("circle").attr("cx", 5).attr("cy", 5.5).attr("r", 5).attr("fill", color(n));
      else it.append("rect").attr("width", 10).attr("height", 10).attr("y", 0.5).attr("fill", color(n));
      it.append("text").attr("x", 16).attr("y", 10).attr("font-size", 11.5).attr("font-weight", 600).attr("fill", "#333")
        .attr("font-family", SANS).text(label);
      x += w;
    });
    return y0 + rows * rowH;
  }

  function box(C, top, m) {
    const left = m.left, right = m.right ?? PAD, bottom = m.bottom;
    const iw = Math.max(40, C.W - left - right), ih = Math.max(40, H - top - bottom);
    const g = C.root.append("g").attr("class", "qv-plot").attr("transform", `translate(${left},${top})`);
    return {g, iw, ih, left, top, right, bottom};
  }

  function styleAxis(sel, font = 11) {
    sel.attr("class", "axis").selectAll("path,line").attr("stroke", AXIS);
    sel.selectAll("text").attr("fill", TICK).attr("font-weight", 600).attr("font-size", font).attr("font-family", SANS);
    return sel;
  }
  function grid(g, scale, iw, ih, dir, ticks = 5) {
    const ax = dir === "y" ? d3.axisLeft(scale).ticks(ticks).tickSize(-iw).tickFormat("") : d3.axisBottom(scale).ticks(ticks).tickSize(-ih).tickFormat("");
    const gl = g.append("g").attr("class", "grid-lines");
    if (dir === "x") gl.attr("transform", `translate(0,${ih})`);
    gl.call(ax);
    gl.select(".domain").remove();
    gl.selectAll("line").attr("stroke", GRID).attr("stroke-dasharray", "2,3");
    return gl;
  }
  function axisTitles(C, b, xT, yT) {
    if (yT) {
      C.root.append("text").attr("class", "qv-axis-title").attr("transform", `translate(${PAD + 4},${b.top + b.ih / 2}) rotate(-90)`)
        .attr("text-anchor", "middle").attr("dy", "0.71em").attr("font-size", 12.5).attr("font-weight", 700).attr("fill", "#000")
        .attr("font-family", SANS).text(clip(yT, b.ih, 12.5, 700));
    }
    if (xT) {
      C.root.append("text").attr("class", "qv-axis-title").attr("x", b.left + b.iw / 2).attr("y", H - 10).attr("text-anchor", "middle")
        .attr("font-size", 12.5).attr("font-weight", 700).attr("fill", "#000").attr("font-family", SANS).text(clip(xT, b.iw, 12.5, 700));
    }
  }
  function yTickW(scale, fmt, ticks = 5) { return d3.max(scale.ticks(ticks), t => tw(fmt(t), 11)) || 20; }
  const leftFor = (C, w) => PAD + (C.spec.yLabel ? 24 : 0) + w + 10;
  const bottomFor = (C, extra = 0) => 26 + extra + (C.spec.xLabel ? 24 : 0);

  function bandBottomAxis(g, x, ih, labels, maxW = 110) {
    const bw = x.step ? x.step() : x.bandwidth();
    const widest = d3.max(labels, l => tw(l, 11)) || 0;
    const rotate = widest > bw - 6;
    const ax = g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).tickSizeOuter(0));
    styleAxis(ax);
    const every = rotate ? Math.max(1, Math.ceil(14 / bw)) : 1;
    ax.selectAll(".tick").each(function (d, i) {
      const t = d3.select(this).select("text");
      title(t, d);
      if (i % every) { t.remove(); return; }
      t.text(clip(d, rotate ? maxW : bw - 4, 11));
      if (rotate) t.attr("transform", "rotate(-35)").attr("text-anchor", "end").attr("dx", "-0.4em").attr("dy", "0.5em");
    });
    return rotate ? Math.min(maxW, widest) * 0.6 + 8 : 0;
  }
  function pointBottomAxis(g, x, ih, labels, iw) {
    const widest = (d3.max(labels, l => tw(l, 11)) || 10) + 12;
    const every = Math.max(1, Math.ceil(widest * labels.length / iw));
    const ax = g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).tickSizeOuter(0));
    styleAxis(ax);
    ax.selectAll(".tick").each(function (d, i) {
      if (i % every && i !== labels.length - 1) d3.select(this).select("text").remove();
      else if (i !== labels.length - 1 && (labels.length - 1 - i) < every && (labels.length - 1) % every) d3.select(this).select("text").remove();
    });
  }
  function bandLeftAxis(g, y, labels, maxW) {
    const ax = g.append("g").call(d3.axisLeft(y).tickSizeOuter(0).tickSize(0).tickPadding(8));
    styleAxis(ax);
    ax.select(".domain").remove();
    ax.selectAll(".tick text").each(function (d) { title(d3.select(this).text(clip(d, maxW, 11)), d); });
    return ax;
  }
  const labelWidth = (labels, cap) => Math.min(cap, d3.max(labels, l => tw(l, 11)) || 0);

  function empty(C, msg) {
    C.root.append("text").attr("x", C.W / 2).attr("y", H / 2).attr("text-anchor", "middle").attr("fill", "#6b7280")
      .attr("font-size", 14).attr("font-family", SANS).text(msg || "No numbers to draw yet");
  }

  function sumBy(rows, key) {
    const m = new Map();
    rows.forEach(r => m.set(key(r), (m.get(key(r)) || 0) + r.v));
    return m;
  }
  function catValues(rows, maxN, positiveOnly) {
    let rs = rows.filter(r => Number.isFinite(r.v) && r.cat !== "");
    if (positiveOnly) rs = rs.filter(r => r.v > 0);
    const m = sumBy(rs, r => r.cat);
    let d = [...m].map(([cat, v]) => ({cat, v}));
    if (d.length > maxN + 1) {
      d.sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
      const rest = d.slice(maxN);
      d = d.slice(0, maxN);
      d.push({cat: OTHER, v: d3.sum(rest, e => e.v), n: rest.length});
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
  function lump(rows, field, max) {
    const names = uniq(rows.map(r => r[field]));
    const {keep, other} = capByTotal(names, sumBy(rows, r => r[field]), max);
    if (!other) return {rows, names};
    const k = new Set(keep);
    return {rows: rows.map(r => (k.has(r[field]) ? r : {...r, [field]: OTHER})), names: [...keep, OTHER], dropped: names.length - keep.length};
  }

  const R = {
    bar(C) {
      const {spec} = C;
      const d = catValues(C.rows, 12, false);
      if (!d.length) return empty(C);
      if (d.some(e => e.cat === OTHER)) C.note = `Top 12 shown, ${d.at(-1).n} more in Other`;
      const top = legend(C, [], null) + 8;
      const lo = Math.min(0, d3.min(d, e => e.v)), hi = Math.max(0, d3.max(d, e => e.v));
      const fmt = v => fmtShort(v, spec.unit);
      const widest = d3.max(d, e => tw(e.cat, 11));
      const horizontal = d.length > 8 || widest > Math.max(60, (C.W - 120) / d.length - 8);
      const color = e => (e.cat === OTHER ? OTHER_COLOR : e.v < 0 ? "#E53229" : PALETTE[0]);
      if (horizontal) {
        const lw = labelWidth(d.map(e => e.cat), Math.min(200, C.W * 0.3));
        const b = box(C, top, {left: PAD + lw + 10, bottom: bottomFor(C), right: PAD + 44});
        const x = d3.scaleLinear([lo, hi * 1.1 || 1], [0, b.iw]).nice(), y = d3.scaleBand(d.map(e => e.cat), [0, b.ih]).padding(0.28);
        grid(b.g, x, b.iw, b.ih, "x", 5);
        styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).ticks(5).tickFormat(fmt).tickSizeOuter(0)));
        const bars = b.g.selectAll("rect.bar").data(d).join("rect").attr("class", "bar").attr("fill", color).attr("y", e => y(e.cat))
          .attr("height", y.bandwidth()).attr("x", x(0)).attr("width", 0);
        bars.each(function (e) { title(d3.select(this), `${e.cat}: ${fmtFull(e.v, spec.unit)}`); });
        (C.anim ? bars.transition().duration(700).ease(d3.easeCubicOut) : bars).attr("x", e => x(Math.min(0, e.v))).attr("width", e => Math.abs(x(e.v) - x(0)));
        const fs = Math.max(9, Math.min(12, y.bandwidth() * 0.6));
        b.g.selectAll("text.bar-label").data(d).join("text").attr("class", "bar-label").attr("font-size", fs).attr("fill", "#555")
          .attr("font-weight", 500).attr("font-family", SANS).attr("y", e => y(e.cat) + y.bandwidth() / 2).attr("dy", "0.35em")
          .attr("x", e => x(e.v) + (e.v < 0 ? -5 : 5)).attr("text-anchor", e => (e.v < 0 ? "end" : "start")).text(e => fmt(e.v));
        bandLeftAxis(b.g, y, d.map(e => e.cat), lw);
        b.g.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y2", b.ih).attr("stroke", "#9ca3af");
        axisTitles(C, b, spec.yLabel, spec.xLabel);
      } else {
        const x0 = d3.scaleLinear([lo * 1.1, hi * 1.15 || 1], [300, 0]).nice();
        const b = box(C, top, {left: leftFor(C, yTickW(x0, fmt)), bottom: bottomFor(C, 30)});
        const x = d3.scaleBand(d.map(e => e.cat), [0, b.iw]).paddingInner(0.38).paddingOuter(0.14);
        const y = x0.range([b.ih, 0]);
        grid(b.g, y, b.iw, b.ih, "y", 5);
        styleAxis(b.g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmt).tickSizeOuter(0))).select(".domain").remove();
        const bars = b.g.selectAll("rect.bar").data(d).join("rect").attr("class", "bar").attr("fill", color).attr("x", e => x(e.cat))
          .attr("width", x.bandwidth()).attr("y", y(0)).attr("height", 0);
        bars.each(function (e) { title(d3.select(this), `${e.cat}: ${fmtFull(e.v, spec.unit)}`); });
        (C.anim ? bars.transition().duration(700).ease(d3.easeCubicOut) : bars).attr("y", e => y(Math.max(0, e.v))).attr("height", e => Math.abs(y(e.v) - y(0)));
        const fs = Math.max(9, Math.min(12, x.bandwidth() * 0.3));
        b.g.selectAll("text.bar-label").data(d).join("text").attr("class", "bar-label").attr("font-size", fs).attr("fill", "#555")
          .attr("font-weight", 500).attr("font-family", SANS).attr("text-anchor", "middle").attr("x", e => x(e.cat) + x.bandwidth() / 2)
          .attr("y", e => (e.v < 0 ? y(e.v) + fs + 3 : y(e.v) - 5)).text(e => fmt(e.v));
        bandBottomAxis(b.g, x, b.ih, d.map(e => e.cat), 90);
        b.g.append("line").attr("x2", b.iw).attr("y1", y(0)).attr("y2", y(0)).attr("stroke", "#9ca3af");
        axisTitles(C, b, spec.xLabel, spec.yLabel);
      }
    },

    line(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.t !== "").map(r => ({...r, series: r.series || spec.yLabel || "Value"}));
      if (!rows.length) return empty(C);
      const ts = uniq(rows.map(r => r.t));
      let names = uniq(rows.map(r => r.series));
      if (names.length > 8) {
        const {keep} = capByTotal(names, sumBy(rows, r => r.series), 8);
        C.note = `Top 8 of ${names.length} series`;
        names = keep;
      }
      const get = pivot(rows, r => r.series, r => r.t);
      const series = names.map(s => ({s, pts: ts.map(t => ({t, v: get(s, t)}))}));
      const all = series.flatMap(e => e.pts.map(p => p.v)).filter(v => v !== undefined);
      const color = makeColor(names);
      const top = legend(C, names, color, "line") + 10;
      const [mn, mx] = d3.extent(all);
      const pad = (mx - mn) * 0.05 || Math.abs(mx) * 0.1 || 1;
      const fmt = v => fmtShort(v, spec.unit);
      const y0 = d3.scaleLinear([mn >= 0 && mn < (mx - mn) * 0.6 ? 0 : mn - pad, mx + pad], [300, 0]).nice();
      const b = box(C, top, {left: leftFor(C, yTickW(y0, fmt)), bottom: bottomFor(C), right: PAD + 8});
      const x = d3.scalePoint(ts, [0, b.iw]).padding(0.1), y = y0.range([b.ih, 0]);
      grid(b.g, y, b.iw, b.ih, "y", 5);
      styleAxis(b.g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmt).tickSizeOuter(0))).select(".domain").remove();
      pointBottomAxis(b.g, x, b.ih, ts, b.iw);
      if (y.domain()[0] < 0) b.g.append("line").attr("x2", b.iw).attr("y1", y(0)).attr("y2", y(0)).attr("stroke", "#9ca3af");
      const line = d3.line().defined(p => p.v !== undefined).x(p => x(p.t)).y(p => y(p.v)).curve(d3.curveMonotoneX);
      const dotR = ts.length > 40 ? 0 : Math.max(2.5, Math.min(4.5, b.iw / ts.length * 0.15));
      series.forEach(e => {
        const path = b.g.append("path").datum(e.pts).attr("fill", "none").attr("stroke", color(e.s)).attr("stroke-width", 2.4)
          .attr("stroke-linejoin", "round").attr("stroke-linecap", "round").attr("d", line);
        if (C.anim) {
          const L = path.node().getTotalLength();
          path.attr("stroke-dasharray", `${L} ${L}`).attr("stroke-dashoffset", L).transition().duration(800).ease(d3.easeCubicOut)
            .attr("stroke-dashoffset", 0).on("end", function () { d3.select(this).attr("stroke-dasharray", null); });
        }
        if (dotR) b.g.selectAll(null).data(e.pts.filter(p => p.v !== undefined)).join("circle").attr("cx", p => x(p.t)).attr("cy", p => y(p.v))
          .attr("r", dotR).attr("fill", "#fff").attr("stroke", color(e.s)).attr("stroke-width", 1.6)
          .each(function (p) { title(d3.select(this), `${e.s}, ${p.t}: ${fmtFull(p.v, spec.unit)}`); });
      });
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
      const color = makeColor(names);
      const top = legend(C, names, color, "square") + 10;
      const fmt = v => fmtShort(v, spec.unit);
      const lo = d3.min(stack, s => d3.min(s, p => p[0])), hi = d3.max(stack, s => d3.max(s, p => p[1]));
      const y0 = d3.scaleLinear([Math.min(0, lo), hi * 1.05 || 1], [300, 0]).nice();
      const b = box(C, top, {left: leftFor(C, yTickW(y0, fmt)), bottom: bottomFor(C), right: PAD + 8});
      const x = d3.scalePoint(ts, [0, b.iw]), y = y0.range([b.ih, 0]);
      grid(b.g, y, b.iw, b.ih, "y", 5);
      const area = d3.area().x(p => x(p.data.t)).y0(p => y(p[0])).y1(p => y(p[1])).curve(d3.curveMonotoneX);
      const paths = b.g.selectAll("path.area").data(stack).join("path").attr("class", "area").attr("fill", s => color(s.key))
        .attr("fill-opacity", 0.88).attr("stroke", "#fff").attr("stroke-width", 0.8).attr("d", area);
      paths.each(function (s) { title(d3.select(this), s.key); });
      if (C.anim) {
        const flat = d3.area().x(p => x(p.data.t)).y0(y(0)).y1(y(0)).curve(d3.curveMonotoneX);
        paths.attr("d", flat).transition().duration(700).ease(d3.easeCubicOut).attr("d", area);
      }
      styleAxis(b.g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmt).tickSizeOuter(0))).select(".domain").remove();
      pointBottomAxis(b.g, x, b.ih, ts, b.iw);
      axisTitles(C, b, spec.xLabel, spec.yLabel);
    },

    stacked_bar(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.v > 0 && r.cat !== "").map(r => ({...r, series: r.series || "Value"}));
      if (!rows.length) return empty(C);
      const LS = lump(rows, "series", 7);
      rows = LS.rows;
      const LC = lump(rows, "cat", 14);
      rows = LC.rows;
      if (LC.dropped) C.note = `Top 14 shown, ${LC.dropped} more in Other`;
      const names = LS.names, cats = LC.names, get = pivot(rows, r => r.cat, r => r.series);
      const table = cats.map(c => {
        const o = {cat: c}, tot = d3.sum(names, s => get(c, s) || 0) || 1;
        names.forEach(s => (o[s] = (get(c, s) || 0) / tot * 100));
        o.__tot = tot;
        return o;
      });
      const stack = d3.stack().keys(names)(table);
      const color = makeColor(names);
      const top = legend(C, names, color, "square") + 10;
      const lw = labelWidth(cats, Math.min(200, C.W * 0.3));
      const b = box(C, top, {left: PAD + (spec.xLabel ? 24 : 0) + lw + 10, bottom: 26 + (spec.yLabel ? 24 : 0), right: PAD + 6});
      const y = d3.scaleBand(cats, [0, b.ih]).padding(0.24), x = d3.scaleLinear([0, 100], [0, b.iw]);
      grid(b.g, x, b.iw, b.ih, "x", 5);
      styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).ticks(5).tickFormat(v => v + "%").tickSizeOuter(0)));
      const segs = b.g.selectAll("g.s").data(stack).join("g").attr("class", "s").attr("fill", s => color(s.key))
        .selectAll("rect").data(s => s.map(p => ((p.key = s.key), p))).join("rect").attr("y", p => y(p.data.cat)).attr("height", y.bandwidth())
        .attr("stroke", "#fff").attr("stroke-width", 1);
      segs.each(function (p) { title(d3.select(this), `${p.data.cat}, ${p.key}: ${d3.format(".1f")(p[1] - p[0])}% (${fmtFull((p[1] - p[0]) / 100 * p.data.__tot, spec.unit)})`); });
      (C.anim ? segs.attr("x", 0).attr("width", 0).transition().duration(700).ease(d3.easeCubicOut) : segs)
        .attr("x", p => x(p[0])).attr("width", p => Math.max(0, x(p[1]) - x(p[0])));
      const fs = Math.max(9, Math.min(11, y.bandwidth() * 0.55));
      b.g.selectAll("text.seg").data(stack.flatMap(s => s.filter(p => x(p[1]) - x(p[0]) > tw("100%", fs) + 6))).join("text").attr("class", "seg")
        .attr("x", p => (x(p[0]) + x(p[1])) / 2).attr("y", p => y(p.data.cat) + y.bandwidth() / 2).attr("dy", "0.35em").attr("text-anchor", "middle")
        .attr("font-size", fs).attr("font-weight", 600).attr("fill", "#fff").attr("font-family", SANS).text(p => Math.round(p[1] - p[0]) + "%");
      bandLeftAxis(b.g, y, cats, lw);
      axisTitles(C, b, spec.yLabel ? "Share of " + spec.yLabel.replace(/^share of /i, "") : "", spec.xLabel);
    },

    scatter(C) {
      const {spec} = C;
      let rows = C.rows.map(r => ({...r, v2: num(r.v2)})).filter(r => Number.isFinite(r.v) && Number.isFinite(r.v2));
      if (!rows.length) return empty(C);
      const hasSeries = rows.some(r => r.series);
      rows = rows.map(r => ({...r, series: r.series || "Items"}));
      const counts = new Map();
      rows.forEach(r => counts.set(r.series, (counts.get(r.series) || 0) + 1));
      const names0 = uniq(rows.map(r => r.series)), cap = capByTotal(names0, counts, 8);
      if (cap.other) { const k = new Set(cap.keep); rows = rows.map(r => (k.has(r.series) ? r : {...r, series: OTHER})); }
      const names = cap.other ? [...cap.keep, OTHER] : names0;
      const color = makeColor(names);
      const top = legend(C, hasSeries ? names : [], color, "circle") + 10;
      const ext = (a, f) => { const [lo, hi] = d3.extent(a, f), p = (hi - lo) * 0.05 || Math.abs(hi) * 0.1 || 1; return [lo - p, hi + p]; };
      const fy = v => fmtShort(v, spec.unit);
      const y0 = d3.scaleLinear(ext(rows, r => r.v2), [300, 0]).nice();
      const b = box(C, top, {left: leftFor(C, yTickW(y0, fy)), bottom: bottomFor(C), right: PAD + 8});
      const x = d3.scaleLinear(ext(rows, r => r.v), [0, b.iw]).nice(), y = y0.range([b.ih, 0]);
      grid(b.g, y, b.iw, b.ih, "y", 5);
      grid(b.g, x, b.iw, b.ih, "x", 6);
      styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).ticks(6).tickFormat(short).tickSizeOuter(0)));
      styleAxis(b.g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fy).tickSizeOuter(0))).select(".domain").remove();
      const r = rows.length > 600 ? 2.2 : rows.length > 150 ? 3.5 : 5;
      const dots = b.g.append("g").selectAll("circle").data(rows).join("circle").attr("cx", e => x(e.v)).attr("cy", e => y(e.v2))
        .attr("fill", e => color(e.series)).attr("fill-opacity", 0.72).attr("stroke", "#fff").attr("stroke-width", rows.length > 600 ? 0 : 0.8);
      dots.each(function (e) { title(d3.select(this), `${e.cat ? e.cat + ", " : ""}${hasSeries ? e.series + ": " : ""}${full(e.v)}, ${fmtFull(e.v2, spec.unit)}`); });
      (C.anim ? dots.attr("r", 0).transition().duration(500).delay((e, i) => Math.min(400, i * 4)) : dots).attr("r", r);
      axisTitles(C, b, spec.xLabel, spec.yLabel);
    },

    histogram(C) {
      const {spec} = C;
      const vals = C.rows.map(r => r.v).filter(Number.isFinite);
      if (!vals.length) return empty(C);
      const [lo, hi] = d3.extent(vals);
      const x0 = d3.scaleLinear(lo === hi ? [lo - 1, hi + 1] : [lo, hi]).nice();
      const nb = Math.max(6, Math.min(30, Math.ceil(Math.log2(vals.length) + 1) * 2));
      const bins = d3.bin().domain(x0.domain()).thresholds(x0.ticks(nb))(vals);
      const top = legend(C, [], null) + 10;
      const y0 = d3.scaleLinear([0, d3.max(bins, e => e.length) * 1.1], [300, 0]).nice();
      const b = box(C, top, {left: leftFor(C, yTickW(y0, short)), bottom: bottomFor(C), right: PAD + 8});
      const x = x0.range([0, b.iw]), y = y0.range([b.ih, 0]);
      grid(b.g, y, b.iw, b.ih, "y", 5);
      const bars = b.g.selectAll("rect").data(bins).join("rect").attr("x", e => x(e.x0) + 0.5).attr("width", e => Math.max(0, x(e.x1) - x(e.x0) - 1))
        .attr("fill", PALETTE[0]).attr("y", y(0)).attr("height", 0);
      bars.each(function (e) { title(d3.select(this), `${fmtFull(e.x0, spec.unit)} to ${fmtFull(e.x1, spec.unit)}: ${e.length}`); });
      (C.anim ? bars.transition().duration(700).ease(d3.easeCubicOut) : bars).attr("y", e => y(e.length)).attr("height", e => y(0) - y(e.length));
      styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).ticks(Math.min(10, b.iw / 70)).tickFormat(v => fmtShort(v, spec.unit)).tickSizeOuter(0)));
      styleAxis(b.g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(short).tickSizeOuter(0))).select(".domain").remove();
      axisTitles(C, b, spec.xLabel, spec.yLabel || "Count");
    },

    heatmap(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.cat !== "" && str(r.series) !== "");
      if (!rows.length) return empty(C);
      let cats = uniq(rows.map(r => r.cat)), cols = uniq(rows.map(r => r.series));
      const note = [];
      if (cats.length > 24) { note.push(`first 24 of ${cats.length} rows`); cats = cats.slice(0, 24); }
      if (cols.length > 36) { note.push(`first 36 of ${cols.length} columns`); cols = cols.slice(0, 36); }
      if (note.length) C.note = "Showing " + note.join(", ");
      const get = pivot(rows, r => r.cat, r => r.series);
      const cells = cats.flatMap(c => cols.map(s => ({c, s, v: get(c, s)})));
      const vs = cells.map(e => e.v).filter(v => v !== undefined);
      const [mn, mx] = d3.extent(vs);
      const diverging = mn < 0 && mx > 0;
      let scale, tOf;
      if (diverging) {
        const m = Math.max(-mn, mx);
        tOf = v => (v + m) / (2 * m);
        scale = v => d3.interpolateRdBu(1 - tOf(v));
      } else {
        const ramp = d3.interpolateRgbBasis(["#ffffff", "rgb(155,137,196)", "rgb(45,27,142)"]);
        tOf = v => (mx === mn ? 0.6 : (v - mn) / (mx - mn));
        scale = v => ramp(0.08 + 0.87 * tOf(v));
      }
      const legY = 44 + (C.note ? 16 : 0);
      if (C.note) legend(C, [], null);
      const gradW = Math.min(220, C.W * 0.35);
      const lg = C.root.append("g").attr("transform", `translate(${PAD},${legY})`);
      const gid = "qvgrad" + Math.random().toString(36).slice(2, 8);
      const grad = C.root.append("defs").append("linearGradient").attr("id", gid);
      d3.range(0, 1.0001, 0.05).forEach(t => grad.append("stop").attr("offset", t).attr("stop-color", scale(mn + t * (mx - mn))));
      lg.append("rect").attr("width", gradW).attr("height", 10).attr("rx", 2).attr("fill", `url(#${gid})`);
      [[0, mn, "start"], [gradW, mx, "end"]].forEach(([xx, v, a]) => lg.append("text").attr("x", xx).attr("y", 24).attr("text-anchor", a)
        .attr("font-size", 10.5).attr("font-weight", 600).attr("fill", TICK).attr("font-family", SANS).text(fmtShort(v, spec.unit)));
      if (spec.yLabel) lg.append("text").attr("x", gradW + 10).attr("y", 9.5).attr("font-size", 11).attr("font-weight", 600).attr("fill", "#333")
        .attr("font-family", SANS).text(clip(spec.yLabel, C.W - gradW - 60, 11));
      const top = legY + 36;
      const lw = labelWidth(cats, Math.min(180, C.W * 0.28));
      const colW = d3.max(cols, s => tw(s, 11)) || 0;
      const est = (C.W - lw - 2 * PAD) / cols.length;
      const rot = colW > est - 4;
      const bottom = 20 + (rot ? Math.min(80, colW) * 0.6 + 8 : 0) + (spec.xLabel ? 24 : 0);
      const b = box(C, top, {left: PAD + lw + 10, bottom, right: PAD});
      const x = d3.scaleBand(cols, [0, b.iw]).padding(0.04), y = d3.scaleBand(cats, [0, b.ih]).padding(0.04);
      const rects = b.g.selectAll("rect.cell").data(cells).join("rect").attr("class", "cell").attr("x", e => x(e.s)).attr("y", e => y(e.c))
        .attr("width", x.bandwidth()).attr("height", y.bandwidth()).attr("rx", 1.5).attr("fill", e => (e.v === undefined ? "#eceef1" : scale(e.v)));
      rects.each(function (e) { title(d3.select(this), `${e.c}, ${e.s}: ${e.v === undefined ? "no data" : fmtFull(e.v, spec.unit)}`); });
      if (C.anim) rects.attr("opacity", 0).transition().duration(500).delay((e, i) => (i % cols.length) * 12).attr("opacity", 1);
      const fs = Math.min(11, y.bandwidth() * 0.5);
      if (fs >= 8 && x.bandwidth() >= tw("888k", fs) + 4) {
        b.g.selectAll("text.cv").data(cells.filter(e => e.v !== undefined)).join("text").attr("class", "cv")
          .attr("x", e => x(e.s) + x.bandwidth() / 2).attr("y", e => y(e.c) + y.bandwidth() / 2).attr("dy", "0.35em").attr("text-anchor", "middle")
          .attr("font-size", fs).attr("font-weight", 400).attr("font-family", SANS)
          .attr("fill", e => (diverging ? Math.abs(tOf(e.v) - 0.5) > 0.3 : tOf(e.v) > 0.5) ? "#fff" : INK).text(e => short(e.v)).style("pointer-events", "none");
      }
      bandLeftAxis(b.g, y, cats, lw);
      const ax = b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).tickSize(0).tickPadding(6));
      styleAxis(ax).select(".domain").remove();
      ax.selectAll(".tick text").each(function (d) {
        const t = d3.select(this).text(clip(d, rot ? 80 : x.bandwidth(), 11));
        title(t, d);
        if (rot) t.attr("transform", "rotate(-35)").attr("text-anchor", "end").attr("dx", "-0.2em").attr("dy", "0.4em");
      });
      if (spec.xLabel) C.root.append("text").attr("x", b.left + b.iw / 2).attr("y", H - 10).attr("text-anchor", "middle").attr("font-size", 12.5)
        .attr("font-weight", 700).attr("fill", "#000").attr("font-family", SANS).text(clip(spec.xLabel, b.iw, 12.5, 700));
    },

    treemap(C) {
      const {spec} = C;
      const d = catValues(C.rows, 12, true);
      if (!d.length) return empty(C, "Treemaps need positive numbers");
      if (d.some(e => e.cat === OTHER)) C.note = `Top 12 shown, ${d.at(-1).n} more in Other`;
      const top = legend(C, [], null) + 8;
      const b = box(C, top, {left: PAD, bottom: PAD, right: PAD});
      const root = d3.hierarchy({children: d}).sum(e => e.v || 0).sort((a, b2) => (a.data.cat === OTHER) - (b2.data.cat === OTHER) || b2.value - a.value);
      d3.treemap().size([b.iw, b.ih]).paddingInner(2).round(true)(root);
      const color = makeColor(root.leaves().map(l => l.data.cat));
      const total = root.value;
      const n = b.g.selectAll("g.leaf").data(root.leaves()).join("g").attr("class", "leaf").attr("transform", e => `translate(${e.x0},${e.y0})`);
      n.each(function (e) { title(d3.select(this), `${e.data.cat}: ${fmtFull(e.value, spec.unit)} (${d3.format(".1%")(e.value / total)})`); });
      n.append("rect").attr("width", e => e.x1 - e.x0).attr("height", e => e.y1 - e.y0).attr("fill", e => color(e.data.cat));
      n.each(function (e) {
        const w = e.x1 - e.x0, h = e.y1 - e.y0, g = d3.select(this);
        if (w < 34 || h < 20) return;
        const fs = Math.max(10, Math.min(15, Math.sqrt(w * h) / 9));
        g.append("text").attr("x", 7).attr("y", 7 + fs).attr("font-size", fs).attr("font-weight", 700).attr("fill", "#fff").attr("font-family", SANS)
          .text(clip(e.data.cat, w - 12, fs, 700));
        if (h > fs * 2 + 18) g.append("text").attr("x", 7).attr("y", 11 + fs * 2.1).attr("font-size", fs * 0.82).attr("font-weight", 500)
          .attr("fill", "#fff").attr("fill-opacity", 0.9).attr("font-family", SANS)
          .text(clip(`${fmtShort(e.value, spec.unit)} / ${d3.format(".0%")(e.value / total)}`, w - 12, fs * 0.82, 500));
      });
      if (C.anim) n.attr("opacity", 0).transition().duration(450).delay((e, i) => i * 30).attr("opacity", 1);
    },

    donut(C) {
      const {spec} = C;
      const d = catValues(C.rows, 5, true);
      if (!d.length) return empty(C, "Donuts need positive numbers");
      if (d.some(e => e.cat === OTHER)) C.note = `Top 5 shown, ${d.at(-1).n} more in Other`;
      const top = legend(C, [], null) + 8;
      const b = box(C, top, {left: PAD, bottom: PAD, right: PAD});
      const total = d3.sum(d, e => e.v), color = makeColor(d.map(e => e.cat));
      const rad = Math.min(b.ih / 2, b.iw * 0.28);
      const cx = Math.min(b.iw * 0.32, rad + 30), cy = b.ih / 2;
      const arcs = d3.pie().value(e => e.v).sort(null).padAngle(0.012)(d);
      const arc = d3.arc().innerRadius(rad * 0.6).outerRadius(rad).cornerRadius(2);
      const c = b.g.append("g").attr("transform", `translate(${cx},${cy})`);
      const paths = c.selectAll("path").data(arcs).join("path").attr("fill", a => color(a.data.cat)).attr("d", arc);
      paths.each(function (a) { title(d3.select(this), `${a.data.cat}: ${fmtFull(a.data.v, spec.unit)} (${d3.format(".1%")(a.data.v / total)})`); });
      if (C.anim) paths.transition().duration(700).ease(d3.easeCubicOut).attrTween("d", a => { const i = d3.interpolate({startAngle: a.startAngle, endAngle: a.startAngle}, a); return t => arc(i(t)); });
      c.append("text").attr("text-anchor", "middle").attr("dy", "0.1em").attr("font-family", SERIF).attr("font-size", Math.max(16, rad * 0.26))
        .attr("font-weight", 700).attr("fill", INK).text(fmtShort(total, spec.unit));
      c.append("text").attr("text-anchor", "middle").attr("dy", "1.9em").attr("font-size", 11.5).attr("font-weight", 600).attr("fill", TICK)
        .attr("font-family", SANS).text(clip(spec.yLabel ? "Total " + spec.yLabel : "Total", rad * 1.1, 11.5));
      const lx = cx + rad + 40, rowH = Math.min(44, b.ih / d.length);
      const lwAvail = b.iw - lx - 10;
      const lg = b.g.append("g").attr("transform", `translate(${lx},${cy - (rowH * d.length) / 2})`);
      d.forEach((e, i) => {
        const it = lg.append("g").attr("transform", `translate(0,${i * rowH})`);
        title(it, e.cat);
        it.append("rect").attr("y", 4).attr("width", 12).attr("height", 12).attr("fill", color(e.cat));
        it.append("text").attr("x", 20).attr("y", 15).attr("font-size", 13).attr("font-weight", 600).attr("fill", "#333").attr("font-family", SANS)
          .text(clip(e.cat, lwAvail - 20, 13));
        it.append("text").attr("x", 20).attr("y", 31).attr("font-size", 12).attr("fill", TICK).attr("font-family", SANS)
          .text(`${d3.format(".1%")(e.v / total)} / ${fmtShort(e.v, spec.unit)}`);
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
      const top = legend(C, [], null) + 8;
      const srcNames = uniq(pairs.map(p => p.s)), dstNames = uniq(pairs.map(p => p.t));
      const lwL = labelWidth(srcNames, 150) + 8, lwR = labelWidth(dstNames, 150) + 8;
      const b = box(C, top, {left: PAD + lwL, bottom: PAD + 4, right: PAD + lwR});
      function layout(shared) {
        const id = (side, n) => (shared ? n : side + n);
        const names = uniq(pairs.flatMap(p => [id("s:", p.s), id("t:", p.t)]));
        const idx = new Map(names.map((n, i) => [n, i]));
        const links = pairs.filter(p => !shared || p.s !== p.t).map(p => ({source: idx.get(id("s:", p.s)), target: idx.get(id("t:", p.t)), value: p.v}));
        const nodes = names.map(n => ({id: n, name: shared ? n : n.slice(2)}));
        const n = Math.max(srcNames.length, dstNames.length);
        return d3.sankey().nodeWidth(12).nodePadding(Math.max(4, Math.min(14, b.ih / n / 3))).nodeSort(null)
          .extent([[0, 0], [b.iw, b.ih]])({nodes, links});
      }
      const overlap = srcNames.some(n => dstNames.includes(n));
      let sk;
      if (overlap) { try { sk = layout(true); } catch (e) { sk = null; } }
      if (!sk) sk = layout(false);
      const color = makeColor(sk.nodes.filter(n => n.sourceLinks.length).map(n => n.name));
      const nodeColor = n => (n.sourceLinks.length ? color(n.name) : "#475569");
      const links = b.g.append("g").attr("fill", "none").selectAll("path").data(sk.links).join("path").attr("d", d3.sankeyLinkHorizontal())
        .attr("stroke", l => color(l.source.name)).attr("stroke-opacity", 0.38).attr("stroke-width", l => Math.max(1, l.width));
      links.each(function (l) { title(d3.select(this), `${l.source.name} to ${l.target.name}: ${fmtFull(l.value, spec.unit)}`); });
      if (C.anim) links.attr("stroke-opacity", 0).transition().duration(600).delay(150).attr("stroke-opacity", 0.38);
      const nodes = b.g.selectAll("rect.node").data(sk.nodes).join("rect").attr("class", "node").attr("x", n => n.x0).attr("y", n => n.y0)
        .attr("width", n => n.x1 - n.x0).attr("height", n => Math.max(1, n.y1 - n.y0)).attr("fill", nodeColor);
      nodes.each(function (n) { title(d3.select(this), `${n.name}: ${fmtFull(n.value, spec.unit)}`); });
      const maxX = d3.max(sk.nodes, n => n.x1);
      b.g.selectAll("text.n").data(sk.nodes.filter(n => n.y1 - n.y0 >= 9 || sk.nodes.length < 16)).join("text").attr("class", "n")
        .attr("x", n => (n.x0 < 1 ? -6 : n.x1 >= maxX - 1 ? n.x1 + 6 : n.x1 + 6)).attr("y", n => (n.y0 + n.y1) / 2).attr("dy", "0.35em")
        .attr("text-anchor", n => (n.x0 < 1 ? "end" : "start")).attr("font-size", 11.5).attr("font-weight", 600).attr("fill", "#333")
        .attr("font-family", SANS).text(n => clip(n.name, 150, 11.5));
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
        C.note = `Top 10 of ${cats.length} by average rank`;
        cats = cats.filter(c => keep.has(c));
      }
      const get = new Map(rows.map(r => [r.cat + "\u0000" + r.t, r.v]));
      const series = cats.map(c => ({c, pts: ts.map(t => ({t, v: get.get(c + "\u0000" + t)}))}));
      const maxRank = Math.max(cats.length, Math.ceil(d3.max(series.flatMap(s => s.pts), p => (p.v === undefined || p.v > 25 ? NaN : p.v)) || 1));
      const color = makeColor(cats);
      const top = legend(C, [], null) + 12;
      const lastOf = s => s.pts.filter(p => p.v !== undefined).at(-1), firstOf = s => s.pts.find(p => p.v !== undefined);
      const lwR = labelWidth(cats, 150) + 14, lwL = labelWidth(cats, 120) + 14;
      const b = box(C, top, {left: PAD + (spec.yLabel ? 24 : 0) + 26 + lwL, bottom: bottomFor(C), right: PAD + lwR});
      const x = d3.scalePoint(ts, [0, b.iw]).padding(0.15), y = d3.scaleLinear([1, maxRank], [0, b.ih]);
      const dens = cats.length > 7 ? 0.75 : 1;
      d3.range(1, maxRank + 1).forEach(k => b.g.append("line").attr("x2", b.iw).attr("y1", y(k)).attr("y2", y(k)).attr("stroke", GRID).attr("stroke-dasharray", "2,3"));
      const ay = b.g.append("g").attr("transform", `translate(${-lwL},0)`).call(d3.axisLeft(y).tickValues(d3.range(1, maxRank + 1, maxRank > 15 ? 2 : 1)).tickFormat(k => "#" + k).tickSize(0).tickPadding(8));
      styleAxis(ay).select(".domain").remove();
      pointBottomAxis(b.g, x, b.ih + 10, ts, b.iw);
      b.g.select(".axis .domain").remove();
      series.forEach(s => {
        const g = b.g.append("g");
        title(g, s.c);
        const vis = s.pts.filter(p => p.v !== undefined && p.v <= maxRank);
        const path = g.append("path").datum(s.pts).attr("fill", "none").attr("stroke", color(s.c)).attr("stroke-width", 3.5 * dens)
          .attr("stroke-linecap", "round").attr("d", d3.line().defined(p => p.v !== undefined && p.v <= maxRank).x(p => x(p.t)).y(p => y(p.v)).curve(d3.curveBumpX));
        if (C.anim) {
          const L = path.node().getTotalLength();
          path.attr("stroke-dasharray", `${L} ${L}`).attr("stroke-dashoffset", L).transition().duration(900).ease(d3.easeCubicOut)
            .attr("stroke-dashoffset", 0).on("end", function () { d3.select(this).attr("stroke-dasharray", null); });
        }
        g.selectAll("circle").data(vis).join("circle").attr("cx", p => x(p.t)).attr("cy", p => y(p.v)).attr("r", 5 * dens).attr("fill", color(s.c))
          .attr("stroke", "#fff").attr("stroke-width", 1.2).each(function (p) { title(d3.select(this), `${s.c}, ${p.t}: #${p.v}`); });
      });
      const side = (pick, xOff, anchor) => {
        const items = series.map(s => ({s, p: pick(s)})).filter(e => e.p && e.p.v <= maxRank).sort((a, b2) => a.p.v - b2.p.v);
        const ys = declump(items.map(e => y(e.p.v)), 0, b.ih, 13);
        items.forEach((e, i) => b.g.append("text").attr("x", x(e.p.t) + xOff).attr("y", ys[i]).attr("dy", "0.35em").attr("text-anchor", anchor)
          .attr("font-size", 11.5).attr("font-weight", 600).attr("fill", color(e.s.c)).attr("font-family", SANS).text(clip(e.s.c, 140, 11.5)));
      };
      side(lastOf, 10, "start");
      side(firstOf, -10, "end");
      axisTitles(C, b, spec.xLabel, spec.yLabel || "Rank");
    },

    dot_range(C) {
      const {spec} = C;
      let rows = C.rows.filter(r => Number.isFinite(r.v) && r.cat !== "");
      if (!rows.length) return empty(C);
      const S = uniq(rows.map(r => str(r.series) || "Value")).slice(0, 2);
      rows = rows.filter(r => S.includes(str(r.series) || "Value"));
      let cats = uniq(rows.map(r => r.cat));
      if (cats.length > 20) { C.note = `First 20 of ${cats.length} shown`; cats = cats.slice(0, 20); }
      const get = pivot(rows, r => r.cat, r => str(r.series) || "Value");
      const d = cats.map(c => ({c, a: get(c, S[0]), b: get(c, S[1])}));
      const color = makeColor(S);
      const top = legend(C, S, color, "circle") + 10;
      const vals = d.flatMap(e => [e.a, e.b]).filter(v => v !== undefined);
      const [lo, hi] = d3.extent(vals), p = (hi - lo) * 0.06 || Math.abs(hi) * 0.1 || 1;
      const lw = labelWidth(cats, Math.min(200, C.W * 0.3));
      const b = box(C, top, {left: PAD + (spec.xLabel ? 24 : 0) + lw + 10, bottom: 26 + (spec.yLabel ? 24 : 0), right: PAD + 10});
      const x = d3.scaleLinear([lo - p, hi + p], [0, b.iw]).nice(), y = d3.scaleBand(cats, [0, b.ih]).padding(0.5);
      grid(b.g, x, b.iw, b.ih, "x", 6);
      styleAxis(b.g.append("g").attr("transform", `translate(0,${b.ih})`).call(d3.axisBottom(x).ticks(6).tickFormat(v => fmtShort(v, spec.unit)).tickSizeOuter(0)));
      const r = Math.max(3.5, Math.min(7, y.step() * 0.28));
      const row = b.g.selectAll("g.r").data(d).join("g").attr("class", "r").attr("transform", e => `translate(0,${y(e.c) + y.bandwidth() / 2})`);
      row.each(function (e) { title(d3.select(this), `${e.c}: ${S[0]} ${e.a === undefined ? "n/a" : fmtFull(e.a, spec.unit)}, ${S[1] || ""} ${e.b === undefined ? "n/a" : fmtFull(e.b, spec.unit)}`); });
      const both = e => e.a !== undefined && e.b !== undefined;
      const lines = row.filter(both).append("line").attr("stroke", "#c3c8d0").attr("stroke-width", Math.max(2, r * 0.5)).attr("stroke-linecap", "round");
      const ca = row.filter(e => e.a !== undefined).append("circle").attr("r", r).attr("fill", color(S[0]));
      const cb = row.filter(e => e.b !== undefined).append("circle").attr("r", r).attr("fill", color(S[1]));
      if (C.anim) {
        const mid = e => x(both(e) ? (e.a + e.b) / 2 : e.a ?? e.b);
        lines.attr("x1", mid).attr("x2", mid); ca.attr("cx", mid); cb.attr("cx", mid);
        lines.transition().duration(700).ease(d3.easeCubicOut).attr("x1", e => x(e.a)).attr("x2", e => x(e.b));
        ca.transition().duration(700).ease(d3.easeCubicOut).attr("cx", e => x(e.a));
        cb.transition().duration(700).ease(d3.easeCubicOut).attr("cx", e => x(e.b));
      } else {
        lines.attr("x1", e => x(e.a)).attr("x2", e => x(e.b)); ca.attr("cx", e => x(e.a)); cb.attr("cx", e => x(e.b));
      }
      bandLeftAxis(b.g, y, cats, lw);
      axisTitles(C, b, spec.yLabel, spec.xLabel);
    },
  };

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

  function widthOf(svgEl) {
    const w = svgEl.getBoundingClientRect().width || (svgEl.parentNode && svgEl.parentNode.clientWidth) || 820;
    return Math.max(320, Math.round(w));
  }

  function render(svgEl, spec) {
    if (!svgEl) return;
    spec = spec || {};
    const st = svgEl.__qv || (svgEl.__qv = {});
    const W = widthOf(svgEl);
    const changed = st.kind !== spec.kind;
    st.spec = spec; st.kind = spec.kind; st.w = W;
    const svg = d3.select(svgEl).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`)
      .attr("xmlns", "http://www.w3.org/2000/svg").attr("font-family", SANS).classed("qv-chart", true);
    svg.selectAll("*").interrupt();
    svg.selectAll("*").remove();
    const root = svg.append("g").attr("class", "qv-root");
    root.append("rect").attr("class", "qv-bg").attr("width", W).attr("height", H).attr("fill", "#fff");
    const C = {root, spec, rows: cleanRows(spec.rows), W, anim: changed, note: ""};
    header(C);
    if (!R[spec.kind]) empty(C, spec.kind ? `Unknown chart type "${spec.kind}"` : "Describe your data to see a chart");
    else {
      try { R[spec.kind](C); } catch (e) { console.error("QV.render", spec.kind, e); root.selectAll(".qv-plot").remove(); empty(C, "Could not draw this data"); }
    }
    if (changed) root.attr("opacity", 0).transition().duration(FADE_MS).ease(d3.easeCubicOut).attr("opacity", 1);
    if (!st.ro && typeof ResizeObserver !== "undefined") {
      let timer;
      st.ro = new ResizeObserver(() => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          const s = svgEl.__qv;
          if (s && s.spec && Math.abs(widthOf(svgEl) - s.w) > 1) render(svgEl, s.spec);
        }, 120);
      });
      st.ro.observe(svgEl);
    }
    return svgEl;
  }

  function rng(seed) {
    let h = 1779033703 ^ seed.length;
    for (let i = 0; i < seed.length; i++) { h = Math.imul(h ^ seed.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
    let a = h >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }

  function mock(kind, labels, seed) {
    const f = labels && typeof labels === "object" ? labels : {};
    const list = (a, min) => (Array.isArray(a) ? a.map(str).map(s => s.trim()).filter(Boolean) : []).filter((s, i, arr) => arr.indexOf(s) === i).length >= min
      ? uniq(a.map(str).map(s => s.trim()).filter(Boolean)) : null;
    const rg = Array.isArray(f.range) && f.range.length === 2 && Number.isFinite(+f.range[0]) && Number.isFinite(+f.range[1]) && +f.range[1] > +f.range[0]
      ? [+f.range[0], +f.range[1]] : [0, 100];
    // Qwen sometimes puts the years in categories and the items in series. Swap them back.
    const timeish = a => a && a.every(x => /^(\d{4}([-\/]\d{2,4})?|(19|20)\d{2}[- ]?q[1-4]|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?( \d{4})?)$/i.test(x));
    let catList = list(f.categories, 2), ser = list(f.series, 2);
    if (timeish(catList) && ser && !timeish(ser)) [catList, ser] = [ser, null];
    f.categories = catList;
    const cats = (catList || ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]).slice(0, 12);
    const series = (ser || ["Group 1", "Group 2", "Group 3"]).slice(0, 8);
    const r = rng([kind, JSON.stringify([f.title, f.x, f.y, f.unit, cats, ser, rg]), seed == null ? "" : String(seed)].join("|"));
    const span = rg[1] - rg[0], within = (a = 0, b = 1) => rg[0] + (a + r() * (b - a)) * span;
    // Qwen's time labels when it gave enough, so "monthly" gets months; years otherwise
    const tl = list(f.times, 3);
    const years = n => tl ? tl.slice(0, 12) : d3.range(n).map(i => String(2025 - n + 1 + i));
    const round = v => (Math.abs(v) >= 100 ? Math.round(v) : Math.abs(v) >= 1 ? Math.round(v * 10) / 10 : Math.round(v * 1000) / 1000);
    let rows = [];
    switch (kind) {
      case "bar": case "treemap":
        rows = cats.map(cat => ({cat, v: round(within(0.15, 1))})); break;
      case "donut":
        rows = (cats.length <= 5 ? cats : ser && ser.length <= 5 ? ser : cats.slice(0, 4)).map(cat => ({cat, v: round(within(0.2, 1))})); break;
      case "line": {
        // the items tracked over time are the lines. Qwen usually lists them as categories, so those win
        const S = list(f.categories, 2) ? cats.slice(0, 8) : ser ? series : [null];
        S.forEach(s => { let v = within(0.3, 0.6); years(8).forEach(t => { v = Math.min(rg[1], Math.max(rg[0], v + (r() - 0.4) * span * 0.12)); rows.push(s ? {t, series: s, v: round(v)} : {t, v: round(v)}); }); });
        break;
      }
      case "stacked_area":
        (list(f.categories, 2) ? cats.slice(0, 8) : series).forEach((s, i, all) => { let v = within(0.1, 0.3) / all.length * 2; years(8).forEach(t => { v = Math.max(span * 0.02, v * (0.9 + r() * 0.3)); rows.push({t, series: s, v: round(v)}); }); });
        break;
      case "stacked_bar": case "sankey":
        (kind === "sankey" ? cats.slice(0, 5) : cats).forEach(cat => series.forEach(s => { if (kind !== "sankey" || r() > 0.2) rows.push({cat, series: s, v: round(within(0.1, 1))}); }));
        break;
      case "heatmap": {
        const cols = ser && ser.length >= 3 ? series : years(6);
        cats.forEach((cat, i) => { const base = r(); cols.forEach((s, j) => rows.push({cat, series: s, v: round(rg[0] + Math.min(1, Math.max(0, base * 0.6 + r() * 0.4 + j * 0.03)) * span)})); });
        break;
      }
      case "scatter":
        d3.range(60).forEach(() => { const a = r(); rows.push({v: round(a * 100), v2: round(rg[0] + (a * 0.7 + r() * 0.3) * span), ...(ser ? {series: series[Math.floor(r() * series.length)]} : {})}); });
        break;
      case "histogram":
        d3.range(400).forEach(() => rows.push({v: round(rg[0] + (r() + r() + r() + r()) / 4 * span)}));
        break;
      case "bump": {
        const C6 = cats.slice(0, 6);
        let order = d3.shuffle(C6.slice(), r);
        years(6).forEach(t => {
          for (let k = 0; k < 2; k++) { const i = Math.floor(r() * (order.length - 1)); [order[i], order[i + 1]] = [order[i + 1], order[i]]; }
          order.forEach((cat, i) => rows.push({t, cat, v: i + 1}));
        });
        break;
      }
      case "dot_range": {
        const S = (ser || ["2020", "2025"]).slice(0, 2);
        cats.forEach(cat => { const a = within(0.1, 0.75); rows.push({cat, series: S[0], v: round(a)}, {cat, series: S[1], v: round(Math.min(rg[1], Math.max(rg[0], a + (r() - 0.25) * span * 0.35)))}); });
        break;
      }
    }
    const xLabel = kind === "histogram" ? str(f.y || f.x) : kind === "scatter" ? str(f.x) : ["stacked_bar", "dot_range", "heatmap"].includes(kind) ? str(f.x) : str(f.x);
    const yLabel = kind === "histogram" ? "Count" : kind === "bump" ? "Rank" : ["treemap", "donut", "sankey"].includes(kind) ? str(f.y) : str(f.y || "Value");
    return {kind, title: str(f.title), xLabel, yLabel, unit: kind === "bump" ? "" : str(f.unit), mock: true, rows};
  }

  let fontCss = null;
  async function embeddedFonts() {
    if (fontCss !== null) return fontCss;
    fontCss = "";
    try {
      const url = "https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&display=swap";
      const css = await (await fetch(url)).text();
      const faces = css.split("@font-face").slice(1).map(b => "@font-face" + b.split("}")[0] + "}");
      const latin = faces.filter((b, i) => /U\+0000-00FF/.test(b) || faces.length <= 3);
      const out = [];
      for (const face of latin) {
        const m = face.match(/url\((https:[^)]+)\)/);
        if (!m) continue;
        const buf = await (await fetch(m[1])).arrayBuffer();
        let bin = "";
        const bytes = new Uint8Array(buf);
        for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        out.push(face.replace(m[1], "data:font/woff2;base64," + btoa(bin)));
      }
      fontCss = out.join("\n");
    } catch (e) { fontCss = ""; }
    return fontCss;
  }

  const STYLE_PROPS = ["fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
    "opacity", "font-family", "font-size", "font-weight", "font-style", "text-anchor", "dominant-baseline", "letter-spacing", "visibility", "display"];

  async function exportPNG(svgEl, filename) {
    if (!svgEl) return;
    const W = +svgEl.getAttribute("width") || widthOf(svgEl), Hh = +svgEl.getAttribute("height") || H;
    const clone = svgEl.cloneNode(true);
    const src = [svgEl, ...svgEl.querySelectorAll("*")], dst = [clone, ...clone.querySelectorAll("*")];
    src.forEach((el, i) => {
      const cs = getComputedStyle(el), out = dst[i];
      if (!out || !out.style) return;
      STYLE_PROPS.forEach(p => { const v = cs.getPropertyValue(p); if (v) out.style.setProperty(p, v); });
    });
    clone.querySelectorAll(".qv-root").forEach(n => { n.style.opacity = "1"; n.removeAttribute("opacity"); });
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", W); clone.setAttribute("height", Hh);
    clone.style.width = W + "px"; clone.style.height = Hh + "px";
    const fonts = await embeddedFonts();
    if (fonts) {
      const s = document.createElementNS("http://www.w3.org/2000/svg", "style");
      s.textContent = fonts;
      clone.insertBefore(s, clone.firstChild);
    }
    const data = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(new XMLSerializer().serializeToString(clone));
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = data; });
    const canvas = document.createElement("canvas");
    canvas.width = W * 2; canvas.height = Hh * 2;
    const ctx = canvas.getContext("2d");
    ctx.scale(2, 2);
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, W, Hh);
    ctx.drawImage(img, 0, 0, W, Hh);
    const blob = await new Promise(res => canvas.toBlob(res, "image/png"));
    const name = (filename || (svgEl.__qv && svgEl.__qv.spec && svgEl.__qv.spec.title) || "chart").replace(/[^\w\- .]+/g, "").trim().replace(/\s+/g, "-") || "chart";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = /\.png$/i.test(name) ? name : name + ".png";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    return blob;
  }

  window.QV = {render, mock, exportPNG, kinds: Object.keys(R)};
})();

function draw() {
  if (typeof state === "undefined" || !state || !state.kind) return;
  const t = document.getElementById("title");
  if (t) t.textContent = "";
  QV.render(document.getElementById("chart"), QV.mock(state.kind, state.fill || {}, ""));
}
