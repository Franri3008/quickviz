(() => {
  const DB = "qv-keep", STORE = "pages";
  let opening = null;

  function db() {
    if (!opening) opening = new Promise((ok, no) => {
      if (!window.indexedDB) { no(new Error("no IndexedDB")); return; }
      const r = indexedDB.open(DB, 1);
      r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains(STORE)) r.result.createObjectStore(STORE); };
      r.onsuccess = () => { r.result.onversionchange = () => { r.result.close(); opening = null; }; ok(r.result); };
      r.onerror = () => no(r.error);
      r.onblocked = () => no(new Error("blocked"));
    }).catch(e => { opening = null; throw e; });
    return opening;
  }

  function run(mode, fn) {
    return db().then(d => new Promise((ok, no) => {
      const tx = d.transaction(STORE, mode);
      let out;
      fn(tx.objectStore(STORE), v => { out = v; });
      tx.oncomplete = () => ok(out);
      tx.onerror = tx.onabort = () => no(tx.error || new Error("aborted"));
    }));
  }

  function get(owner) {
    return run("readonly", (st, done) => {
      const got = {};
      const a = st.get([owner, "ui"]), b = st.get([owner, "data"]);
      a.onsuccess = () => { got.ui = a.result; done(got); };
      b.onsuccess = () => { got.data = b.result; done(got); };
    });
  }

  function put(owner, parts) {
    return run("readwrite", st => { for (const [k, v] of Object.entries(parts)) st.put(v, [owner, k]); });
  }

  function drop(owner) {
    return run("readwrite", st => st.delete(IDBKeyRange.bound([owner], [owner, []])));
  }

  function prune(maxAge) {
    const old = Date.now() - maxAge;
    return run("readwrite", st => {
      const keys = [], fresh = new Set();
      const c = st.openCursor();
      c.onsuccess = () => {
        const cur = c.result;
        if (cur) {
          keys.push(cur.key);
          if (cur.key[1] === "ui" && cur.value && cur.value.at > old) fresh.add(cur.key[0]);
          cur.continue();
          return;
        }
        for (const k of keys) if (!fresh.has(k[0])) st.delete(k);
      };
    });
  }

  window.QVKeep = {get, put, drop, prune};
})();
