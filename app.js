// Input, Jev calls and state.
let seq = 0, timer = null, ctrl = null, state = {kind: null, fill: null, text: ""};

// ---------- input: debounce 200 ms, cancel stale calls, drop out-of-order replies ----------
document.getElementById("q").addEventListener("input", e => {
  clearTimeout(timer);
  const text = e.target.value.trim();
  if (text.length < 4) return;
  timer = setTimeout(() => run(text), 200);
});

async function post(path, body, signal) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body), signal});
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
}

async function run(text) {
  const my = ++seq;
  if (ctrl) ctrl.abort();
  ctrl = new AbortController();
  const t0 = performance.now();
  try {
    const p = await post("/api/pick", {text}, ctrl.signal);
    if (my !== seq) return;
    const total = Math.round(performance.now() - t0);
    document.getElementById("err").textContent = "";
    document.getElementById("meta").innerHTML =
      `<b>${p.choice}</b> — confidence ${(p.confidence ?? 0).toFixed(2)} — Jev ${p.ms} ms, round trip ${total} ms`;
    document.getElementById("alts").innerHTML = p.ranked.slice(1).map(([k, v]) =>
      `<span data-k="${k}">${k} ${v.toFixed(2)}</span>`).join("");
    document.querySelectorAll("#alts span").forEach(s => s.onclick = () => { state.kind = s.dataset.k; draw(); });
    const kindChanged = p.choice !== state.kind;
    state = {kind: p.choice, fill: kindChanged ? null : state.fill, text};
    draw();
    // second layer: real-sounding labels, swapped in when they arrive
    try {
      const f = await post("/api/fill", {text, kind: p.choice}, ctrl.signal);
      if (my !== seq) return;
      state.fill = f; draw();
      document.getElementById("meta").innerHTML += ` — labels ${f.ms} ms`;
    } catch (e) {
      if (e.name !== "AbortError" && my === seq) document.getElementById("err").textContent = "Labels failed, showing generic ones";
    }
  } catch (e) {
    if (e.name !== "AbortError" && my === seq) document.getElementById("err").textContent = String(e.message).slice(0, 160);
  }
}

