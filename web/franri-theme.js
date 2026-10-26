(function () {
  const petrol = "#13759a", tangerine = "#c4540c", indigo = "#6348f2", green = "#25984d", rose = "#e56c7f", sky = "#069ce4";
  const berry = "#a0446e", gold = "#aa9117", magenta = "#d915a9", forest = "#466f45", crimson = "#c42f4f";
  const ash = "#7a766f", pebble = "#8a857e";

  const F = {
    name: "franri",
    font: 'Carlito, Calibri, "Segoe UI", sans-serif',
    webFont: true,
    fs: { min: 13, tick: 15, label: 16, title: 18 },

    green, navy: indigo, red: crimson, grey: ash,
    grey2: pebble, grey3: "#d3d0cb", yellow: gold,
    greenTint: "#f6d9c6", navyTint: "#e0dbfc", greyTint: "#e8e6e3",
    ink: "#1c1917", rule: "#e2dfda", paper: "#ffffff", gridDash: "2 3",

    primary: petrol, focusColor: tangerine, euColor: indigo,
    hl: [tangerine, green, sky, magenta, gold, petrol],
    dot: { a: petrol, b: tangerine, aTime: pebble, bTime: petrol },

    focus: "BE",
    eu: ["EU27", "EU"],

    country(geo) {
      if (geo === F.focus) return tangerine;
      if (F.eu.indexOf(geo) >= 0) return indigo;
      return pebble;
    },
    countryTint(geo) {
      if (geo === F.focus) return F.greenTint;
      if (F.eu.indexOf(geo) >= 0) return F.navyTint;
      return F.greyTint;
    },

    region: {
      BE1: indigo,    Brussels: indigo,
      BE2: petrol,    Flanders: petrol,
      BE3: tangerine, Wallonia: tangerine,
    },

    seq: ["#f3f8e6", "#cfe8c9", "#97d0bf", "#58b0b4", "#2a8aa3", "#14638a", "#0d3f63"],
    div: ["#8c3b0c", "#e9b894", "#f7f6f3", "#9ccbd6", "#0d5a75"],
    divLo: "#8c3b0c", divHi: "#0d5a75", mid: "#ffffff",
    heat: ["#ffffff", "#5fa3bd", "#0d3f63"],
    noData: "#e8e6e3",
    water: "#eaf3f6",

    cat: [petrol, tangerine, green, indigo, rose, sky, berry, gold, magenta, forest],

    named: {
      "green": green, "navy": indigo, "red": crimson, "grey": ash, "light grey": pebble, "yellow": gold,
      "light green": "#4f9d5a", "teal": "#0f8584", "slate": "#5b6f8a", "rose": rose,
      "blue": petrol, "petrol": petrol, "orange": tangerine, "tangerine": tangerine, "indigo": indigo, "violet": indigo,
      "purple": indigo, "pink": magenta, "magenta": magenta, "berry": berry, "gold": gold, "sky": sky, "cyan": sky, "forest": forest,
    },
    shades: { "white": "#ffffff", "light grey": "#f7f6f4", "pale green": "#eef6ee", "pale blue": "#ecf4f7", "pale yellow": "#fbf6e4" },

    ctl: { ink: "#1c1917", label: "#4a4641", border: "1px solid rgba(28, 25, 23, 0.16)", btnBg: "#f7f6f4", btnInk: "#4a4641",
      accent: petrol, onAccent: "#ffffff", track: "#d3e7ef", radius: 6, trackRadius: 6, pill: true, twoWay: "buttons", weight: 700, checkInk: "#4a4641",
      playBg: "#f7f6f4", playInk: ash, playBorder: "1px solid rgba(28, 25, 23, 0.16)", focus: "2px solid " + petrol },

    tile: null,
    logo: null,

    sectorOrder: ["J", "M, N", "B–E", "F", "K", "O, P, Q", "A", "R–U", "L", "G, H, I"],
    sectorColor(name, i) {
      const k = F.sectorOrder.indexOf(String(name).split(" — ")[0]);
      return F.cat[(k >= 0 ? k : i) % F.cat.length];
    },
  };

  window.QV_THEMES = Object.assign(window.QV_THEMES || {}, { franri: F });
})();
