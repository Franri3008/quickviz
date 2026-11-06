(() => {
  const stub = () => new Proxy(function () {}, {
    get(t, k) {
      if (k === Symbol.toPrimitive) return () => "";
      if (k === "then") return undefined;
      if (!(k in t)) t[k] = stub();
      return t[k];
    },
    set(t, k, v) { t[k] = v; return true; },
    apply() { return stub(); },
  });
  const frame = {mount: () => ({render: () => Promise.resolve({errors: []}), clear: () => Promise.resolve(null), settled: () => Promise.resolve(),
    png: () => Promise.resolve(null), state: () => Promise.resolve({}), outline: () => Promise.resolve(""), sig: () => Promise.resolve(null)})};
  const USES = ["state", "toData", "namesColumns", "namesBody", "firstRecipe", "namedRecipe", "withAutoControls", "applyChange", "buildSpec",
    "kindOptions", "chatBody", "catKey", "rateText", "KIND_NAMES", "NO_CHANGE"];
  const PATCH_ONLY = "That change needs code that runs in the browser, and the server cannot run it, so nothing changed. Try saying it another way.";
  const PATCH_LEFT = "Part of that change needs code that runs in the browser, so that part was left out.";
  let app = null;

  function boot(src) {
    const watcher = function () { return stub(); };
    app = new Function("document", "QVFrame", "fetch", "localStorage", "ResizeObserver", "MutationObserver", src + "\nreturn {" + USES.join(", ") + "};")(
      stub(), frame, () => Promise.reject(new Error("offline")), stub(), watcher, watcher);
  }

  async function load(input) {
    const s = app.state;
    s.data = app.toData(input.data);
    s.style = input.style;
    s.names = input.names || null;
    s.recipe = input.recipe || null;
    s.spec = null;
    if (QV.loadRegionIndex) await QV.loadRegionIndex();
    return s;
  }

  async function columns(input) {
    const d = (await load(input)).data;
    return {text: input.text || "", columns: app.namesColumns(), file: d.name || "", sheet: d.sheets && d.sheets.length > 1 ? d.sheet || "" : ""};
  }

  async function plan(input) {
    const s = await load(input), p = input.decide;
    s.decide = p.guess ? null : p;
    const first = app.firstRecipe(p, null);
    if (!first) return {recipe: null, kinds: []};
    const recipe = app.withAutoControls(first);
    return {recipe, names: {...app.namesBody(recipe), text: input.text || ""}, kinds: app.kindOptions(first.kind, p.ranked)};
  }

  async function finish(input) {
    const s = await load(input);
    let recipe = input.recipe;
    if (input.first && s.names) recipe = app.namedRecipe(recipe, s.names);
    s.recipe = recipe;
    const spec = app.buildSpec(recipe);
    if (!spec.rows.length) throw new Error("That leaves nothing to draw.");
    return {recipe, names: s.names, spec, kind: app.KIND_NAMES[recipe.kind] || recipe.kind};
  }

  async function chat(input) {
    const s = await load(input);
    s.spec = app.buildSpec(s.recipe);
    return app.chatBody(s.recipe, input.message, []);
  }

  async function apply(input) {
    const s = await load(input), base = input.recipe, res = input.res;
    const set = res.set || {}, ops = res.ops || [];
    const changed = Object.keys(set).length || ops.length || !!res.patch;
    let reply = res.reply || (changed ? "Done." : "I did not change anything.");
    if (!changed) return {recipe: base, reply, changed: false};
    if (res.patch && !Object.keys(set).length && !ops.length) return {recipe: base, reply: PATCH_ONLY, changed: false};
    let next;
    try { next = app.withAutoControls(app.applyChange(base, {set, ops})); }
    catch (e) { return {recipe: base, reply: e.message, changed: false}; }
    reply = app.rateText(res, next, reply);
    if (res.patch) reply = (reply + " " + PATCH_LEFT).trim();
    const same = JSON.stringify(app.buildSpec(base)) === JSON.stringify(app.buildSpec(next));
    if (same) return {recipe: base, reply: app.NO_CHANGE, changed: false};
    s.recipe = next;
    const retitle = next.title == null && s.names && app.catKey(next) !== app.catKey(base);
    return {recipe: next, reply, changed: true, names: retitle ? app.namesBody(next) : null};
  }

  window.QVPipe = {boot, columns, plan, finish, chat, apply};
})();
