// Chart renderers. Worker 1 converts these to read the spec in SPEC.md.
const W = 820, H = 420, M = {t: 20, r: 120, b: 40, l: 50};
const svg = d3.select("#chart");
const color = d3.scaleOrdinal(d3.schemeTableau10);

// ---------- mock data, seeded so the same labels give the same chart ----------
function rng(seed) { let s = 0; for (const c of seed) s = (s * 31 + c.charCodeAt(0)) >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32); }
function labels() {
  const f = state.fill || {};
  return {
    title: f.title || "", x: f.x || "", y: f.y || "value", unit: f.unit || "",
    cats: (f.categories && f.categories.length >= 2 ? f.categories : ["A", "B", "C", "D", "E", "F"]).slice(0, 8),
    series: (f.series && f.series.length >= 2 ? f.series : ["Group 1", "Group 2", "Group 3"]).slice(0, 4),
    range: Array.isArray(f.range) && f.range.length === 2 && f.range[1] > f.range[0] ? f.range : [0, 100],
  };
}

// ---------- renderers ----------
function frame() { svg.selectAll("*").remove(); return svg.append("g").attr("transform", `translate(${M.l},${M.t})`); }
const iw = W - M.l - M.r, ih = H - M.t - M.b;
function axes(g, x, y) {
  g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x).tickSizeOuter(0));
  g.append("g").call(d3.axisLeft(y).ticks(5));
}
function legend(g, names) {
  names.forEach((n, i) => {
    const r = g.append("g").attr("transform", `translate(${iw + 12},${i * 18})`);
    r.append("rect").attr("width", 10).attr("height", 10).attr("fill", color(n));
    r.append("text").attr("x", 14).attr("y", 9).text(n);
  });
}
const years = n => d3.range(n).map(i => String(2018 + i));

const R = {
  bar(L, r) {
    const g = frame(), d = L.cats.map(c => ({c, v: L.range[0] + r() * (L.range[1] - L.range[0])}));
    const x = d3.scaleBand(L.cats, [0, iw]).padding(0.25), y = d3.scaleLinear([0, d3.max(d, e => e.v)], [ih, 0]).nice();
    axes(g, x, y);
    g.selectAll("rect.b").data(d).join("rect").attr("x", e => x(e.c)).attr("width", x.bandwidth()).attr("fill", color(0))
      .attr("y", ih).attr("height", 0).transition().attr("y", e => y(e.v)).attr("height", e => ih - y(e.v));
  },
  line(L, r) {
    const g = frame(), xs = years(8), S = L.series.slice(0, 3);
    const d = S.map(s => { let v = L.range[0] + r() * (L.range[1] - L.range[0]) * 0.5; return {s, pts: xs.map(t => ({t, v: v += (r() - 0.35) * (L.range[1] - L.range[0]) * 0.1}))}; });
    const x = d3.scalePoint(xs, [0, iw]), y = d3.scaleLinear(d3.extent(d.flatMap(e => e.pts), p => p.v), [ih, 0]).nice();
    axes(g, x, y); legend(g, S);
    d.forEach(e => g.append("path").datum(e.pts).attr("fill", "none").attr("stroke", color(e.s)).attr("stroke-width", 2)
      .attr("d", d3.line(p => x(p.t), p => y(p.v))));
  },
  stacked_area(L, r) {
    const g = frame(), xs = years(8), S = L.series;
    const rows = xs.map(t => Object.fromEntries([["t", t], ...S.map(s => [s, 10 + r() * 30])]));
    const st = d3.stack().keys(S)(rows);
    const x = d3.scalePoint(xs, [0, iw]), y = d3.scaleLinear([0, d3.max(st.at(-1), e => e[1])], [ih, 0]).nice();
    axes(g, x, y); legend(g, S);
    g.selectAll("path.a").data(st).join("path").attr("fill", e => color(e.key)).attr("opacity", 0.85)
      .attr("d", d3.area(p => x(p.data.t), p => y(p[0]), p => y(p[1])));
  },
  stacked_bar(L, r) {
    const g = frame(), S = L.series;
    const rows = L.cats.map(c => Object.fromEntries([["c", c], ...S.map(s => [s, r()])]));
    rows.forEach(row => { const t = d3.sum(S, s => row[s]); S.forEach(s => row[s] = row[s] / t * 100); });
    const st = d3.stack().keys(S)(rows);
    const x = d3.scaleBand(L.cats, [0, iw]).padding(0.25), y = d3.scaleLinear([0, 100], [ih, 0]);
    axes(g, x, y); legend(g, S);
    g.selectAll("g.s").data(st).join("g").attr("fill", e => color(e.key)).selectAll("rect").data(e => e).join("rect")
      .attr("x", p => x(p.data.c)).attr("width", x.bandwidth()).attr("y", p => y(p[1])).attr("height", p => y(p[0]) - y(p[1]));
  },
  scatter(L, r) {
    const g = frame(), n = 60, d = d3.range(n).map(() => { const a = r(); return {a: a * 100, b: L.range[0] + (a * 0.7 + r() * 0.3) * (L.range[1] - L.range[0]), s: L.series[Math.floor(r() * L.series.length)]}; });
    const x = d3.scaleLinear([0, 100], [0, iw]), y = d3.scaleLinear(d3.extent(d, e => e.b), [ih, 0]).nice();
    axes(g, x, y); legend(g, L.series);
    g.selectAll("circle").data(d).join("circle").attr("cx", e => x(e.a)).attr("cy", e => y(e.b)).attr("r", 5).attr("fill", e => color(e.s)).attr("opacity", 0.75);
  },
  histogram(L, r) {
    const g = frame(), vals = d3.range(400).map(() => (r() + r() + r() + r()) / 4 * (L.range[1] - L.range[0]) + L.range[0]);
    const x = d3.scaleLinear(L.range, [0, iw]), bins = d3.bin().domain(x.domain()).thresholds(20)(vals);
    const y = d3.scaleLinear([0, d3.max(bins, b => b.length)], [ih, 0]).nice();
    axes(g, x, y);
    g.selectAll("rect").data(bins).join("rect").attr("x", b => x(b.x0) + 1).attr("width", b => Math.max(0, x(b.x1) - x(b.x0) - 2))
      .attr("y", b => y(b.length)).attr("height", b => ih - y(b.length)).attr("fill", color(0));
  },
  heatmap(L, r) {
    const g = frame(), cols = L.series.length >= 3 ? L.series : years(6);
    const d = L.cats.flatMap(c => cols.map(s => ({c, s, v: r()})));
    const x = d3.scaleBand(cols, [0, iw]).padding(0.04), y = d3.scaleBand(L.cats, [0, ih]).padding(0.04), c = d3.scaleSequential(d3.interpolateBlues).domain([0, 1]);
    g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x)); g.append("g").call(d3.axisLeft(y));
    g.selectAll("rect").data(d).join("rect").attr("x", e => x(e.s)).attr("y", e => y(e.c)).attr("width", x.bandwidth()).attr("height", y.bandwidth()).attr("fill", e => c(e.v));
  },
  treemap(L, r) {
    const g = frame(), root = d3.hierarchy({children: L.cats.map(c => ({name: c, value: 5 + r() * 50}))}).sum(e => e.value).sort((a, b) => b.value - a.value);
    d3.treemap().size([iw + M.r - 20, ih]).padding(2)(root);
    const n = g.selectAll("g").data(root.leaves()).join("g").attr("transform", e => `translate(${e.x0},${e.y0})`);
    n.append("rect").attr("width", e => e.x1 - e.x0).attr("height", e => e.y1 - e.y0).attr("fill", e => color(e.data.name));
    n.append("text").attr("x", 6).attr("y", 16).style("fill", "#fff").text(e => e.data.name);
  },
  donut(L, r) {
    const g = frame(), S = L.series.slice(0, 4), d = S.map(s => ({s, v: 1 + r() * 5}));
    const arcs = d3.pie().value(e => e.v).sort(null)(d), rad = ih / 2;
    const c = g.append("g").attr("transform", `translate(${iw / 2},${ih / 2})`);
    c.selectAll("path").data(arcs).join("path").attr("d", d3.arc().innerRadius(rad * 0.55).outerRadius(rad)).attr("fill", a => color(a.data.s));
    legend(g, S);
  },
  sankey(L, r) {
    const g = frame(), src = L.cats.slice(0, 4), dst = L.series.map(s => s + " ");
    const nodes = [...src, ...dst].map(name => ({name}));
    const links = []; src.forEach((s, i) => dst.forEach((t, j) => { if (r() > 0.25) links.push({source: i, target: src.length + j, value: 1 + r() * 10}); }));
    const sk = d3.sankey().nodeWidth(14).nodePadding(12).extent([[0, 0], [iw, ih]])({nodes: nodes.map(d => ({...d})), links: links.map(d => ({...d}))});
    g.append("g").attr("fill", "none").selectAll("path").data(sk.links).join("path").attr("d", d3.sankeyLinkHorizontal())
      .attr("stroke", l => color(l.source.name)).attr("stroke-opacity", 0.4).attr("stroke-width", l => Math.max(1, l.width));
    g.selectAll("rect").data(sk.nodes).join("rect").attr("x", n => n.x0).attr("y", n => n.y0).attr("width", n => n.x1 - n.x0).attr("height", n => n.y1 - n.y0).attr("fill", n => color(n.name));
    g.selectAll("text.n").data(sk.nodes).join("text").attr("x", n => n.x0 < iw / 2 ? n.x1 + 6 : n.x0 - 6).attr("y", n => (n.y0 + n.y1) / 2 + 4)
      .attr("text-anchor", n => n.x0 < iw / 2 ? "start" : "end").text(n => n.name);
  },
  bump(L, r) {
    const g = frame(), xs = years(6), C = L.cats.slice(0, 6);
    const ranks = xs.map(() => d3.shuffle(C.slice(), r));
    const x = d3.scalePoint(xs, [0, iw]).padding(0.2), y = d3.scalePoint(d3.range(1, C.length + 1), [0, ih]).padding(0.5);
    g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x)); g.append("g").call(d3.axisLeft(y));
    C.forEach(c => {
      const pts = xs.map((t, i) => ({t, k: ranks[i].indexOf(c) + 1}));
      g.append("path").datum(pts).attr("fill", "none").attr("stroke", color(c)).attr("stroke-width", 3).attr("d", d3.line(p => x(p.t), p => y(p.k)).curve(d3.curveBumpX));
      g.selectAll(null).data(pts).join("circle").attr("cx", p => x(p.t)).attr("cy", p => y(p.k)).attr("r", 5).attr("fill", color(c));
    });
    legend(g, C);
  },
  dot_range(L, r) {
    const g = frame(), S = L.series.slice(0, 2), span = L.range[1] - L.range[0];
    const d = L.cats.map(c => { const a = L.range[0] + r() * span; return {c, a, b: a + (r() - 0.3) * span * 0.4}; });
    const x = d3.scaleLinear(d3.extent(d.flatMap(e => [e.a, e.b])), [0, iw]).nice(), y = d3.scaleBand(L.cats, [0, ih]).padding(0.5);
    g.append("g").attr("transform", `translate(0,${ih})`).call(d3.axisBottom(x)); g.append("g").call(d3.axisLeft(y));
    const row = g.selectAll("g.r").data(d).join("g").attr("transform", e => `translate(0,${y(e.c) + y.bandwidth() / 2})`);
    row.append("line").attr("x1", e => x(e.a)).attr("x2", e => x(e.b)).attr("stroke", "#bbb").attr("stroke-width", 2);
    row.append("circle").attr("cx", e => x(e.a)).attr("r", 6).attr("fill", color(S[0]));
    row.append("circle").attr("cx", e => x(e.b)).attr("r", 6).attr("fill", color(S[1]));
    legend(g, S);
  },
};

function draw() {
  if (!state.kind || !R[state.kind]) return;
  const L = labels();
  color.domain([]);
  document.getElementById("title").textContent = L.title;
  R[state.kind](L, rng(state.kind + L.cats.join() + L.series.join()));
}
