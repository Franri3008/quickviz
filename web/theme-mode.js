(function () {
  const KEY = "qv-theme";
  const root = document.documentElement;
  const mq = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;
  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { }
  const pick = () => (saved === "dark" || saved === "light" ? saved : mq && mq.matches ? "dark" : "light");
  function apply() {
    const t = pick();
    if (root.dataset.theme === t) return;
    root.dataset.theme = t;
    root.style.colorScheme = t;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = t === "dark" ? "#131517" : "#ffffff";
    window.dispatchEvent(new CustomEvent("qv-theme", {detail: t}));
  }
  apply();
  if (mq && mq.addEventListener) mq.addEventListener("change", () => { if (!saved) apply(); });
  document.addEventListener("DOMContentLoaded", apply);
  window.QVTheme = {
    get: () => root.dataset.theme,
    toggle() {
      saved = root.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, saved); } catch (e) { }
      apply();
    },
  };
})();
