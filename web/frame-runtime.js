(function () {
  const up = window.parent;
  const send = m => up.postMessage(m, "*");
  const host = document.getElementById("host"), svgEl = document.getElementById("chart");
  const asks = new Map();
  let askId = 0, lastH = -1;

  for (const k of ["fetch", "XMLHttpRequest", "WebSocket", "WebSocketStream", "EventSource", "RTCPeerConnection", "webkitRTCPeerConnection",
    "RTCDataChannel", "Worker", "SharedWorker", "WebTransport", "open", "localStorage", "sessionStorage", "indexedDB", "caches", "BroadcastChannel"]) {
    try { Object.defineProperty(window, k, {value: undefined, writable: false, configurable: false}); } catch (e) { }
  }
  try { Object.defineProperty(Navigator.prototype, "sendBeacon", {value: undefined, writable: false, configurable: false}); } catch (e) { }
  try { Object.defineProperty(Navigator.prototype, "serviceWorker", {value: undefined, writable: false, configurable: false}); } catch (e) { }

  window.QV_GET_JSON = url => new Promise(ok => {
    const id = ++askId;
    asks.set(id, ok);
    send({type: "need", id, url: String(url)});
  });

  function size() {
    const h = Math.ceil(host.getBoundingClientRect().height);
    if (h !== lastH) { lastH = h; send({type: "size", height: h}); }
  }
  window.QV_ON_RENDER = el => { if (el === svgEl) size(); };
  if (window.ResizeObserver) new ResizeObserver(size).observe(host);

  function ctlState() {
    const cv = svgEl.__qv && svgEl.__qv.cv;
    return cv ? {idx: cv.idx.slice(), off: {series: [...cv.off.series], cat: [...cv.off.cat]}} : null;
  }

  function hash(s) {
    let a = 0x811c9dc5, b = 0x9747b28c;
    for (let i = 0; i < s.length; i++) {
      const c = s.charCodeAt(i);
      a = Math.imul(a ^ c, 16777619);
      b = Math.imul(b ^ c, 2246822507) ^ (b >>> 13);
    }
    return (a >>> 0).toString(16).padStart(8, "0") + (b >>> 0).toString(16).padStart(8, "0") + ":" + s.length;
  }

  function drawOff(spec, patches, width, fitH) {
    const box = document.createElement("div");
    box.style.cssText = "position:absolute;left:-10000px;top:0;width:" + width + "px;visibility:hidden";
    document.body.appendChild(box);
    const s2 = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    box.appendChild(s2);
    try {
      QV.render(s2, spec, {fitH, still: true, noResize: true, noControls: true, patches: patches || []});
      const st = s2.__qv || {};
      if (!Array.isArray(st.used)) return null;
      return new XMLSerializer().serializeToString(s2).replace(/qv(grad|clip)[a-z0-9]+/g, "qv$1") + "\u0000" + (st.patchErr || []).length;
    } finally {
      const st = s2.__qv;
      if (st && st.cv && st.cv.timer) clearInterval(st.cv.timer);
      box.remove();
    }
  }

  function signature(spec, patches) {
    const live = svgEl.__qv || {};
    const ctlH = live.box ? live.box.reduce((h, d) => h + d.offsetHeight, 0) : 0;
    const screenW = Math.round(live.w || host.clientWidth || QV.EXPORT_W);
    const fitH = live.fitH ? live.fitH - ctlH : null;
    const parts = [];
    for (const [w, f] of [[screenW, fitH], [QV.EXPORT_W, null]]) {
      const m = drawOff(spec, patches, w, f);
      if (m == null) return null;
      parts.push(m);
    }
    const ctl = Array.isArray(spec.controls) && spec.controls.length ? JSON.stringify([spec.controls, spec.rows]) : "";
    return hash(parts.join("\u0001") + "\u0000" + ctl);
  }

  function clear() {
    const st = svgEl.__qv;
    if (st && st.cv && st.cv.timer) clearInterval(st.cv.timer);
    if (st && st.box) st.box.forEach(b => b.remove());
    svgEl.replaceChildren();
    svgEl.removeAttribute("width"); svgEl.removeAttribute("height"); svgEl.removeAttribute("viewBox");
    svgEl.__qv = st && st.ro ? {ro: st.ro} : undefined;
    size();
  }

  addEventListener("message", async e => {
    if (e.source !== up) return;
    const m = e.data;
    if (!m || typeof m !== "object") return;
    if (m.type === "geo") {
      const ok = asks.get(m.id);
      asks.delete(m.id);
      if (ok) ok(m.data || null);
      return;
    }
    if (m.flags && typeof m.flags === "object") Object.assign(window.QV_FLAGS, m.flags);
    try {
      if (m.type === "render") {
        const t0 = performance.now();
        let error = "";
        try { QV.render(svgEl, m.spec, {fitH: m.fitH == null ? null : m.fitH, still: !!m.still, patches: m.patches || []}); }
        catch (err) { error = String((err && err.message) || err); }
        const st = svgEl.__qv || {};
        lastH = -1;
        size();
        send({type: "rendered", id: m.id, height: lastH, errors: st.patchErr || [], used: Array.isArray(st.used) ? st.used : null, fit: st.fit || null, orient: st.orient || null, error, ms: Math.round(performance.now() - t0)});
      } else if (m.type === "clear") {
        clear();
        send({type: "rendered", id: m.id, height: lastH, errors: [], error: ""});
      } else if (m.type === "png") {
        const out = await QV.exportMarkup(svgEl);
        send({type: "png", id: m.id, markup: out ? out.markup : "", W: out ? out.W : 0, H: out ? out.H : 0, transparent: !!(out && out.transparent)});
      } else if (m.type === "state") {
        const st = svgEl.__qv || {};
        send({type: "state", id: m.id, ctlInit: ctlState(), geoUsed: st.geoUsed || null, flagsUsed: st.flagsUsed || []});
      } else if (m.type === "sig") {
        let sig = null;
        try { sig = signature(m.spec || {}, m.patches); } catch (err) { sig = null; }
        send({type: "sig", id: m.id, sig});
      } else if (m.type === "outline") {
        send({type: "outline", id: m.id, text: QV.outline(svgEl, m.max || 6000)});
      }
    } catch (err) {
      send({type: "failed", id: m.id, error: String((err && err.message) || err).slice(0, 300)});
    }
  });

  QV.ready.then(() => send({type: "ready"}));
})();
