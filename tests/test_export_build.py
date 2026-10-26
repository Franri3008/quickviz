import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = WEB / "export"
MANIFEST = json.loads((OUT / "manifest.json").read_text())
CHARTS = (WEB / "charts.js").read_text()
STALE = "is out of date. Run .venv/bin/python scripts/build_export.py and commit web/export/"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _export_fn() -> str:
    start = CHARTS.index("async function exportHTML(")
    return CHARTS[start:CHARTS.index("window.QV = ", start)]


def _node_fn(name: str) -> str:
    start = CHARTS.index(f"function {name}(")
    return CHARTS[start:CHARTS.index("\n  }\n", start) + 4]


@pytest.mark.parametrize("out", sorted(MANIFEST))
def test_minified_copy_matches_its_source(out):
    m = MANIFEST[out]
    assert (OUT / out).exists(), f"web/export/{out} is missing. Run .venv/bin/python scripts/build_export.py"
    assert _sha(WEB / m["source"]) == m["source_sha256"], f"web/{m['source']} changed, so web/export/{out} {STALE}"
    assert _sha(OUT / out) == m["sha256"], f"web/export/{out} was edited by hand or {STALE}"


def test_every_inlined_file_is_built():
    assert set(MANIFEST) == {"charts.min.js", "ceps-theme.min.js", "aiw-theme.min.js", "franri-theme.min.js", "d3.min.js", "d3-sankey.min.js",
                             "topojson-client.min.js", "countries-50m.min.json"}


@pytest.mark.parametrize("out", [o for o in sorted(MANIFEST) if o.endswith(".js")])
def test_minified_js_has_no_comments_but_the_licence_line(out):
    text = (OUT / out).read_text()
    assert "/*" not in text
    lines = text.split("\n")
    assert not any(line.lstrip().startswith("//") for line in lines[1:])
    if lines[0].startswith("//"):
        assert out in ("d3.min.js", "d3-sankey.min.js", "topojson-client.min.js") and "Copyright" in lines[0]


def test_minified_charts_is_smaller():
    assert (OUT / "charts.min.js").stat().st_size < (WEB / "charts.js").stat().st_size * 0.8


def test_export_inlines_the_minified_copies():
    fn = _export_fn()
    for name in ("export/d3.min.js", "export/d3-sankey.min.js", "export/ceps-theme.min.js", "export/aiw-theme.min.js", "export/franri-theme.min.js",
                 "export/charts.min.js", "export/topojson-client.min.js", "export/countries-50m.min.json"):
        assert name in fn
    assert "vendor/" not in fn and '"charts.js"' not in fn and '"ceps-theme.js"' not in fn and '"aiw-theme.js"' not in fn and '"franri-theme.js"' not in fn


def test_export_page_template_has_no_comments():
    fn = _export_fn()
    page = fn[fn.index("return `<!doctype html>"):]
    assert "<!--" not in page and "/*" not in page
    assert not re.search(r"(?m)^\s*//", page)


def test_world_map_is_smaller_and_keeps_every_country():
    full = json.loads((WEB / "vendor" / "countries-50m.json").read_text())
    small = json.loads((OUT / "countries-50m.min.json").read_text())
    assert list(small["objects"]) == ["countries"]
    ids = lambda t: sorted(str(g.get("id")) for g in t["objects"]["countries"]["geometries"])
    assert ids(small) == ids(full)
    assert len(small["arcs"]) == len(full["arcs"])
    assert all(len(a) >= 2 for a in small["arcs"])
    assert (OUT / "countries-50m.min.json").stat().st_size < (WEB / "vendor" / "countries-50m.json").stat().st_size * 0.75


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_export_keeps_only_the_font_faces_the_text_needs():
    css = (WEB / "fonts" / "carlito.css").read_text()
    code = _node_fn("fontsFor") + f"""
const css = {json.dumps(css)};
const n = t => (fontsFor(css, t).match(/@font-face/g) || []).length;
console.log(JSON.stringify([n("Belgium 24.7% EU27 – …"), n("Česko"), n("Łódź"), fontsFor(css, "a").includes("\\n")]));
"""
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [2, 4, 4, False]


def test_png_is_four_times_and_fits_the_canvas_limits():
    assert "async function pngFromMarkup(m, filename, scale = 4)" in CHARTS
    assert "async function exportPNG(svgEl, filename, scale = 4)" in CHARTS
    body = _node_fn("pngFromMarkup")
    assert "CANVAS_SIDE / Math.max(W, Hh)" in body and "Math.sqrt(CANVAS_AREA / (W * Hh))" in body
    assert "const CANVAS_SIDE = 16384;" in CHARTS and "const CANVAS_AREA = 16777216;" in CHARTS
    assert 760 * 4 * 900 * 4 <= 16777216


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_both_themes_have_the_same_keys_and_the_same_sizes():
    code = f"""
global.window = {{}};
{(WEB / "ceps-theme.js").read_text()}
{(WEB / "aiw-theme.js").read_text()}
const t = window.QV_THEMES, k = o => Object.keys(o).sort().join();
console.log(JSON.stringify([k(t.ceps) === k(t.aiw), k(t.ceps.ctl) === k(t.aiw.ctl), window.CEPS === t.ceps,
  JSON.stringify(t.ceps.fs) === JSON.stringify(t.aiw.fs), t.ceps.webFont, t.aiw.webFont, t.aiw.font.includes("Carlito")]));
"""
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [True, True, True, True, True, False, False]


def test_charts_has_no_colour_or_font_of_its_own():
    body = CHARTS.replace("/^(#fff(fff)?|white)$/i", "")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", body)
    assert "Carlito" not in body


def test_aiw_logo_in_the_theme_matches_the_svg_file():
    svg = (WEB / "aiw-logo.svg").read_text()
    theme = (WEB / "aiw-theme.js").read_text()
    paths = re.findall(r'<path[^>]*\sd="([^"]+)"', svg)
    assert len(paths) == 8 and all(f'd: "{d}"' in theme for d in paths)


def test_aiw_export_has_no_web_font():
    fn = _export_fn()
    assert "th.webFont ? embeddedFonts()" in fn and 'th.webFont ? "QV.ready.then(fit);" : "fit();"' in fn


def test_flags_cover_every_country_and_the_eu():
    flags = json.loads((WEB / "flags" / "flags.json").read_text())
    alias = json.loads(re.search(r"const GEO_ALIAS = (\{.*?\});\n", CHARTS).group(1))
    assert set(flags) == set(alias) | {"eu", "_notice"}
    assert "MIT" in flags["_notice"] and "lipis/flag-icons" in flags["_notice"]
    assert "MIT License" in (WEB / "flags" / "LICENSE").read_text()
    assert (WEB / "flags" / "flags.json").stat().st_size < 1700 * 1024
    for key, body in flags.items():
        if key == "_notice":
            continue
        assert re.match(r'<g fill="#[0-9a-fA-F]+" stroke="none"', body), key
        assert not re.search(r"<script|<style|<image|<foreignObject|\son\w+=|https?:|xlink", body), key
        ids = set(re.findall(r'\sid="([^"]+)"', body))
        assert all(i.startswith(f"qvf{key}-") for i in ids), key
        refs = set(re.findall(r'url\(#([^)]+)\)', body)) | set(re.findall(r'href="#([^"]+)"', body))
        assert refs <= ids, key


def test_export_inlines_only_the_flags_drawn():
    fn = _export_fn()
    assert "ex.flagsUsed" in fn and "qv.flagsUsed" in fn and "flagKeys(spec)" in fn
    assert "window.QV_FLAGS = ${JSON.stringify(Object.fromEntries([[\"_notice\"" in fn
    assert "flags/flags.json" not in fn
    host = (WEB / "frame-host.js").read_text()
    runtime = (WEB / "frame-runtime.js").read_text()
    assert 'text("flags/flags.json")' in host and "postMessage(withFlags(msg)" in host and "postMessage(withFlags(x)" in host
    assert "QV.flagKeys(m.spec)" in host and "flagsUsed" in host
    assert "Object.assign(window.QV_FLAGS, m.flags)" in runtime and "flagsUsed: st.flagsUsed" in runtime
    assert "flagData: await chart.flags()" in (WEB / "app.js").read_text()


def test_synced_renderer_matches_its_manifest():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from sync_renderer import MANIFEST, check, listed

    assert MANIFEST.exists()
    files = json.loads(MANIFEST.read_text())["files"]
    assert {"charts.js", "franri-theme.js", "aiw-theme.js", "capabilities.json", "vendor/d3.min.js", "flags/flags.json", "geo/regions/index.json"} <= set(files)
    assert check() == []
    assert set(listed(WEB)) == set(files)
