(() => {
  const $ = id => document.getElementById(id);
  const SAY = {
    blocked: "This account is blocked. You can still use QuickViz without signing in.",
    failed: "Sign-in did not work. Please try again.",
    cancelled: "Sign-in was cancelled.",
  };
  let me = null, timer = 0, ask = null;

  function paint() {
    if (!me) return;
    const left = me.credits_left;
    $("credits").textContent = `${left.toLocaleString("en")} ${left === 1 ? "credit" : "credits"} left today`;
    $("credits").title = `${me.credits_day.toLocaleString("en")} credits a day. They come back at midnight UTC.`;
    $("credits").classList.toggle("low", left <= 0);
    $("credits").hidden = false;
    $("signin").hidden = me.signed_in || !me.sign_in;
    $("who-wrap").hidden = !me.signed_in;
    $("who-email").textContent = me.email || "";
    $("who-line").textContent = me.email ? `Signed in as ${me.email}` : "";
    $("admin-link").hidden = !me.is_admin;
    if (left > 0 && $("cap-banner").dataset.reason === "credits") $("cap-banner").hidden = true;
  }

  async function load() {
    if (ask) return ask;
    ask = fetch("/api/me", {credentials: "same-origin"}).then(r => (r.ok ? r.json() : null)).then(j => { if (j) { me = j; paint(); } })
      .catch(() => {}).finally(() => { ask = null; });
    return ask;
  }

  function refresh() {
    clearTimeout(timer);
    timer = setTimeout(load, 250);
  }

  async function signIn(ev) {
    ev.preventDefault();
    const go = () => { location.href = "/auth/google/login"; };
    const save = window.QVSave ? Promise.race([QVSave(), new Promise(ok => setTimeout(ok, 1500))]) : Promise.resolve();
    save.then(go, go);
  }

  function closeMenu() {
    $("who-menu").hidden = true;
    $("who").setAttribute("aria-expanded", "false");
  }

  $("signin").addEventListener("click", signIn);
  $("cap-signin").addEventListener("click", signIn);
  $("who").addEventListener("click", () => {
    const open = $("who-menu").hidden;
    $("who-menu").hidden = !open;
    $("who").setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", ev => { if (!$("who-wrap").contains(ev.target)) closeMenu(); });
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && !$("who-menu").hidden) { closeMenu(); $("who").focus(); } });
  $("signout").addEventListener("click", async () => {
    closeMenu();
    try { await fetch("/api/logout", {method: "POST", credentials: "same-origin"}); } catch (e) { }
    $("cap-banner").hidden = true;
    load();
  });

  const said = new URLSearchParams(location.search).get("signin");
  if (said) {
    if (SAY[said] && $("err")) { $("err").textContent = SAY[said]; $("err").hidden = false; }
    history.replaceState(null, "", location.pathname + location.hash);
  }

  window.QVCredits = {refresh, load, get: () => me};
  load();
})();
