import re
from pathlib import Path

from tests.test_no_blending import STRESS, load, run

ROOT = Path(__file__).resolve().parents[1]
GAP = "MOCK_ai_use_gap_small_vs_large_firms.csv"
EU = "European Union - 27 countries (from 2020)"
EA = "Euro area – 20 countries (from 2023)"

BAR = """
state.recipe = withAutoControls(applyChange(fitsKind("bar", {filters: []}), {ops: [{op: "roles", cat: "GEO"}]}));
state.spec = buildSpec(state.recipe);
"""


def stress():
    return load("samples", STRESS)


def test_auto_top_n_fits_the_reported_rows():
    out = run(stress(), BAR + """
      const before = new Set(state.spec.rows.map(r => r.cat)).size;
      fitTop({fit: {n: before, cap: 17}});
      const s = buildSpec(state.recipe);
      ({before, top: state.recipe.top, cats: s.rows.map(r => r.cat), note: s.autoNote, orientation: s.orientation})
    """)
    assert out["before"] == 31
    assert out["top"] == {"n": 15, "other": False, "by": "latest", "column": "GEO", "auto": True}
    assert len(out["cats"]) == 17 and EU in out["cats"] and EA in out["cats"]
    assert "Other" not in out["cats"]
    assert re.search(r"Showing the top 15 of 29 (countries|items), to fit the screen\.", out["note"])
    assert "Totals are shown for reference and not counted." in out["note"]
    assert "Other" not in out["note"]
    assert out["orientation"] == "horizontal"


def test_auto_top_n_follows_the_screen_with_a_margin():
    out = run(stress(), BAR + """
      fitTop({fit: {n: 31, cap: 17}});
      const a = state.recipe.top.n;
      fitTop({fit: {n: 17, cap: 18}});
      const b = state.recipe.top.n;
      fitTop({fit: {n: 17, cap: 20}});
      const c = state.recipe.top.n;
      fitTop({fit: {n: 20, cap: 12}});
      const d = state.recipe.top.n;
      fitTop({fit: {n: 12, cap: 40}});
      ({a, b, c, d, gone: state.recipe.top})
    """)
    assert (out["a"], out["b"], out["c"], out["d"]) == (15, 15, 18, 10)
    assert out["gone"] is None


def test_user_top_n_wins_over_the_screen():
    out = run(stress(), BAR + """
      fitTop({fit: {n: 31, cap: 17}});
      state.recipe = applyChange(state.recipe, {ops: [{op: "top_n", n: 25}]});
      fitTop({fit: {n: 27, cap: 17}});
      const more = state.recipe.top;
      state.recipe = applyChange(state.recipe, {ops: [{op: "top_n", n: 0}]});
      fitTop({fit: {n: 31, cap: 17}});
      ({more, all: state.recipe.top, rows: buildSpec(state.recipe).rows.length, ai: recipeForAI(state.recipe).top})
    """)
    assert out["more"]["n"] == 25 and not out["more"].get("auto")
    assert out["all"] == {"n": 0}
    assert out["rows"] == 31
    assert out["ai"] is None


def test_auto_top_n_is_sent_to_the_model_as_a_screen_fit():
    out = run(stress(), BAR + """
      fitTop({fit: {n: 31, cap: 17}});
      recipeForAI(state.recipe).top
    """)
    assert out == {"n": 15, "other": False, "by": "latest", "column": "GEO", "fit": "screen"}


def test_dot_range_with_27_rows_is_cut_to_fit():
    out = run(load("samples", GAP), """
      state.recipe = withAutoControls(fitsKind("dot_range", {filters: []}));
      state.spec = buildSpec(state.recipe);
      const before = new Set(state.spec.rows.map(r => r.cat)).size;
      fitTop({fit: {n: before, cap: 14}});
      const s = buildSpec(state.recipe);
      ({before, n: state.recipe.top.n, cats: [...new Set(s.rows.map(r => r.cat))], note: s.autoNote})
    """)
    assert out["before"] == 28
    assert out["n"] == 13 and len(out["cats"]) == 14 and "EU27" in out["cats"]
    assert re.match(r"Showing the top 13 of 27 (countries|items), to fit the screen\.", out["note"])


def test_heatmap_rows_are_cut_and_kinds_without_rows_are_left_alone():
    out = run(stress(), """
      state.recipe = withAutoControls(applyChange(fitsKind("heatmap", {filters: []}), {ops: [{op: "roles", cat: "GEO", series: "Size classes in number of persons employed"}]}));
      state.spec = buildSpec(state.recipe);
      fitTop({fit: {n: 31, cap: 9}});
      const heat = state.recipe.top;
      state.recipe = withAutoControls(fitsKind("line", {filters: []}));
      state.spec = buildSpec(state.recipe);
      fitTop({fit: {n: 31, cap: 9}});
      ({heat, line: state.recipe.top || null})
    """)
    assert out["heat"]["n"] == 7 and out["heat"]["column"] == "GEO" and out["heat"]["auto"]
    assert out["line"] is None


def test_charts_never_scroll_inside_the_frame():
    src = (ROOT / "web" / "charts.js").read_text()
    assert "H * 0.8" not in src
    assert 'svg.style("height", !fitH ? null : Math.min(H, Math.max(FIT_MIN, fitH) + ctlH) + "px")' in src
    assert "function fitRows(C, n, fixed)" in src
    for kind in ("bar(C)", "stacked_bar(C)", "heatmap(C)", "dot_range(C)"):
        body = src[src.index("    " + kind + " {"):]
        body = body[:body.index("\n    },\n")]
        assert "fitRows(C," in body, kind
    css = (ROOT / "web" / "style.css").read_text()
    assert "scrollbar-gutter: stable" in css


def test_heatmap_cells_are_square():
    src = (ROOT / "web" / "charts.js").read_text()
    body = src[src.index("    heatmap(C) {"):]
    body = body[:body.index("\n    },\n")]
    assert "WIDE" not in body and "stepX" not in body
    assert "const gw = step * (cols.length + gapH), gh = step * (cats.length + gapH);" in body
    assert "d3.scaleBand(cols, [0, gw]).padding(gapH), y = d3.scaleBand(cats, [0, gh]).padding(gapH)" in body
    assert "bandLeftAxis(C, b.g, y, cats, lw, FS.tick, fl)" in body
