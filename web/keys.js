(() => {
  const $ = id => document.getElementById(id);
  const btn = $("keys-open"), dlg = $("keys-dialog");
  if (!btn || !dlg) return;
  const day = t => (t ? new Date(t * 1000).toLocaleDateString("en-GB", {day: "numeric", month: "short", year: "numeric"}) : "never");
  const command = key => `claude mcp add --transport http quickviz ${location.origin}/mcp --header "Authorization: Bearer ${key}"`;

  function say(msg) {
    $("keys-err").textContent = msg || "";
    $("keys-err").hidden = !msg;
  }

  async function call(path, opts = {}) {
    const r = await fetch(path, {credentials: "same-origin", ...opts});
    let j = null;
    try { j = await r.json(); } catch (e) { }
    if (!r.ok) throw new Error((j && typeof j.detail === "string" && j.detail) || `Something went wrong (${r.status}).`);
    return j;
  }

  function draw(keys) {
    const list = $("keys-list");
    if (!keys.length) {
      const li = document.createElement("li");
      li.className = "menu-empty";
      li.textContent = "No keys yet.";
      list.replaceChildren(li);
      return;
    }
    list.replaceChildren(...keys.map(k => {
      const li = document.createElement("li"), meta = document.createElement("span"), b = document.createElement("b"), info = document.createElement("span");
      meta.className = "keys-meta";
      b.textContent = k.name;
      info.textContent = `${k.prefix}… made ${day(k.created)}, last used ${day(k.last_used)}`;
      meta.append(b, info);
      const del = document.createElement("button");
      del.type = "button";
      del.textContent = "Delete";
      del.setAttribute("aria-label", `Delete the key ${k.name}`);
      del.onclick = async () => {
        if (!confirm(`Delete the key "${k.name}"? Claude can no longer use it.`)) return;
        try { await call(`/api/keys/${encodeURIComponent(k.id)}`, {method: "DELETE"}); say(""); load(); } catch (e) { say(e.message); }
      };
      li.append(meta, del);
      return li;
    }));
  }

  async function load() {
    try { draw((await call("/api/keys")).keys); } catch (e) { say(e.message); }
  }

  $("keys-form").onsubmit = async e => {
    e.preventDefault();
    say("");
    try {
      const k = await call("/api/keys", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name: $("keys-name").value.trim()})});
      $("keys-name").value = "";
      $("keys-token").textContent = k.key;
      $("keys-cmd").textContent = command(k.key);
      $("keys-new").hidden = false;
      load();
    } catch (err) { say(err.message); }
  };

  $("keys-copy").onclick = async () => {
    try { await navigator.clipboard.writeText($("keys-cmd").textContent); $("keys-copy").textContent = "Copied"; }
    catch (e) { $("keys-copy").textContent = "Select the command and copy it"; }
  };

  const close = () => { if (dlg.open) dlg.close(); };
  btn.onclick = () => {
    $("who-menu").hidden = true;
    $("who").setAttribute("aria-expanded", "false");
    $("keys-new").hidden = true;
    $("keys-token").textContent = $("keys-cmd").textContent = "";
    $("keys-copy").textContent = "Copy the command";
    say("");
    dlg.showModal();
    $("keys-name").focus();
    load();
  };
  $("keys-close").onclick = close;
  dlg.addEventListener("close", () => { $("keys-token").textContent = $("keys-cmd").textContent = ""; $("keys-new").hidden = true; $("who").focus(); });
  dlg.addEventListener("click", e => { if (e.target === dlg) close(); });
})();
