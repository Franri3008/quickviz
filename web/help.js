(function () {
  const PALETTES = {
    ceps: {G: "#207164", N: "#0c2443", L: "#8fc0b6", T: "#c4ded9", M: "#56998c", Y: "#a3a3a1", D: "#134a41", W: "#eef5f3"},
    aiw: {G: "#2756d3", N: "#e53229", L: "#9db4ec", T: "#dde7f9", M: "#5b7fe0", Y: "#9ca3af", D: "#1a3d99", W: "#f1f5fd"},
    franri: {G: "#13759a", N: "#c4540c", L: "#8fc3d6", T: "#d3e7ef", M: "#5fa3bd", Y: "#8a857e", D: "#0d3f63", W: "#ecf4f7"},
  };
  const rect = (x, y, w, h, c) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${c}"/>`;
  const dot = (x, y, c, r = 2.6) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${c}"/>`;
  const line = (pts, c, w = 2) => `<polyline points="${pts}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linejoin="round" stroke-linecap="round"/>`;
  const axis = `<path d="M4 29H44" stroke="#d4d4d2" stroke-width="1"/>`;

  const kinds = ({G, N, L, T, M, Y, D, W}) => [
    {name: "Bar chart", what: "Compares one number across items.",
      svg: axis + rect(7, 9, 6, 20, G) + rect(16, 14, 6, 15, G) + rect(25, 18, 6, 11, G) + rect(34, 22, 6, 7, N)},
    {name: "Line chart", what: "Shows how numbers change over time.",
      svg: axis + line("5,24 14,19 23,21 32,12 43,8", G) + line("5,27 14,25 23,22 32,21 43,17", N)},
    {name: "Stacked area chart", what: "Shows how a total over time splits into parts.",
      svg: axis + `<path d="M4 29V20L14 17L24 18L34 12L44 10V29Z" fill="${L}"/><path d="M4 29V25L14 23L24 24L34 20L44 19V29Z" fill="${G}"/>`},
    {name: "Stacked bar chart", what: "Shows how each item splits into parts.",
      svg: axis + [8, 20, 32].map((x, i) => rect(x, 6, 8, 8 + i * 3, T) + rect(x, 14 + i * 3, 8, 7 - i, M) + rect(x, 21 + 2 * i, 8, 8 - 2 * i, G)).join("")},
    {name: "Scatter plot", what: "Shows how two numbers relate across items.",
      svg: axis + `<path d="M4 4V29" stroke="#d4d4d2"/>` + [[9, 24], [14, 21], [18, 22], [22, 16], [27, 17], [31, 11], [36, 12], [40, 7]].map(([x, y], i) => dot(x, y, i === 5 ? N : G)).join("")},
    {name: "Histogram", what: "Shows how one number spreads across many rows.",
      svg: axis + [22, 16, 9, 6, 11, 18, 24].map((y, i) => rect(6 + i * 5, y, 4.4, 29 - y, G)).join("")},
    {name: "Heatmap", what: "Shows a value for every pair of two groupings as a grid of colours.",
      svg: [[T, L, G, M], [L, W, T, G], [G, T, L, D]].map((row, j) => row.map((c, i) => rect(6 + i * 9.2, 4 + j * 8.4, 8.4, 7.6, c)).join("")).join("")},
    {name: "Treemap", what: "Shows shares of a whole as tiles sized by value.",
      svg: rect(4, 4, 20, 25, G) + rect(25, 4, 19, 14, M) + rect(25, 19, 10, 10, L) + rect(36, 19, 8, 10, T)},
    {name: "Donut chart", what: "Shows how a whole splits into a few parts.",
      svg: `<g transform="rotate(-90 24 16.5)" fill="none" stroke-width="6"><circle cx="24" cy="16.5" r="10" stroke="${G}" stroke-dasharray="31 63"/><circle cx="24" cy="16.5" r="10" stroke="${N}" stroke-dasharray="0 31 18 63"/><circle cx="24" cy="16.5" r="10" stroke="${L}" stroke-dasharray="0 49 14 63"/></g>`},
    {name: "Flow chart", what: "Shows amounts flowing from sources to targets.",
      svg: rect(4, 4, 4, 12, G) + rect(4, 18, 4, 11, N) + rect(40, 4, 4, 9, Y) + rect(40, 15, 4, 14, Y) +
        `<path d="M8 4C24 4 24 4 40 4V9C24 9 24 10 8 10Z" fill="${G}" opacity=".45"/><path d="M8 10C24 10 24 15 40 15V21C24 21 24 16 8 16Z" fill="${G}" opacity=".3"/><path d="M8 18C24 18 24 21 40 21V29C24 29 24 29 8 29Z" fill="${N}" opacity=".35"/>`},
    {name: "Ranking chart", what: "Shows how the ranks of items change over time.",
      svg: line("6,7 18,17 30,17 42,27", G) + line("6,17 18,7 30,27 42,17", N) + line("6,27 18,27 30,7 42,7", Y) +
        [6, 18, 30, 42].map(x => [7, 17, 27].map(y => dot(x, y, "#fff", 1.4)).join("")).join("")},
    {name: "Dot range chart", what: "Compares two values per item and shows the gap between them.",
      svg: [[8, 30, 7], [14, 38, 16.5], [11, 24, 26]].map(([a, b, y]) => `<path d="M${a} ${y}H${b}" stroke="#d4d4d2" stroke-width="2.4"/>` + dot(a, y, L, 3) + dot(b, y, G, 3)).join("")},
    {name: "Map", what: "Colours countries, or the regions of one country, by value.",
      svg: `<path d="M6 8L15 4L21 9L18 16L9 17Z" fill="${T}"/><path d="M21 9L31 6L36 13L29 19L18 16Z" fill="${G}"/><path d="M9 17L18 16L29 19L26 29L12 27Z" fill="${M}"/><path d="M29 19L36 13L44 18L40 28L26 29Z" fill="${L}"/>`},
  ];

  const btn = document.getElementById("help"), dlg = document.getElementById("help-dialog");
  if (!btn || !dlg) return;
  const fill = () => {
    const style = document.body.dataset.style;
    document.getElementById("help-list").innerHTML = kinds(PALETTES[style] || PALETTES.ceps).map(k =>
      `<li><span class="help-icon"><svg viewBox="0 0 48 33" aria-hidden="true">${k.svg}</svg></span>` +
      `<span class="help-text"><b>${k.name}</b><span>${k.what}</span></span></li>`).join("");
  };
  fill();

  const focusables = () => [...dlg.querySelectorAll("button, [href], [tabindex]:not([tabindex='-1'])")].filter(el => !el.disabled && el.offsetParent !== null);
  const close = () => { if (dlg.open) dlg.close(); };
  btn.onclick = () => {
    if (dlg.open) return;
    fill();
    dlg.showModal();
    dlg.querySelector(".help-scroll").scrollTop = 0;
    document.getElementById("help-close").focus();
  };
  document.getElementById("help-close").onclick = close;
  dlg.addEventListener("close", () => btn.focus());
  dlg.addEventListener("click", e => { if (e.target === dlg) close(); });
  dlg.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key !== "Tab") return;
    const f = focusables();
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
})();
