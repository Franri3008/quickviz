import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.viz_parse import parse_file

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def load(name, sheet=None):
    out = parse_file((SAMPLES / name).read_bytes(), name, sheet)
    names = [c["name"] for c in out["columns"]]
    rows = [{n: ("" if v is None else v) for n, v in zip(names, r)} for r in out["rows"]]
    return {**out, "rows": rows, "cols": out["columns"], "name": name}


def js(data, code, decide=None, names=None):
    setup = (f"state.data = {json.dumps(data)}; state.decide = {json.dumps(decide)}; state.names = {json.dumps(names)};\n"
             "globalThis.__countries = {};\n")
    r = subprocess.run(["node", str(ROOT / "tests" / "app_harness.js")], input=setup + code, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def jev(roles):
    return {"columns": {k: {"role": v, "confidence": 0.9} for k, v in roles.items()}}


ADOPTION = "MOCK_ai_adoption_eu_countries_2025.csv"
ADOPTION_JEV = jev({"country": "name", "iso3": "ignore", "country_group": "group",
                    "ai_use_pct_all_firms": "value", "ai_use_pct_large_firms": "value"})


def test_dot_range_two_number_columns():
    out = js(load(ADOPTION), """
      const r = fitsKind("dot_range", {filters: []});
      const s = buildSpec(r);
      ({roles: r.roles, items: new Set(s.rows.map(x => x.cat)).size, series: [...new Set(s.rows.map(x => x.series))], unit: s.unit})
    """, ADOPTION_JEV)
    assert out["roles"]["cat"] == "country"
    assert out["roles"]["wide"] == ["ai_use_pct_all_firms", "ai_use_pct_large_firms"]
    assert out["items"] == 27
    assert out["series"] == ["All firms", "Large firms"]
    assert out["unit"] == "%"


def test_dot_range_never_uses_a_group_with_more_than_two_values():
    out = js(load(ADOPTION), """
      const r = rolesFor("dot_range", {series: "country_group"});
      r.series
    """, ADOPTION_JEV)
    assert out == "(columns)"


def test_dot_range_series_with_two_values():
    out = js(load("MOCK_ai_use_gap_small_vs_large_firms.csv"), """
      const r = fitsKind("dot_range", {filters: []});
      const s = buildSpec(r);
      ({roles: r.roles, items: new Set(s.rows.map(x => x.cat)).size, series: new Set(s.rows.map(x => x.series)).size})
    """)
    assert out["roles"] == {"cat": "country", "series": "firm_size", "v": "ai_use_pct"}
    assert out["items"] == 28
    assert out["series"] == 2


def test_dot_range_not_offered_without_a_shape():
    assert js(load("MOCK_rd_spending_vs_ai_patents.csv"), 'fitsKind("dot_range", {filters: []})') is None
    assert js(load("MOCK_ai_patent_rank_countries_2015_2025.csv"), 'fitsKind("dot_range", {filters: []})') is None


def test_dot_range_time_series_needs_two_periods():
    data = load("MOCK_ai_vacancy_share_german_regions_wide.csv")
    assert js(data, 'fitsKind("dot_range", {filters: []})') is None
    out = js(data, """
      const r = fitsKind("dot_range", {roles: {series: "Year"}, filters: [{column: "Year", keep: ["2019", "2025"]}]});
      new Set(buildSpec(r).rows.map(x => x.cat)).size
    """)
    assert out == 16


def test_group_that_never_splits_an_item_is_not_a_series():
    out = js(load(ADOPTION), """
      const a = rolesFor("stacked_bar", {series: "country_group"});
      const b = rolesFor("heatmap", {});
      [a.series, b.series]
    """, ADOPTION_JEV)
    assert out == ["(columns)", "(columns)"]


def test_unrelated_numbers_are_not_stacked():
    data = load("MOCK_rd_spending_vs_ai_patents.csv")
    assert js(data, 'fitsKind("stacked_bar", {filters: []})') is None
    assert js(data, 'fitsKind("heatmap", {filters: []})') is None


def test_one_to_one_columns_make_no_flow():
    out = js(load("MOCK_energy_flows_two_sheets.xlsx", "Net balance"), 'fitsKind("sankey", {filters: []})')
    assert out is None


def test_undo_leaves_one_line():
    out = js(load(ADOPTION), """
      state.recipe = fitsKind("donut", {filters: []});
      localChange({set: {kind: "bar"}, autoTime: true}, "Switched to bar chart");
      undo();
      ({kind: state.recipe.kind, chat: state.chat.map(m => [m.role, m.text, !!m.undone])})
    """, ADOPTION_JEV)
    assert out["kind"] == "donut"
    assert out["chat"] == [["note", "Switched to bar chart", True]]


def test_blank_recipe_sends_no_old_title():
    out = js(load(ADOPTION), "recipeForAI(blankRecipe())", ADOPTION_JEV, {"title": "Old chart title", "columns": {}, "unit": "%"})
    assert out["kind"] is None
    assert out["title"] is None and out["yLabel"] is None and out["unit"] is None


AGG_DATA = {
    "name": "agg.csv", "aggregates": ["European Union - 27 countries (from 2020)", "Total"],
    "cols": [{"name": "geo", "type": "category", "distinct": 4}, {"name": "size", "type": "category", "distinct": 2},
             {"name": "Year", "type": "time", "distinct": 2}, {"name": "Value", "type": "number", "distinct": 8}],
    "rows": [{"geo": g, "size": s, "Year": y, "Value": v}
             for g, base in [("Belgium", 10), ("Spain", 20), ("European Union - 27 countries (from 2020)", 15), ("Total", 99)]
             for s in ["Small", "Large"] for y, v in [("2024", base), ("2025", base + 1)]],
}


def test_aggregates_never_summed_into_a_line():
    out = js(AGG_DATA, """
      const s = buildSpec({kind: "line", roles: {t: "Year", v: "Value"}, agg: "sum", filters: []});
      s.rows.map(r => [r.t, r.v])
    """)
    assert out == [["2024", 60], ["2025", 64]]


def test_aggregates_left_out_of_parts_but_kept_as_bars():
    out = js(AGG_DATA, """
      const tm = buildSpec({kind: "treemap", roles: {cat: "geo", v: "Value"}, agg: "sum", filters: [{column: "Year", keep: ["2024"]}]});
      const bar = buildSpec({kind: "bar", roles: {cat: "geo", v: "Value"}, agg: "sum", filters: [{column: "Year", keep: ["2024"]}]});
      const kept = buildSpec({kind: "treemap", roles: {cat: "geo", v: "Value"}, agg: "sum",
        filters: [{column: "geo", keep: ["Total", "Spain"]}, {column: "Year", keep: ["2024"]}]});
      ({tm: tm.rows.map(r => r.cat).sort(), bar: bar.rows.length, kept: kept.rows.map(r => r.cat).sort()})
    """)
    assert out["tm"] == ["Belgium", "Spain"]
    assert out["bar"] == 4
    assert out["kept"] == ["Spain", "Total"]


ENERGY = "MOCK_energy_imports_wide.xlsx"


def test_stacked_kinds_stack_number_columns_that_differ_in_size():
    out = js(load(ENERGY), """
      ["stacked_bar", "stacked_area"].map(k => { const r = fitsKind(k, {filters: []}); return r && r.roles.wide; })
    """)
    assert out == [["Gas", "Oil", "Coal", "Nuclear"]] * 2


def test_recipe_for_ai_says_which_way_the_bars_run():
    out = js(load(ENERGY), """
      const r = fitsKind("stacked_bar", {filters: []}), v = {...r, orientation: "vertical"};
      const bar = {...r, kind: "bar"};
      const a = recipeForAI(r).orientation, b = recipeForAI(v).orientation, c = recipeForAI(bar).orientation;
      state.recipe = bar; state.orient = "vertical";
      [a, b, c, recipeForAI(bar).orientation, recipeForAI({...r, kind: "line"}).orientation === undefined]
    """)
    assert out == ["horizontal", "vertical", "auto", "vertical", True]


def test_dot_range_still_needs_a_matching_pair():
    out = js(load(ENERGY), """
      fitsKind("dot_range", {filters: []})
    """)
    assert out is None


def test_editing_an_unsure_picture_value_updates_the_table():
    data = {"name": "chart.png", "n_rows": 2, "rows": [{"Label": "A", "Value": 10}, {"Label": "B", "Value": 20}],
            "cols": [{"name": "Label", "type": "category"}, {"name": "Value", "type": "number", "min": 10, "max": 20}],
            "reading": {"source": "picture", "summary": "Read from a chart picture, 2 values unsure, check them",
                        "picture": {"flagged": [{"row": 0, "column": "Value"}, {"row": 1, "column": "Value"}]}}}
    out = js(data, """
const input = {value: "12,5", classList: {add() {}, remove() {}}, closest: () => ({classList: {remove() {}}})};
editCell(0, "Value", input);
const bad = {value: "lots", classList: {add() { bad.marked = true; }, remove() {}}, closest: () => ({classList: {remove() {}}})};
editCell(1, "Value", bad);
({rows: state.data.rows, min: state.data.cols[1].min, flagged: state.data.reading.picture.flagged, summary: state.data.reading.summary,
  bad: bad.value, marked: !!bad.marked, n: readNumber("1,234")})
""")
    assert out["rows"] == [{"Label": "A", "Value": 12.5}, {"Label": "B", "Value": 20}] and out["min"] == 12.5
    assert out["flagged"] == [{"row": 1, "column": "Value"}]
    assert out["summary"] == "Read from a chart picture, 1 value unsure, check it"
    assert out["bad"] == 20 and out["marked"] and out["n"] == 1234


def test_picture_bar_direction_reaches_the_first_chart_and_font_styles_merge():
    data = {"name": "chart.png", "n_rows": 2, "rows": [{"Label": "A", "Value": 10}, {"Label": "B", "Value": 20}],
            "cols": [{"name": "Label", "type": "category", "distinct": 2, "values": ["A", "B"]}, {"name": "Value", "type": "number", "min": 10, "max": 20}],
            "orientation_hint": "horizontal", "reading": {"source": "picture", "summary": "x", "picture": {"flagged": []}}}
    out = js(data, """
globalThis.AbortController = class { constructor() { this.signal = {}; } abort() {} };
(async () => {
  await autoChart();
  const first = {kind: state.recipe.kind, orientation: state.recipe.orientation};
  state.auto = null; state.data = {...state.data, orientation_hint: null};
  await autoChart();
  const r = state.recipe, set = fs => ({set: {fontStyle: fs}});
  return {first, plain: r.orientation ?? null,
    spec: buildSpec(applyChange(r, set({source: "italic", title: "bold italic"}))).fontStyle,
    part: applyChange(applyChange(r, set({source: "italic", title: "normal"})), set({title: null})).fontStyle,
    all: applyChange(applyChange(r, set({source: "italic"})), set(null)).fontStyle ?? null,
    sent: recipeForAI(applyChange(r, set({note: "bold"}))).layout,
    dim: buildSpec(applyChange(r, {set: {dimSize: 11}})).dimSize,
    dimSent: recipeForAI(applyChange(r, {set: {dimSize: "small"}})).layout,
    dimOff: buildSpec(applyChange(applyChange(r, {set: {dimSize: 11}}), {set: {dimSize: null}})).dimSize ?? null};
})()
""")
    assert out["first"] == {"kind": "bar", "orientation": "horizontal"} and out["plain"] is None
    assert out["spec"] == {"source": "italic", "title": "bold italic"}
    assert out["part"] == {"source": "italic"} and out["all"] is None
    assert out["sent"] == {"fontStyle": {"note": "bold"}}
    assert out["dim"] == 11 and out["dimSent"] == {"dimSize": "small"} and out["dimOff"] is None
