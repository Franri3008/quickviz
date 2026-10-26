const fs = require("fs");
const path = require("path");
const vm = require("vm");

const web = path.join(__dirname, "..", "web");
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

const ctx = {console, setTimeout, clearTimeout, Promise, JSON, Math, Date, Map, Set, URLSearchParams, AbortController};
ctx.window = ctx;
ctx.globalThis = ctx;
ctx.document = stub();
ctx.__stub = stub;
ctx.location = {href: ""};
ctx.localStorage = stub();
ctx.requestAnimationFrame = () => 0;
ctx.addEventListener = () => {};
ctx.fetch = () => Promise.reject(new Error("offline"));
ctx.Option = function (text, value) { this.text = text; this.value = value; };
ctx.QV = {
  ready: new Promise(() => {}),
  countryId: n => (globalThis.__countries || {})[n] || null,
  isEU: n => /^(eu|eu27|eu 27|eu27_2020|euro area)$/i.test(String(n).trim()),
  regionCountry: () => null,
  loadRegionIndex: () => Promise.resolve(null),
  render: () => {},
};
ctx.QVFrame = {mount: () => ({render: () => Promise.resolve({errors: []}), clear: () => Promise.resolve(null), settled: () => Promise.resolve(),
  png: () => Promise.resolve(null), state: () => Promise.resolve({}), outline: () => Promise.resolve(""), sig: () => Promise.resolve(null)})};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(web, "vendor", "d3.min.js"), "utf8"), ctx);
vm.runInContext(fs.readFileSync(path.join(web, "charts-mock.js"), "utf8"), ctx, {filename: "charts-mock.js"});
vm.runInContext(fs.readFileSync(path.join(web, "app.js"), "utf8"), ctx, {filename: "app.js"});

let src = "";
process.stdin.on("data", d => (src += d));
process.stdin.on("end", () => {
  const out = vm.runInContext(src, ctx, {filename: "test.js"});
  Promise.resolve(out).then(v => process.stdout.write(JSON.stringify(v === undefined ? null : v)));
});
