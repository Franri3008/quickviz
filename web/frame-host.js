(function () {
  const NEED = /^\.\/(vendor\/countries-50m\.json|geo\/regions\/(index|[A-Z]{3})\.json)$/;
  const MAX_H = 6000;
  const RENDER_MS = 6000;
  const version = (document.querySelector('meta[name="qv-version"]') || {}).content || "";
  const safe = t => String(t).replace(/<\/(script)/gi, "<\\/$1").replace(/<!--/g, "<\\!--");
  let docP = null, flagData = {};

  async function text(path) {
    const r = await fetch(path + (version ? "?v=" + encodeURIComponent(version) : ""), {credentials: "same-origin"});
    if (!r.ok) throw new Error("Could not load " + path);
    return r.text();
  }

  function srcdoc() {
    if (docP) return docP;
    docP = Promise.all(["vendor/d3.min.js", "vendor/d3-sankey.min.js", "vendor/topojson-client.min.js", "ceps-theme.js", "aiw-theme.js", "franri-theme.js", "charts.js", "frame-runtime.js"].map(text)
      .concat([QV.embeddedFonts(), text("flags/flags.json").then(t => { flagData = JSON.parse(t); }).catch(() => { })]))
      .then(([d3src, sankey, topo, theme, aiw, franri, charts, runtime, fonts]) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${QV.FRAME_CSP}">
<style>${fonts}
html,body{margin:0;padding:0;background:transparent;overflow:hidden;color-scheme:light}
body{font-family:Carlito,Calibri,"Segoe UI",sans-serif;color:#1a1a1a}
#host{width:100%}
#chart{display:block;width:100%;height:auto}</style>
</head><body><div id="host"><svg id="chart" role="img" aria-label="Chart"></svg></div>
<script>window.QV_BASE = "./"; window.QV_FONT_CSS = ${safe(JSON.stringify(fonts))};<\/script>
<script>${safe(d3src)}<\/script>
<script>${safe(sankey)}<\/script>
<script>${safe(topo)}<\/script>
<script>${safe(theme)}<\/script>
<script>${safe(aiw)}<\/script>
<script>${safe(franri)}<\/script>
<script>${safe(charts)}<\/script>
<script>${safe(runtime)}<\/script>
</body></html>`)
      .catch(e => { docP = null; throw e; });
    return docP;
  }

  function withFlags(m) {
    if (!m || !m.spec) return m;
    const keys = QV.flagKeys(m.spec).filter(k => typeof flagData[k] === "string");
    return keys.length ? {...m, flags: Object.fromEntries(keys.map(k => [k, flagData[k]]))} : m;
  }

  const num = (v, lo, hi) => (typeof v === "number" && Number.isFinite(v) ? Math.max(lo, Math.min(hi, v)) : null);
  const strs = a => (Array.isArray(a) ? a.filter(x => typeof x === "string").slice(0, 200) : []);

  function cleanFit(f) {
    if (!f || typeof f !== "object") return null;
    const n = num(f.n, 0, 10000), cap = num(f.cap, 1, 10000);
    return n == null || cap == null ? null : {n: Math.round(n), cap: Math.round(cap)};
  }

  function cleanErrors(list) {
    return (Array.isArray(list) ? list : []).slice(0, 20).filter(x => x && typeof x === "object")
      .map(x => ({index: num(x.index, 0, 1000) ?? -1, note: String(x.note || "").slice(0, 200), message: String(x.message || "").slice(0, 300)}));
  }

  function cleanState(m) {
    const geo = typeof m.geoUsed === "string" && /^(world|[A-Z]{3})$/.test(m.geoUsed) ? m.geoUsed : null;
    const c = m.ctlInit;
    const ctlInit = c && typeof c === "object" && Array.isArray(c.idx)
      ? {idx: c.idx.slice(0, 8).map(v => (Number.isInteger(v) && v >= 0 && v < 1000 ? v : 0)), off: {series: strs(c.off && c.off.series), cat: strs(c.off && c.off.cat)}}
      : null;
    const flagsUsed = strs(m.flagsUsed).filter(k => /^(\d{3}|eu)$/.test(k));
    return {geoUsed: geo, ctlInit, flagsUsed};
  }

  function mount(first) {
    let el = first, ready = false, seq = 0, last = null, lastId = 0, booting = null;
    const waits = new Map(), queue = [];

    function post(msg) {
      if (ready && el.contentWindow) el.contentWindow.postMessage(withFlags(msg), "*");
      else queue.push(msg);
    }

    function ask(type, extra = {}, ms = RENDER_MS) {
      const id = ++seq;
      return new Promise((ok, no) => {
        const timer = setTimeout(() => { waits.delete(id); no(new Error("timeout")); }, ms);
        waits.set(id, {ok: v => { clearTimeout(timer); ok(v); }, no: e => { clearTimeout(timer); no(e); }, type});
        post({type, id, ...extra});
      });
    }

    function boot() {
      ready = false;
      el.setAttribute("sandbox", "allow-scripts");
      el.style.height = el.style.height || "520px";
      booting = srcdoc().then(doc => { el.srcdoc = doc; }).catch(e => { console.error("chart frame", e); });
      return booting;
    }

    function reset() {
      const fresh = el.cloneNode(false);
      fresh.removeAttribute("srcdoc");
      el.replaceWith(fresh);
      el = fresh;
      for (const [, w] of waits) w.no(new Error("reset"));
      waits.clear();
      queue.length = 0;
      boot();
      if (last) post(last);
    }

    async function need(m) {
      let data = null;
      if (typeof m.url === "string" && NEED.test(m.url)) {
        try { const r = await fetch(m.url.slice(2), {credentials: "same-origin"}); if (r.ok) data = await r.json(); } catch (e) { }
      }
      if (el.contentWindow) el.contentWindow.postMessage({type: "geo", id: m.id, data}, "*");
    }

    window.addEventListener("message", e => {
      if (!el.contentWindow || e.source !== el.contentWindow) return;
      const m = e.data;
      if (!m || typeof m !== "object" || typeof m.type !== "string") return;
      if (m.type === "ready") {
        ready = true;
        const q = queue.splice(0);
        if (last && !q.includes(last)) q.unshift(last);
        q.forEach(x => el.contentWindow.postMessage(withFlags(x), "*"));
        return;
      }
      if (m.type === "size" || m.type === "rendered") {
        const h = num(m.height, 0, MAX_H);
        if (h) el.style.height = h + "px";
      }
      if (m.type === "need") { need(m); return; }
      const w = waits.get(m.id);
      if (!w) return;
      waits.delete(m.id);
      if (m.type === "failed") { w.no(new Error(String(m.error || "failed").slice(0, 300))); return; }
      if (m.type !== w.type && !(w.type === "render" && m.type === "rendered") && !(w.type === "clear" && m.type === "rendered")) return;
      if (m.type === "rendered") w.ok({errors: cleanErrors(m.errors), used: Array.isArray(m.used) ? strs(m.used) : null, fit: cleanFit(m.fit), orient: m.orient === "vertical" || m.orient === "horizontal" ? m.orient : null, error: String(m.error || "").slice(0, 300), ms: num(m.ms, 0, 1e6)});
      else if (m.type === "png") {
        const W = num(m.W, 1, 4000), H = num(m.H, 1, 6000);
        if (typeof m.markup !== "string" || !m.markup || m.markup.length > 40e6 || !W || !H) w.no(new Error("No image came back from the chart"));
        else w.ok({markup: m.markup, W, H, transparent: !!m.transparent});
      } else if (m.type === "state") w.ok(cleanState(m));
      else if (m.type === "outline") w.ok(typeof m.text === "string" ? m.text.slice(0, 12000) : "");
      else if (m.type === "sig") w.ok(typeof m.sig === "string" && /^[0-9a-f]{16}:\d+$/.test(m.sig) ? m.sig : null);
    });

    function render(spec, opts = {}) {
      const msg = {type: "render", spec, fitH: opts.fitH == null ? null : opts.fitH, still: !!opts.still, patches: opts.patches || []};
      const id = ++seq;
      msg.id = id;
      last = msg;
      lastId = id;
      const keep = queue.filter(x => x.type !== "render" && x.type !== "clear");
      queue.filter(x => !keep.includes(x)).forEach(x => { const w = waits.get(x.id); if (w) { waits.delete(x.id); w.ok({errors: [], error: "", superseded: true}); } });
      queue.splice(0, queue.length, ...keep);
      return new Promise((ok, no) => {
        const timer = setTimeout(() => {
          waits.delete(id);
          if (lastId === id && ready) { const bad = last; last = {...bad, patches: []}; reset(); }
          no(new Error("The chart took too long to draw"));
        }, RENDER_MS + (ready ? 0 : 8000));
        waits.set(id, {ok: v => { clearTimeout(timer); ok(v); }, no: e => { clearTimeout(timer); no(e); }, type: "render"});
        post(msg);
      });
    }

    function clear() {
      last = null;
      el.style.height = "520px";
      return ask("clear").catch(() => null);
    }

    function settled(ms = 700) {
      const id = lastId;
      const w = waits.get(id);
      if (!w) return Promise.resolve();
      return new Promise(ok => {
        const t = setTimeout(ok, ms);
        const prev = w.ok;
        w.ok = v => { clearTimeout(t); prev(v); ok(); };
      });
    }

    boot();
    return {
      render, clear, settled,
      png: () => ask("png", {}, 15000),
      state: () => ask("state", {}, 4000),
      outline: (max = 6000) => ask("outline", {max}, 4000).catch(() => ""),
      sig: (spec, patches) => ask("sig", {spec, patches: patches || []}, RENDER_MS).catch(() => null),
      flags: () => srcdoc().then(() => flagData, () => flagData),
      get el() { return el; },
    };
  }

  window.QVFrame = {mount};
})();
