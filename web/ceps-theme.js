(function () {
  const green = "#207164", navy = "#0c2443", red = "#b02441", grey = "#6b6b69";

  const C = {
    name: "ceps",
    font: 'Carlito, Calibri, "Segoe UI", sans-serif',
    webFont: true,
    fs: { min: 13, tick: 15, label: 16, title: 18 },

    green, navy, red, grey,
    grey2: "#a3a3a1", grey3: "#d4d4d2", yellow: "#f2c64b",
    greenTint: "#c4ded9", navyTint: "#b7c0cc", greyTint: "#e6e6e4",
    ink: "#1a1a1a", rule: "#e3e3e1", paper: "#ffffff", gridDash: "2 3",

    primary: green, focusColor: green, euColor: navy,
    hl: [green, red, "#56998c", "#d0687f", "#4a5f80", "#f2c64b"],
    dot: { a: green, b: navy, aTime: "#8fc0b6", bTime: green },

    focus: "BE",
    eu: ["EU27", "EU"],

    country(geo) {
      if (geo === C.focus) return green;
      if (C.eu.indexOf(geo) >= 0) return navy;
      return grey;
    },
    countryTint(geo) {
      if (geo === C.focus) return C.greenTint;
      if (C.eu.indexOf(geo) >= 0) return C.navyTint;
      return C.greyTint;
    },

    region: {
      BE1: navy,  Brussels: navy,
      BE2: green, Flanders: green,
      BE3: red,   Wallonia: red,
    },

    seq: ["#eef5f3", "#c4ded9", "#8fc0b6", "#56998c", "#207164", "#134a41"],
    div: [red, "#e3b3be", "#f6f6f4", "#c4ded9", green],
    divLo: red, divHi: green, mid: "#ffffff",
    heat: ["#ffffff", "#56998c", "#134a41"],
    noData: "#f1f1ef",
    water: null,

    cat: [green, navy, red, grey, "#f2c64b", "#56998c", "#4a5f80", "#d0687f", "#a3a3a1", "#8fc0b6"],

    named: {
      "green": green, "navy": navy, "red": red, "grey": grey, "light grey": "#a3a3a1", "yellow": "#f2c64b",
      "light green": "#8fc0b6", "teal": "#56998c", "slate": "#4a5f80", "rose": "#d0687f",
    },
    shades: { "white": "#ffffff", "light grey": "#f7f7f5", "pale green": "#eef5f3", "pale blue": "#e9eef5", "pale yellow": "#fdf8e6" },

    ctl: { ink: "#1a1a1a", label: "#6b6b69", border: "1px solid #d4d4d2", btnBg: "#ffffff", btnInk: "#4a4a48",
      accent: green, onAccent: "#ffffff", track: "#c4ded9", radius: 0, trackRadius: 10, pill: false, twoWay: "buttons", weight: 400, checkInk: "#1a1a1a",
      playBg: green, playInk: "#ffffff", playBorder: "1px solid " + green, focus: "2px solid " + green },

    tile: null,
    logo: null,

    sectorOrder: ["J", "M, N", "B–E", "F", "K", "O, P, Q", "A", "R–U", "L", "G, H, I"],
    sectorColor(name, i) {
      const k = C.sectorOrder.indexOf(String(name).split(" — ")[0]);
      return C.cat[(k >= 0 ? k : i) % C.cat.length];
    },
  };

  window.QV_THEMES = Object.assign(window.QV_THEMES || {}, { ceps: C });
  window.CEPS = C;
})();
