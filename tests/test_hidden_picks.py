from pathlib import Path

from tests.test_no_blending import STRESS, load, run

ROOT = Path(__file__).resolve().parents[1]
SIZE = "Size classes in number of persons employed"
EU = "European Union - 27 countries (from 2020)"


def stress():
    return load("samples", STRESS)


def test_one_area_out_of_many_is_said_by_the_chart():
    out = run(stress(), f"""
      const geo = new Set(valuesOf(state.data.rows, "GEO"));
      QV.countryId = n => (geo.has(n) ? "X" : null);
      const r = withAutoControls(fitsKind("heatmap", {{filters: [], roles: {{cat: "Year", series: "{SIZE}", v: "Value"}}}}));
      ({{line: hiddenPicks(r), controls: (r.controls || []).map(c => c.column), ai: recipeForAI(r).what_is_shown, note: buildSpec(r).note}})
    """)
    assert "GEO" not in out["controls"]
    assert out["line"] == f"Showing {EU}. 32 areas in the file."
    assert EU in out["ai"]
    assert out["note"] == ""


def test_no_line_when_a_dropdown_shows_the_pick():
    out = run(stress(), """
      const r = withAutoControls(fitsKind("bar", {filters: []}));
      ({line: hiddenPicks(r), controls: (r.controls || []).map(c => c.column)})
    """)
    assert SIZE in out["controls"] and out["line"] == ""


def test_no_line_when_every_area_is_drawn():
    out = run(stress(), """
      const r = withAutoControls(fitsKind("heatmap", {filters: []}));
      ({line: hiddenPicks(r), roles: r.roles})
    """)
    assert out["roles"]["cat"] == "GEO" and out["line"] == ""


def test_line_sits_by_the_chart_and_not_in_the_export():
    html = (ROOT / "web" / "index.html").read_text()
    head, frame = html.index('class="stage-head"'), html.index('id="frame"')
    assert head < html.index('id="shown-line"') < frame
    assert "hiddenPicks" not in (ROOT / "web" / "charts.js").read_text()
