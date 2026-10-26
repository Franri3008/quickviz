import pytest

from app.viz_chat import SYSTEM, ChangeError, validate_change

COLUMNS = [
    {"name": "country", "type": "category", "distinct": 3, "values": ["Spain", "Belgium", "EU27"]},
    {"name": "firm_size", "type": "category", "distinct": 2, "values": ["Small", "Large"]},
    {"name": "year", "type": "time", "distinct": 6, "values": ["2020", "2021", "2022", "2023", "2024", "2025"]},
    {"name": "all_firms", "type": "number", "distinct": 30, "min": 1.0, "max": 40.0},
    {"name": "large_firms", "type": "number", "distinct": 30, "min": 5.0, "max": 60.0},
]
NAMES = ["Spain", "Belgium", "EU27"]


def change(**set_):
    return validate_change({"reply": "ok", "set": set_}, COLUMNS, NAMES)


@pytest.mark.parametrize("fields", [
    {"textHalo": "on"},
    {"textHalo": "auto"},
    {"fontSize": 9},
    {"fontSize": 12},
    {"fontSize": 24},
    {"fontSize": "small"},
    {"textColor": "navy"},
    {"textColor": "black"},
    {"background": "transparent"},
    {"background": "pale green"},
    {"border": "on"},
    {"padding": 0},
    {"padding": 40},
    {"labelMax": 12},
    {"thousands": "space"},
    {"thousands": "none", "decimalMark": "comma"},
    {"numberStyle": "full"},
    {"numberStyle": "short"},
    {"axisTitles": "off"},
    {"legendTitle": "Firm size"},
    {"opacity": 0.5},
    {"lineStyle": "dotted"},
    {"dashed": ["EU27"]},
    {"markerShape": "square"},
    {"markerShape": "triangle"},
    {"titleSize": 22},
    {"flags": "auto"},
    {"flags": "on"},
    {"flags": "off"},
    {"fontStyle": {"source": "italic"}},
    {"fontStyle": {"title": "bold italic", "tickLabels": "bold", "note": "normal"}},
    {"fontStyle": {"title": None}},
    {"fontStyle": None},
    {"dimSize": "small"},
    {"dimSize": "normal"},
    {"dimSize": 11},
    {"dimSize": None},
])
def test_look_fields_pass(fields):
    assert change(**fields)["set"] == fields


def test_font_size_in_px_text_is_read():
    assert change(fontSize="11px")["set"] == {"fontSize": 11}
    assert change(fontSize="10")["set"] == {"fontSize": 10}
    assert change(fontSize=12.4)["set"] == {"fontSize": 12}


@pytest.mark.parametrize("fields", [
    {"fontSize": 8},
    {"fontSize": 25},
    {"fontSize": "8px"},
    {"textHalo": "glow"},
    {"textColor": "pink"},
    {"background": "black"},
    {"border": True},
    {"padding": 60},
    {"labelMax": 2},
    {"thousands": "dot"},
    {"decimalMark": "space"},
    {"numberStyle": "scientific"},
    {"opacity": 0},
    {"opacity": 1.5},
    {"lineStyle": "wavy"},
    {"markerShape": "star"},
    {"titleSize": 40},
    {"dashed": ["Atlantis"]},
    {"flags": "yes"},
    {"flags": True},
    {"fontStyle": {"title": "underline"}},
    {"fontStyle": {"subtitle": "bold"}},
    {"fontStyle": "bold"},
    {"dimSize": 8},
    {"dimSize": 25},
    {"dimSize": "large"},
])
def test_look_fields_rejected(fields):
    with pytest.raises(ChangeError):
        change(**fields)


def test_font_style_words_and_part_names_are_read_loosely():
    assert change(fontStyle={"xLabel": "Bold-Italic", "values": "regular", "source": "Italics"})["set"] == {
        "fontStyle": {"axisTitle": "bold italic", "valueLabels": "normal", "source": "italic"}}


def test_font_style_is_kept_on_every_kind():
    for kind in ("map", "histogram", "treemap", "sankey"):
        out = validate_change({"reply": "Made the source italic.", "set": {"fontStyle": {"source": "italic"}}}, COLUMNS, NAMES, kind=kind, caps=True)
        assert out["set"] == {"fontStyle": {"source": "italic"}} and "dropped" not in out


def test_prompt_teaches_bold_and_italic():
    for line in ['"Make the source italic" -> "set": {"fontStyle": {"source": "italic"}}',
                 '"Make the title italic" -> "set": {"fontStyle": {"title": "bold italic"}}',
                 "Never say the chart cannot do bold or italic.", "Title, titleAlign, titleSize, fontStyle, note"]:
        assert line in SYSTEM


def test_dim_size_reads_px_and_is_taught():
    assert change(dimSize="11px")["set"] == {"dimSize": 11}
    assert change(dimSize=10.4)["set"] == {"dimSize": 10}
    assert '"Make the other names smaller" when a highlight is set -> "set": {"dimSize": "small"}' in SYSTEM
    assert "When no highlight is set, leave dimSize out" in SYSTEM
    out = validate_change({"reply": "Smaller.", "set": {"dimSize": "small"}}, COLUMNS, NAMES, kind="line", caps=True)
    assert out["set"] == {} and out["dropped"] == ["dimSize"]


def test_dashed_names_are_matched():
    assert change(dashed=["eu 27"])["set"]["dashed"] == ["EU27"]


def test_prompt_names_the_new_fields_and_controls():
    for f in ["textHalo", "textColor", "background", "border", "padding", "labelMax", "thousands", "decimalMark", "numberStyle",
              "axisTitles", "opacity", "lineStyle", "dashed", "markerShape", "titleSize", "flags", "controls", '"type": "legend"', '"type": "checkbox"',
              '"type": "slider"', '"type": "switch"', '"type": "select"']:
        assert f in SYSTEM
    assert "Even smaller" in SYSTEM or "even smaller" in SYSTEM
    assert "Never refuse a look request because of house style." in SYSTEM


def test_controls_legend_checkbox_slider():
    out = change(controls=[{"type": "legend"}, {"type": "checkbox", "label": "Countries", "field": "cat"},
                           {"type": "slider", "column": "Year", "label": "Year", "play": True}])["set"]["controls"]
    assert out == [{"type": "legend"}, {"type": "checkbox", "label": "Countries", "field": "cat"},
                   {"type": "slider", "label": "Year", "column": "year", "play": True}]


def test_controls_switch_with_options_checks_ops():
    out = change(controls=[{"type": "switch", "options": [
        {"label": "All firms", "ops": [{"op": "roles", "v": "all firms"}]},
        {"label": "Large firms", "ops": [{"op": "roles", "v": "large_firms"}], "set": {"yLabel": "Large firms (%)"}},
    ]}])["set"]["controls"][0]
    assert out["options"][0] == {"label": "All firms", "set": {}, "ops": [{"op": "roles", "v": "all_firms"}]}
    assert out["options"][1]["set"] == {"yLabel": "Large firms (%)"}


def test_controls_switch_on_two_value_column_and_select_buttons():
    out = change(controls=[{"type": "switch", "column": "firm_size"}, {"type": "select", "column": "country", "style": "buttons"}])
    assert [c["column"] for c in out["set"]["controls"]] == ["firm_size", "country"]


def test_controls_percent_switch():
    out = change(controls=[{"type": "switch", "label": "Show", "options": [
        {"label": "Values", "ops": [{"op": "percent_share", "within": "none"}]},
        {"label": "Shares", "ops": [{"op": "percent_share", "within": "total"}], "set": {"unit": "%"}},
    ]}])
    assert out["set"]["controls"][0]["options"][1]["set"] == {"unit": "%"}


def test_controls_empty_list_removes():
    assert change(controls=[])["set"] == {"controls": []}
    assert change(controls=None)["set"] == {"controls": None}


@pytest.mark.parametrize("controls", [
    [{"type": "knob"}],
    [{"type": "legend"}, {"type": "legend"}],
    [{"type": "legend", "column": "year"}],
    [{"type": "slider"}],
    [{"type": "slider", "column": "nope"}],
    [{"type": "switch", "column": "country"}],
    [{"type": "switch", "options": [{"label": "a", "ops": [{"op": "sort", "by": "value"}]}]}],
    [{"type": "switch", "options": [{"label": "a", "ops": [{"op": "sort", "by": "value"}]}, {"label": "b", "ops": [{"op": "sort", "by": "value"}]},
                                    {"label": "c", "ops": [{"op": "sort", "by": "label"}]}]}],
    [{"type": "select", "column": "all_firms"}],
    [{"type": "select", "column": "year", "options": [{"label": "a", "set": {"title": "x"}}, {"label": "b", "set": {"title": "y"}}]}],
    [{"type": "select", "options": [{"label": "a", "set": {"kind": "bar"}}, {"label": "b", "set": {"title": "y"}}]}],
    [{"type": "select", "options": [{"label": "a", "set": {"fontSize": 99}}, {"label": "b", "set": {"title": "y"}}]}],
    [{"type": "select", "options": [{"label": "a"}, {"label": "b", "set": {"title": "y"}}]}],
    [{"type": "select", "options": [{"label": "a", "ops": [{"op": "filter", "column": "country", "keep": ["Atlantis"]}]},
                                    {"label": "b", "set": {"title": "y"}}]}],
    [{"type": "legend"}, {"type": "checkbox"}, {"type": "slider", "column": "year"}, {"type": "switch", "column": "firm_size"},
     {"type": "select", "column": "country"}],
])
def test_bad_controls_rejected(controls):
    with pytest.raises(ChangeError):
        change(controls=controls)


def test_shade_takes_one_range_or_a_list():
    assert change(shade={"from": 2026, "label": "Projection"})["set"] == {"shade": [{"from": 2026, "label": "Projection"}]}
    assert change(shade=[{"from": "2021", "to": 2023.0}, {"to": "2020", "opacity": 0.3}])["set"]["shade"] == [{"from": 2021, "to": 2023}, {"to": 2020, "opacity": 0.3}]
    assert change(shade={"from": "spain", "to": "EU27"})["set"]["shade"] == [{"from": "Spain", "to": "EU27"}]
    assert change(shade={"from": 2026, "label": " Projection → "})["set"]["shade"][0]["label"] == "Projection"


def test_shade_null_or_empty_removes_it():
    assert change(shade=None)["set"] == {"shade": None}
    assert change(shade=[])["set"] == {"shade": []}


@pytest.mark.parametrize("shade", [
    {},
    {"label": "Projection"},
    {"from": 2030, "to": 2020},
    {"from": 2026, "opacity": 0.05},
    {"from": 2026, "opacity": 0.95},
    {"from": 2026, "label": "x" * 31},
    {"from": 2026, "color": "red"},
    {"from": "Atlantis"},
    [{"from": 2020}, {"from": 2021}, {"from": 2022}, {"from": 2023}],
    "from 2026",
])
def test_bad_shade_rejected(shade):
    with pytest.raises(ChangeError):
        change(shade=shade)


def test_shade_is_drawn_by_the_axis_kinds_only():
    from app.capabilities import CAPS, unsupported
    for kind in ("line", "stacked_area", "bar", "stacked_bar"):
        assert "shade" in CAPS["kinds"][kind]
    assert unsupported({"shade": [{"from": 2026}]}, "scatter") == ["shade"]
    assert CAPS["labels"]["shade"] == "shaded range"


def test_prompt_says_shade_not_patch_and_keep_effects():
    assert '"Tint the projection years from 2026" -> "set": {"shade": {"from": 2026, "label": "Projection"}}' in SYSTEM
    assert "Always use shade, never a patch, to shade, tint, dim or fade a range of years or categories." in SYSTEM
    assert "It never touches g.axis or its text, .qv-axis-title or the legend." in SYSTEM
    assert "Never remove an existing shade or patch unless the user asks to remove or undo it." in SYSTEM


FUELS = (("LNG", 0.27, -0.002), ("Coal", 0.38, -0.009), ("Nuclear", 0.28, 0.003), ("Renewables", 0.05, 0.008), ("Others", 0.02, 0.0))
KOREA = [{"t": str(y), "series": s, "v": round((560 + 6 * i) * (a + b * i), 1)} for i, y in enumerate(range(2016, 2039)) for s, a, b in FUELS]


def draw_shaded(spec, tmp_path, patches=()):
    import html
    import json
    import re
    import subprocess

    from tests.test_capabilities import ROOT, _chrome
    chrome = _chrome()
    if not chrome:
        pytest.skip("needs chrome")
    web = (ROOT / "web").as_uri()
    page = tmp_path / "shade.html"
    page.write_text(f"""<!doctype html><html><head><meta charset="utf-8"></head><body style="width:760px"><svg id="chart"></svg><pre id="out"></pre>
<script src="{web}/vendor/d3.min.js"></script><script src="{web}/ceps-theme.js"></script><script src="{web}/aiw-theme.js"></script><script src="{web}/charts.js"></script>
<script>
const svg = document.getElementById("chart");
QV.render(svg, {json.dumps(spec)}, {{still: true, width: 760, patches: {json.dumps(list(patches))}}});
const plot = svg.querySelector(".qv-plot"), r = e => e.getBoundingClientRect();
const hit = (a, b) => a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;
const bands = [...svg.querySelectorAll(".qv-plot rect.qv-shade-band")];
const axes = [...plot.querySelectorAll(":scope > g.axis")];
const bottom = axes.find(a => /translate\\(0,\\s*[1-9]/.test(a.getAttribute("transform") || ""));
const ih = bottom ? +bottom.getAttribute("transform").match(/,\\s*([\\d.]+)/)[1] : null;
const dom = bottom && bottom.querySelector(".domain"), iw = dom ? Math.max(...(dom.getAttribute("d").match(/[\\d.]+/g) || []).map(Number)) : null;
const tickText = [...plot.querySelectorAll("g.axis .tick text")];
const others = [...tickText, ...svg.querySelectorAll(".qv-axis-title"), ...svg.querySelectorAll(".qv-legend text, .qv-legend rect, .qv-legend circle")];
document.getElementById("out").textContent = JSON.stringify({{
  ih, iw, bg: svg.querySelector(".qv-bg").getAttribute("fill"), used: svg.__qv.used,
  bands: bands.map(b => ({{x: +b.getAttribute("x"), y: +b.getAttribute("y"), w: +b.getAttribute("width"), h: +b.getAttribute("height"),
    fill: b.getAttribute("fill"), op: +b.getAttribute("fill-opacity")}})),
  labels: [...svg.querySelectorAll(".qv-plot text.qv-shade-label")].map(t => ({{text: t.textContent, x: +t.getAttribute("x"), y: +t.getAttribute("y"), w: t.getBBox().width}})),
  ticks: Object.fromEntries([...(bottom ? bottom.querySelectorAll(".tick") : [])].map(t => [t.textContent, +t.getAttribute("transform").match(/\\(([-\\d.]+)/)[1]])),
  tickLook: tickText.map(t => ({{text: t.textContent, opacity: getComputedStyle(t).opacity, own: t.getAttribute("opacity"), fo: t.getAttribute("fill-opacity"),
    style: t.getAttribute("style"), fill: t.getAttribute("fill"), groupOp: getComputedStyle(t.closest(".tick")).opacity, axisOp: getComputedStyle(t.closest("g.axis")).opacity}})),
  covered: others.filter(e => bands.some(b => hit(r(b), r(e)))).map(e => e.textContent || e.tagName),
  outline: QV.outline(svg, 8000),
}});
</script></body></html>""")
    r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--allow-file-access-from-files", "--dump-dom",
                        "--virtual-time-budget=3000", page.as_uri()], capture_output=True, text=True, timeout=60)
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
    assert m and m.group(1), r.stderr[-500:]
    return json.loads(html.unescape(m.group(1)))


def assert_axis_untouched(out, plain):
    assert out["covered"] == []
    assert [t["fill"] for t in out["tickLook"]] == [t["fill"] for t in plain["tickLook"]]
    for t in out["tickLook"]:
        assert t["opacity"] == t["groupOp"] == t["axisOp"] == "1", t
        assert t["own"] is None and t["fo"] is None and not t["style"], t


@pytest.mark.parametrize("style", ["ceps", "aiw"])
def test_korea_projection_shade_stays_in_the_plot(style, tmp_path):
    spec = {"kind": "stacked_area", "style": style, "title": "Korea electricity generation mix by fuel, 2016 to 2038",
            "xLabel": "Year", "yLabel": "TWh", "rows": KOREA}
    plain = draw_shaded(spec, tmp_path)
    out = draw_shaded({**spec, "shade": [{"from": 2026, "label": "Projection"}]}, tmp_path)
    assert plain["bands"] == [] and "shade" in out["used"]
    [band] = out["bands"]
    assert out["ih"] and out["iw"]
    assert band["y"] == 0 and abs(band["h"] - out["ih"]) < 0.01
    assert abs(band["x"] - out["ticks"]["2026"]) <= 0.5 and abs(band["x"] + band["w"] - out["iw"]) <= 0.5
    assert band["fill"] == out["bg"] and band["op"] == 0.55
    [label] = out["labels"]
    assert label["text"] == "Projection" and band["x"] < label["x"] and label["x"] + label["w"] < band["x"] + band["w"] and label["y"] < 30
    assert_axis_untouched(out, plain)


@pytest.mark.parametrize("spec", [
    {"kind": "line", "rows": KOREA, "shade": [{"from": "2026", "to": 2030}]},
    {"kind": "bar", "orientation": "vertical", "rows": [{"cat": str(y), "v": 10 + i} for i, y in enumerate(range(2016, 2039))], "shade": [{"from": 2026}]},
    {"kind": "stacked_bar", "orientation": "vertical", "stack": "absolute", "rows": [{**r, "cat": r["t"]} for r in KOREA if int(r["t"]) % 2 == 0],
     "shade": [{"from": 2026, "label": "Projection"}]},
])
def test_shade_on_other_axis_kinds_stays_in_the_plot(spec, tmp_path):
    out = draw_shaded(spec, tmp_path)
    plain = draw_shaded({k: v for k, v in spec.items() if k != "shade"}, tmp_path)
    [band] = out["bands"]
    assert band["y"] == 0 and abs(band["h"] - out["ih"]) < 0.01
    assert 0 < band["x"] and band["x"] + band["w"] <= out["iw"] + 0.01
    assert band["x"] < out["ticks"]["2026"] < band["x"] + band["w"]
    assert_axis_untouched(out, plain)


def test_horizontal_bar_shade_runs_across(tmp_path):
    rows = [{"cat": n, "v": v} for n, v in (("Spain", 30), ("Belgium", 20), ("EU27", 25), ("France", 12), ("Italy", 9))]
    out = draw_shaded({"kind": "bar", "orientation": "horizontal", "rows": rows, "shade": [{"from": "EU27", "to": "France", "label": "Group"}]}, tmp_path)
    [band] = out["bands"]
    assert band["x"] == 0 and band["y"] > 0 and band["h"] > 0
    assert out["covered"] == [] and out["labels"][0]["text"] == "Group"


def test_a_range_that_matches_nothing_draws_nothing(tmp_path):
    out = draw_shaded({"kind": "line", "rows": KOREA, "shade": [{"from": 2050}, {"to": 2010}]}, tmp_path)
    assert out["bands"] == []


def draw_probe(body, tmp_path):
    import html
    import json
    import re
    import subprocess

    from tests.test_capabilities import ROOT, _chrome
    chrome = _chrome()
    if not chrome:
        pytest.skip("needs chrome")
    web = (ROOT / "web").as_uri()
    page = tmp_path / "probe.html"
    page.write_text(f"""<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{web}/fonts/carlito.css"></head>
<body><svg id="chart"></svg><pre id="out"></pre>
<script src="{web}/vendor/d3.min.js"></script><script src="{web}/vendor/d3-sankey.min.js"></script><script src="{web}/ceps-theme.js"></script>
<script src="{web}/aiw-theme.js"></script><script src="{web}/charts.js"></script>
<script>
const svg = document.getElementById("chart");
const draw = (spec, w = 760) => {{ QV.render(svg, spec, {{still: true, width: w, noResize: true}}); return svg; }};
QV.ready.then(() => {{ {body} }}).catch(e => ({{error: String(e.stack)}})).then(out => {{ document.getElementById("out").textContent = JSON.stringify(out); }});
</script></body></html>""")
    r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--allow-file-access-from-files", "--dump-dom",
                        "--virtual-time-budget=3000", page.as_uri()], capture_output=True, text=True, timeout=60)
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
    assert m and m.group(1), r.stderr[-500:]
    out = json.loads(html.unescape(m.group(1)))
    assert not (isinstance(out, dict) and out.get("error")), out
    return out


COUNTRIES = ["Belgium", "Netherlands", "Luxembourg", "Germany", "France", "Italy", "Spain", "Portugal", "Austria", "Denmark", "Sweden", "EU27"]
LOOK = """
const look = sel => [...svg.querySelectorAll(sel)].filter(t => t.textContent).map(t => (t.getAttribute("font-style") || "") + (t.getAttribute("font-weight") || ""));
const inside = () => { const b = svg.getBoundingClientRect(), W = +svg.getAttribute("width"), H = +svg.getAttribute("height");
  return [...svg.querySelectorAll("text")].filter(t => { const r = t.getBoundingClientRect(); return r.width && (r.left < b.left - 1 || r.right > b.left + W + 1 || r.top < b.top - 1 || r.bottom > b.top + H + 1); }).map(t => t.textContent); };
"""


@pytest.mark.parametrize("style", ["ceps", "aiw"])
def test_font_style_reaches_every_part_and_keeps_text_inside(style, tmp_path):
    base = {"style": style, "title": "Share of enterprises using artificial intelligence by country in the last year", "xLabel": "Country",
            "yLabel": "Share of enterprises (%)", "note": "Enterprises with ten or more persons employed, all sectors except finance and agriculture",
            "source": "Eurostat, isoc_eb_ai, a long source name that runs to the edge", "valueLabels": "on", "highlight": ["Spain"]}
    every = {k: "bold italic" for k in ("title", "axisTitle", "tickLabels", "valueLabels", "legend", "note", "source")}
    rows = [{"cat": c, "v": 10.5 + i} for i, c in enumerate(COUNTRIES)]
    stack = [{"cat": c, "series": s, "v": 10 + i} for c in COUNTRIES[:5] for i, s in enumerate(("Small", "Large"))]
    import json
    out = draw_probe(LOOK + f"""
const base = {json.dumps(base)}, every = {json.dumps(every)}, rows = {json.dumps(rows)}, stack = {json.dumps(stack)};
const res = {{}};
for (const [k, s] of [["bar", {{kind: "bar", rows}}], ["stacked", {{kind: "stacked_bar", stack: "absolute", rows: stack}}], ["heatmap", {{kind: "heatmap", rows: stack}}],
                      ["donut", {{kind: "donut", rows: rows.slice(0, 5)}}], ["treemap", {{kind: "treemap", rows: rows.slice(0, 5)}}], ["sankey", {{kind: "sankey", rows: stack}}]]) {{
  draw({{...base, ...s, fontStyle: every}});
  res[k] = {{outside: inside(), used: svg.__qv.used.includes("fontStyle"), plain: [...svg.querySelectorAll(".qv-title, .qv-axis-title, .qv-note, .qv-source, .qv-legend text, .axis .tick text, .bar-label, .seg, .tot, .cv")]
    .filter(t => t.textContent && t.getAttribute("font-style") !== "italic").map(t => t.textContent)}};
}}
draw({{...base, kind: "bar", rows, fontStyle: {{source: "italic", title: "normal", tickLabels: "normal"}}}});
res.some = {{title: look(".qv-title"), source: look(".qv-source"), note: look(".qv-note"), axis: look(".qv-axis-title"),
  spain: [...svg.querySelectorAll(".qv-plot .axis .tick text")].filter(t => t.firstChild && t.firstChild.nodeValue === "Spain").map(t => (t.getAttribute("font-style") || "") + t.getAttribute("font-weight"))}};
draw({{...base, kind: "bar", rows}});
res.house = {{marked: svg.querySelectorAll("[font-style]").length, title: look(".qv-title")}};
return res;
""", tmp_path)
    for k in ("bar", "stacked", "heatmap", "donut", "treemap", "sankey"):
        assert out[k]["outside"] == [] and out[k]["plain"] == [] and out[k]["used"], (k, out[k])
    some = out["some"]
    assert some["title"] == ["400"] and some["source"] == ["italic400"] and some["note"] == ["400"] and set(some["axis"]) == {"700"}
    assert some["spain"] == ["700"]
    assert out["house"] == {"marked": 0, "title": ["700"]}


def test_bars_turn_horizontal_when_the_names_do_not_fit_flat(tmp_path):
    import json
    sets = {"countries": [{"cat": c, "v": 10 + i} for i, c in enumerate(COUNTRIES)],
            "five": [{"cat": c, "v": 10 + i} for i, c in enumerate(COUNTRIES[:5])],
            "letters": [{"cat": c, "v": i} for i, c in enumerate("ABCDEFGH")],
            "many": [{"cat": f"N{i}", "v": i} for i in range(31)]}
    out = draw_probe(f"""
const sets = {json.dumps(sets)}, res = {{}};
for (const [k, rows] of Object.entries(sets)) {{
  const seen = [];
  for (let w = 320; w <= 760; w += 4) {{ draw({{kind: "bar", rows}}, w); if (seen.at(-1)?.[1] !== svg.__qv.orient) seen.push([w, svg.__qv.orient]); }}
  res[k] = seen;
}}
draw({{kind: "bar", rows: sets.five}}, 760);
res.flat = [...svg.querySelectorAll(".axis .tick text")].filter(t => /rotate/.test(t.getAttribute("transform") || "")).length;
draw({{kind: "bar", rows: sets.countries, orientation: "vertical"}}, 760); res.vertical = svg.__qv.orient;
draw({{kind: "bar", rows: sets.letters, orientation: "horizontal"}}, 760); res.horizontal = svg.__qv.orient;
draw({{kind: "bar", rows: sets.countries, tickAngle: 45}}, 760); res.tilted = svg.__qv.orient;
const edge = res.five[1][0];
draw({{kind: "bar", rows: sets.five, fontStyle: {{tickLabels: "bold"}}}}, edge); res.bold = svg.__qv.orient;
draw({{kind: "bar", rows: sets.five}}, edge); res.plain = svg.__qv.orient;
draw({{kind: "stacked_bar", rows: sets.letters.map(r => ({{...r, series: "x"}}))}}, 760); res.stacked = svg.__qv.orient;
return res;
""", tmp_path)
    assert out["countries"] == [[320, "horizontal"]] and out["many"] == [[320, "horizontal"]] and out["letters"] == [[320, "vertical"]]
    [(_, first), (w, then)] = out["five"]
    assert first == "horizontal" and then == "vertical" and 360 < w < 760
    assert out["flat"] == 0
    assert out["vertical"] == "vertical" and out["horizontal"] == "horizontal" and out["tilted"] == "vertical" and out["stacked"] == "horizontal"
    assert out["plain"] == "vertical" and out["bold"] == "horizontal"


def test_dim_size_shrinks_only_the_other_names(tmp_path):
    import json
    rows = [{"cat": c, "v": 10.5 + i} for i, c in enumerate(COUNTRIES)]
    stack = [{"cat": c, "series": s, "v": 10 + i} for c in COUNTRIES[:5] for i, s in enumerate(("Small", "Large"))]
    pts = [{"cat": c, "v": i, "v2": i * 2} for i, c in enumerate(COUNTRIES[:6])]
    ranks = [{"cat": c, "t": t, "v": (i + j) % 4 + 1} for i, c in enumerate(COUNTRIES[:4]) for j, t in enumerate(("2021", "2022", "2023"))]
    out = draw_probe(LOOK + f"""
const rows = {json.dumps(rows)}, stack = {json.dumps(stack)}, pts = {json.dumps(pts)}, ranks = {json.dumps(ranks)}, res = {{}};
const sizes = () => Object.fromEntries([...svg.querySelectorAll(".qv-plot text")].filter(t => t.firstChild && t.firstChild.nodeType === 3)
  .map(t => [t.firstChild.nodeValue, +t.getAttribute("font-size")]));
const left = () => +svg.querySelector(".qv-plot").getAttribute("transform").match(/translate\\(([\\d.]+)/)[1];
for (const [k, s] of [["hbar", {{kind: "bar", rows, orientation: "horizontal"}}], ["vbar", {{kind: "bar", rows: rows.slice(0, 4), orientation: "vertical"}}],
                      ["stacked", {{kind: "stacked_bar", rows: stack}}], ["heatmap", {{kind: "heatmap", rows: stack}}], ["dots", {{kind: "dot_range", rows: stack}}],
                      ["scatter", {{kind: "scatter", rows: pts}}], ["bump", {{kind: "bump", rows: ranks}}]]) {{
  draw({{...s, highlight: ["Spain", "Belgium"].filter(n => s.rows.some(r => r.cat === n)), dimSize: 11, valueLabels: "on"}});
  res[k] = {{sz: sizes(), used: svg.__qv.used.includes("dimSize"), outside: inside()}};
}}
draw({{kind: "bar", rows, orientation: "horizontal", highlight: ["Spain"]}}); const wide = left(); const plain = sizes();
draw({{kind: "bar", rows, orientation: "horizontal", highlight: ["Spain"], dimSize: "small"}}); res.small = {{sz: sizes(), plain, narrower: left() < wide}};
draw({{kind: "bar", rows, orientation: "horizontal", dimSize: "small"}}); res.none = {{used: svg.__qv.used.includes("dimSize"), sz: sizes()}};
draw({{kind: "stacked_bar", rows: stack, highlight: ["Large"], dimSize: 11}}); res.series = svg.__qv.used.includes("dimSize");
const turn = extra => {{ for (let w = 320; w <= 900; w += 4) {{ draw({{kind: "bar", rows: rows.slice(2, 7), highlight: ["Spain"], ...extra}}, w); if (svg.__qv.orient === "vertical") return w; }} return 0; }};
res.turn = [turn({{}}), turn({{dimSize: "small"}})];
return res;
""", tmp_path)
    for k in ("hbar", "vbar", "stacked", "heatmap", "dots", "scatter", "bump"):
        r = out[k]
        assert r["used"] and [t for t in r["outside"] if t not in ("2021", "2022", "2023")] == [], (k, r)
        assert r["sz"]["Belgium"] != 11 and r["sz"]["Netherlands"] == 11, (k, r["sz"])
    assert out["hbar"]["sz"]["EU27"] != 11
    small, plain = out["small"]["sz"], out["small"]["plain"]
    assert small["Germany"] == plain["Germany"] - 3 and small["Spain"] == plain["Spain"] and out["small"]["narrower"]
    assert out["none"]["used"] is False and out["none"]["sz"]["Germany"] == plain["Germany"]
    assert out["series"] is False
    plain_w, dim_w = out["turn"]
    assert 0 < dim_w < plain_w
