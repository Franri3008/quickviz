import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.viz_chat import COLORS, SYSTEM, ChangeError, validate_change

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
CHARTS = (WEB / "charts.js").read_text()
THEME = (WEB / "ceps-theme.js").read_text()
COLUMNS = [{"name": "country", "type": "text", "values": ["Belgium", "Germany", "Spain"]}, {"name": "v", "type": "number", "min": 1, "max": 9}]


def test_theme_palette_puts_the_yellow_fifth():
    assert 'yellow: "#f2c64b"' in THEME
    assert 'cat: [green, navy, red, grey, "#f2c64b", "#56998c", "#4a5f80", "#d0687f", "#a3a3a1", "#8fc0b6"]' in THEME


def test_charts_palette_follows_the_theme():
    assert "CAT = T.cat.slice();" in CHARTS


def test_old_yellow_is_gone_everywhere():
    for p in [*WEB.glob("*.js"), *(ROOT / "app").glob("*.py"), ROOT / "SPEC.md", ROOT / "README.md"]:
        assert "f3c74d" not in p.read_text().lower(), p
    assert COLORS["yellow"] == "#f2c64b"


@pytest.mark.parametrize("given,kept", [
    ("navy", "navy"), ("Light Grey", "light grey"), (" yellow ", "yellow"),
    ("#ff8800", "#ff8800"), ("#FF8800", "#ff8800"), ("#f80", "#ff8800"), (" #0C2443 ", "#0c2443"),
])
def test_chat_takes_named_and_hex_colours(given, kept):
    ch = validate_change({"reply": "ok", "set": {"colors": {"belgium": given}}}, COLUMNS, ["Belgium"])
    assert ch["set"]["colors"] == {"Belgium": kept}


@pytest.mark.parametrize("bad", [
    "orange", "#ff88", "#ff88000", "#gg8800", "ff8800", "rgb(255,136,0)", "red; background: url(x)",
    "#ff8800;fill:url(javascript:alert(1))", "url(#x)", "constructor", "", 12, None,
])
def test_chat_refuses_what_is_not_a_colour(bad):
    with pytest.raises(ChangeError):
        validate_change({"reply": "ok", "set": {"colors": {"Belgium": bad}}}, COLUMNS, ["Belgium"])


def test_prompt_allows_any_hex():
    line = next(x for x in SYSTEM.split("\n") if x.startswith("colors:"))
    assert "#ff8800" in line and "hex" in line and "come only from" not in line


def test_renderer_reads_item_colours_through_paint():
    assert not re.search(r"NAMED\[(o|spec|C\.spec|over|Object)", CHARTS)
    assert "paint(over[S[0]])" in CHARTS and "if (paint(o)) { map.set(n, paint(o)); return; }" in CHARTS


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_paint_and_text_on_coloured_fills():
    src = CHARTS[CHARTS.index("function hexLum("):CHARTS.index("  const textOn")]
    assert "const paint = " in src
    code = f"""
const NAMED = {{"navy": "#0c2443", "yellow": "#f2c64b"}};
const d3 = {{color: c => ({{formatHex: () => c}})}};
const T = {{ink: "#1a1a1a"}}, WHITE = "#ffffff";
{src}
const textOn = fill => (hexLum(fill) > 0.32 ? T.ink : WHITE);
console.log(JSON.stringify([paint("navy"), paint("NAVY"), paint("#FF8800"), paint("#f80"), paint("orange"), paint("constructor"),
  paint("#ff8800;fill:red"), paint(undefined), textOn("#f2c64b"), textOn("#ff8800"), textOn("#0c2443")]));
"""
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["#0c2443", "#0c2443", "#ff8800", "#f80", None, None, None, None, "#1a1a1a", "#1a1a1a", "#ffffff"]


def test_help_dialog_title_and_no_extra_lines():
    html = (WEB / "index.html").read_text()
    assert '<h2 id="help-title">Available Chart Types</h2>' in html
    assert "Charts you can make" not in html and "help-foot" not in html and "You can ask for any of these" not in html
    js = (WEB / "help.js").read_text()
    assert "needs" not in js.lower() and js.count("name:") == 13


def test_help_list_is_two_columns_on_wide_screens():
    css = (WEB / "style.css").read_text()
    assert ".help-dialog { width: min(900px, calc(100vw - 24px));" in css
    assert re.search(r"@media \(min-width: 700px\) \{\s*\.help-list \{ display: grid; grid-template-columns: 1fr 1fr;", css)
    assert "help-needs" not in css and "help-foot" not in css


@pytest.mark.parametrize("given,kept", [
    ("blue", "#2756d3"), ("Red", "#e53229"), ("amber", "#f59e0b"), ("emerald", "#10b981"), ("violet", "#8b5cf6"),
    ("cyan", "#06b6d4"), ("orange", "#f97316"), ("#FF8800", "#ff8800"), ("#f80", "#ff8800"),
])
def test_aiw_chat_takes_its_own_names_and_hex(given, kept):
    ch = validate_change({"reply": "ok", "set": {"colors": {"Belgium": given}}}, COLUMNS, ["Belgium"], style="aiw")
    assert ch["set"]["colors"] == {"Belgium": kept}


def test_colour_errors_name_the_chosen_style():
    with pytest.raises(ChangeError) as e:
        validate_change({"reply": "ok", "set": {"colors": {"Belgium": "navy"}}}, COLUMNS, ["Belgium"], style="aiw")
    assert "AI World colour" in str(e.value) and "CEPS" not in str(e.value)
    with pytest.raises(ChangeError) as e:
        validate_change({"reply": "ok", "set": {"colors": {"Belgium": "amber"}}}, COLUMNS, ["Belgium"])
    assert "CEPS colour" in str(e.value)


def test_aiw_prompt_names_its_colours_and_the_logo():
    from app.viz_chat import system_prompt

    aiw = system_prompt("aiw")
    line = next(x for x in aiw.split("\n") if x.startswith("colors:"))
    assert "blue, red, amber, emerald, violet, cyan, orange" in line and "CEPS" not in line
    assert "CEPS colours" not in aiw and '"top-left"' in aiw
    assert "ink #0f172a" in aiw and "grey #4b5563" in aiw and "#1a1a1a" not in aiw and "#6b6b69" not in aiw and "@@" not in aiw
    theme = (WEB / "aiw-theme.js").read_text()
    assert all(hexcode in theme for hexcode in ("#0f172a", "#4b5563", "#2756d3"))
    assert "CEPS charts have no logo" in SYSTEM


@pytest.mark.parametrize("asked,now,want", [
    ({"show": False}, None, {"show": False, "pos": "bottom-right"}),
    ({"show": True}, {"show": False, "pos": "top-left"}, {"show": True, "pos": "top-left"}),
    ({"pos": "top-left"}, {"show": False, "pos": "bottom-right"}, {"show": True, "pos": "top-left"}),
    ("top right", None, {"show": True, "pos": "top-right"}),
    (False, None, {"show": False, "pos": "bottom-right"}),
    ("off", None, {"show": False, "pos": "bottom-right"}),
])
def test_aiw_logo_can_be_removed_restored_and_moved(asked, now, want):
    ch = validate_change({"reply": "ok", "set": {"logo": asked}}, COLUMNS, ["Belgium"], kind="bar", caps=True, style="aiw", logo=now)
    assert ch["set"]["logo"] == want


def test_aiw_logo_refuses_a_made_up_corner():
    with pytest.raises(ChangeError):
        validate_change({"reply": "ok", "set": {"logo": {"pos": "middle"}}}, COLUMNS, ["Belgium"], style="aiw")


def test_ceps_logo_change_is_dropped_with_a_plain_answer():
    ch = validate_change({"reply": "Moved the logo.", "set": {"logo": {"pos": "top-left"}}}, COLUMNS, ["Belgium"], kind="bar", caps=True)
    assert ch["set"] == {} and ch["reply"] == "CEPS charts have no logo, so nothing changed."
    ch = validate_change({"reply": "Title changed.", "set": {"title": "X", "logo": {"show": False}}}, COLUMNS, ["Belgium"], kind="bar", caps=True)
    assert ch["set"] == {"title": "X"} and ch["reply"] == "Title changed. CEPS charts have no logo, so nothing changed."


def test_page_has_one_style_and_no_style_menu():
    html = (WEB / "index.html").read_text()
    assert "in CEPS house style" not in (ROOT / "README.md").read_text().split("\n")[2]
    assert 'id="style-pick"' not in html and 'id="style-row"' not in html
    assert '<body class="view-1" data-style="franri">' in html


def test_step_bar_sides_are_centred_and_wrap_when_narrow():
    html = (WEB / "index.html").read_text()
    css = (WEB / "style.css").read_text()
    bar = html[html.index('<div class="stepbar">'):html.index('<div class="notice">')]
    assert bar.index('id="stepper"') < bar.index('id="restart"')
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in css
    side = [line for line in css.splitlines() if line.startswith(".restart-wrap {")]
    assert len(side) == 1 and "justify-self: center" in side[0]
    narrow = css[css.index("@media (max-width: 740px)"):]
    narrow = narrow[:narrow.index("\n}\n")]
    assert "flex-wrap: wrap" in narrow and "order: -1" in narrow and "flex: 0 0 100%" in narrow


def _fn(name):
    body = CHARTS[CHARTS.index(f"  function {name}("):]
    return body[:body.index("\n  }\n")]


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_aiw_treemap_tiles_follow_d3plus_labels():
    code = f"""
global.window = {{}};
{THEME}
{(WEB / "aiw-theme.js").read_text()}
const t = window.QV_THEMES;
console.log(JSON.stringify([t.aiw.tile, t.ceps.tile]));
"""
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [{"font": 'Roboto, "Helvetica Neue", HelveticaNeue, Helvetica, Arial, sans-serif', "ink": "#f7f7f7",
                                     "dark": "#555555", "yiq": 128, "min": 8, "max": 40, "pad": 5}, None]
    tm = CHARTS[CHARTS.index("    treemap(C) {"):]
    tm = tm[:tm.index("\n    },\n")]
    assert "palette(C, leafNames, T.tile ? {rest: RULE, single: T.primary} : {rest: RULE})" in tm
    assert "d3.treemap().size([b.iw, b.ih]).paddingInner(2)" in tm and ".padding(o)" in tm and "const o = T.tile ? 2 : 0;" in tm
    assert "if (T.tile) n.each(" in tm
    body = _fn("tileLabel")
    assert "yiq >= t.yiq ? t.dark : t.ink" in body and 'call(face, "valueLabels")' in body and "700" not in body
    assert "Math.min(t.max, (h - 2 * P) * 0.5)" in body and "if (sh < t.min) sh = 0;" in body
    assert 'attr("text-anchor", mid ? "middle" : "start")' in body and '"\\n" + fmtShort(e.value, spec.unit)' in body
    fit = _fn("tileFit")
    assert "1.165 + iw / ih * 0.1" in fit and "Math.floor(ih * 0.8)" in fit and '+ "..."' in fit


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_aiw_treemap_share_reads_like_d3plus():
    code = f"""
global.window = {{}};
{(WEB / "vendor" / "d3.min.js").read_text()}
const d3 = typeof exports.format === "function" ? exports : window.d3;
{_fn("tileShare")}
  }}
console.log(JSON.stringify([11.4285, 4.2301, 2.3, 1, 0.5912, 0, 100, 12.0].map(tileShare)));
"""
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["11.4%", "4.23%", "2.3%", "1%", "0.59%", "0%", "100%", "12%"]


def test_controls_sit_in_one_centred_row_above_the_source():
    build = _fn("buildControls")
    assert "c.position" not in build and 'row.className = "qv-ctl"' in build
    assert "justify-content:center" in CHARTS[CHARTS.index("const ctlCss"):CHARTS.index("const PLAY =")]
    assert "h += C.ctlH || 0;" in _fn("footH")
    foot = _fn("drawFoot")
    assert foot.index("noteLines(C)") < foot.index("C.ctlY = y;") < foot.index("spec.source")
    assert "render(s2, st.spec, {width: w, still: true, noResize: true, noControls: true});" in CHARTS
    assert "translate(${b.offsetLeft}px,${b.offsetTop}px)" in _fn("pill")


def test_aiw_logo_is_fifteen_percent_bigger():
    assert "Math.max(20.7, Math.min(29.9, W * 0.0368))" in _fn("logoBox")
    assert "Math.max(C.spec.source ? 24 : 0, C.logo && !C.logo.top ? C.logo.h + 8 : 0)" in CHARTS


def test_two_way_control_is_the_button_group_in_both_styles():
    aiw = (WEB / "aiw-theme.js").read_text()
    assert 'twoWay: "buttons"' in aiw and 'twoWay: "buttons"' in THEME
    body = _fn("controlEl")
    assert 'const seg2 = c.type === "switch" && T.ctl.twoWay === "buttons";' in body
    assert '"qv-c qv-" + (seg2 ? "select" : c.type)' in body
    assert 'if (c.type === "switch" && !seg2)' in body and 'if (c.style === "buttons" || seg2)' in body
    assert "st.boxStyle !== T.name" in CHARTS and "st.boxStyle = T.name;" in _fn("buildControls")


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_flags_show_when_most_names_are_countries():
    eu = CHARTS[CHARTS.index("const EU_RE"):CHARTS.index("function hexLum(")]
    geo = CHARTS[CHARTS.index("const GEO_ALIAS"):CHARTS.index("  const INLINE")]
    flags = json.loads((WEB / "flags" / "flags.json").read_text())
    code = f"""
const window = {{QV_FLAGS: {json.dumps({k: flags[k] for k in ("056", "276", "250", "380", "724", "528", "616", "752", "392", "eu")})}}};
const OTHER = "Other";
{eu}
function countryShareOf(names) {{ return names.length ? names.filter(n => countryId(n) || isEU(n)).length / names.length : 0; }}
{geo}
const read = [];
const C = mode => ({{spec: new Proxy({{flags: mode}}, {{get(t, k) {{ read.push(k); return t[k]; }}}})}});
const eight = ["Belgium", "Germany", "France", "Italy", "Spain", "Netherlands", "Poland", "Sweden"];
const out = [flagsOn(C(), [...eight, "EU27", "Candidate countries"]), flagsOn(C(), ["Belgium", "Japan", "EU27", "Small", "Large", "Medium"]),
  flagsOn(C("on"), ["Belgium", "Small", "Large", "Medium"]), flagsOn(C("off"), eight), flagsOn(C(), [...eight, "Other"])];
read.length = 0;
out.push(flagsOn(C("on"), ["Small", "Large"]), read.length);
out.push(flagKey("Belgium"), flagKey("EU27"), flagKey("euro area"), flagKey("Candidate countries"), flagKey("Austria"), flagBox(16));
out.push(flagKeys({{flags: "off", rows: [{{cat: "Belgium", series: "Japan"}}], variants: {{"0": {{rows: [{{cat: "Spain"}}]}}}}}}));
console.log(JSON.stringify(out));
"""
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [True, False, True, False, True, False, 0, "056", "eu", "eu", None, None, {"h": 12, "w": 16, "gap": 6},
                                    ["056", "392", "724"]]


def test_flags_sit_where_the_brief_says():
    for kind in ("bar", "stacked_bar", "heatmap", "bump", "dot_range", "line", "stacked_area", "scatter"):
        body = CHARTS[CHARTS.index(f"    {kind}(C) {{"):]
        body = body[:body.index("\n    },\n")]
        assert "flagsOn(C, " in body, kind
    for kind in ("map", "treemap", "donut", "sankey", "histogram"):
        body = CHARTS[CHARTS.index(f"    {kind}(C) {{"):]
        body = body[:body.index("\n    },\n")]
        assert "flagsOn(" not in body and "legFlags" not in body, kind
    assert "const flag = C.legFlags ? flagKey(it.name) : null;" in _fn("legend")
    assert "if (LMAX) cutLabels(C);\n    placeFlags(C);" in _fn("finish")
    assert 'el.closest("defs")' in CHARTS and '.attr("stroke", RULE)' in _fn("flagSym")
    assert 'el.classList.contains("qv-flag")' in _fn("outline")


def test_page_and_chat_pick_the_franri_theme():
    html = (WEB / "index.html").read_text()
    assert 'src="franri-theme.js' in html and "aiw-theme.js" not in html and 'href="fonts/carlito.css' in html
    assert html.index("charts.js?") < html.index("charts-mock.js?") < html.index("app.js?")
    assert '--font: Carlito, Calibri, "Segoe UI", sans-serif;' in (WEB / "style.css").read_text()
    from app import viz
    from app.viz_chat import FRANRI_COLORS, system_prompt
    assert viz.STYLE == "franri"
    theme = (WEB / "franri-theme.js").read_text()
    assert 'heat: ["#ffffff", "#5fa3bd", "#0d3f63"]' in theme and 'const ash = "#7a766f"' in theme and "grey: ash," in theme
    ch = validate_change({"reply": "ok", "set": {"colors": {"Belgium": "petrol"}}}, COLUMNS, ["Belgium"], style="franri")
    assert ch["set"]["colors"] == {"Belgium": FRANRI_COLORS["petrol"]} == {"Belgium": "#13759a"}
    prompt = system_prompt("franri")
    assert "QuickViz colours: ink #1c1917" in prompt and "Carlito" in prompt and "@@" not in prompt and "AI World" not in prompt
    ch = validate_change({"reply": "Moved it.", "set": {"logo": {"pos": "top-left"}}}, COLUMNS, ["Belgium"], kind="bar", caps=True, style="franri")
    assert ch["set"] == {} and ch["reply"] == "These charts have no logo, so nothing changed."


def test_page_accent_is_franri_petrol():
    css = (WEB / "style.css").read_text()
    root, dark = css.split(':root[data-theme="dark"]', 1)
    assert "--accent: #13759a;" in root and "--accent: #13759a;" in dark
    assert "--link: #13759a;" in root and "--focus: 2px solid #13759a;" in root
    for green in ("#207164", "#2a7d6f", "#6cc2b0", "#134a41"):
        assert green not in css, green
    html = (WEB / "index.html").read_text()
    assert "Never upload sensitive data" in html and "Never type sensitive data" not in html
