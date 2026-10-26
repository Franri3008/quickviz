import json
import re
import subprocess
from pathlib import Path

import pytest

from app.viz_chat import SYSTEM, ChangeError, validate_change
from tests.test_no_blending import CHECK, STRESS, load, run

ROOT = Path(__file__).resolve().parents[1]
SIZE = "Size classes in number of persons employed"
EU = "European Union - 27 countries (from 2020)"
EA = "Euro area – 20 countries (from 2023)"
VC = "MOCK_ai_venture_capital_by_technology_semicolon.csv"
VAC = "MOCK_ai_vacancy_share_german_regions_wide.csv"
COLUMNS = [
    {"name": "country", "type": "category", "distinct": 3, "values": ["Spain", "EU27_2020", "Belgium"]},
    {"name": "year", "type": "time", "distinct": 4, "values": ["2021", "2022", "2023", "2024"]},
    {"name": "rate", "type": "number", "distinct": 12, "min": 1.0, "max": 40.0},
]


def stress():
    return load("samples", STRESS)


def test_totals_never_take_a_slot():
    out = run(stress(), """
      const base = fitsKind("bar", {filters: []});
      const all = buildSpec(base).rows;
      const s = buildSpec(applyChange(base, {ops: [{op: "top_n", n: 20}]}));
      const plain = all.filter(x => !isAggregate(x.cat)).sort((a, b) => b.v - a.v);
      ({cats: s.rows.map(x => x.cat), want: plain.slice(0, 20).map(x => x.cat), aggs: s.rows.filter(x => isAggregate(x.cat)).map(x => [x.cat, x.v]),
        allAggs: all.filter(x => isAggregate(x.cat)).map(x => [x.cat, x.v]), note: s.autoNote, nPlain: plain.length})
    """)
    real = [c for c in out["cats"] if c not in (EU, EA)]
    assert len(real) == 20 and set(real) == set(out["want"])
    assert sorted(out["aggs"]) == sorted(out["allAggs"]) and len(out["aggs"]) == 2
    assert out["nPlain"] == 29
    assert out["note"].startswith("Showing: 10 persons employed or more, 2025. Top 20 of 29 ")
    assert "by 2025 value." in out["note"] and "Totals are shown for reference and not counted." in out["note"]


def test_renamed_total_still_does_not_count():
    out = run(stress(), f"""
      const base = fitsKind("bar", {{filters: []}});
      const s = buildSpec(applyChange(base, {{ops: [{{op: "rename", column: "GEO", map: {{"{EU}": "EU average"}}}}, {{op: "top_n", n: 3}}]}}));
      s.rows.map(x => x.cat)
    """)
    assert "EU average" in out and len(out) == 5


def test_rate_data_gets_no_other():
    out = run(stress(), """
      const base = fitsKind("bar", {filters: []});
      const r = applyChange(base, {ops: [{op: "top_n", n: 10, other: true}]});
      const s = buildSpec(r);
      ({rate: isRate(r), cats: s.rows.map(x => x.cat), note: s.autoNote, ai: recipeForAI(r).values_are})
    """)
    assert out["rate"] is True
    assert "Other" not in out["cats"] and len(out["cats"]) == 12
    assert "Other is left out, because these values are rates" in out["note"]
    assert out["ai"] == "rates"


def test_amounts_sum_the_rest_as_other():
    out = run(load("samples", VC), """
      const base = fitsKind("bar", {filters: []});
      const all = buildSpec(base).rows.slice().sort((a, b) => b.v - a.v);
      const r = applyChange(base, {ops: [{op: "top_n", n: 3, other: true}]});
      const s = buildSpec(r);
      ({rate: isRate(r), rows: s.rows.map(x => [x.cat, x.v]), want: all.slice(3).reduce((a, x) => a + x.v, 0), top: all.slice(0, 3).map(x => x.cat), note: s.autoNote})
    """)
    assert out["rate"] is False
    got = dict(out["rows"])
    assert list(got)[:3] == out["top"] and abs(got["Other"] - out["want"]) < 1e-9
    assert "The other 3 are added up as Other." in out["note"] and "by 2025-Q4 value" in out["note"]


def test_line_ranks_by_latest_mean_or_period():
    out = run(load("samples", VAC), """
      const base = fitsKind("line", {filters: []});
      const rows = buildSpec(base).rows;
      const ser = [...new Set(rows.map(x => x.series))];
      const at = (s, t) => rows.find(x => x.series === s && x.t === t)?.v ?? -Infinity;
      const mean = s => d3.mean(rows.filter(x => x.series === s), x => x.v);
      const sum = s => d3.sum(rows.filter(x => x.series === s), x => Math.abs(x.v));
      const top = f => ser.slice().sort((a, b) => f(b) - f(a)).slice(0, 5).sort();
      const got = op => { const s = buildSpec(applyChange(base, {ops: [op]})); return {items: [...new Set(s.rows.map(x => x.series))].sort(), note: s.autoNote}; };
      ({latest: got({op: "top_n", n: 5}), mean: got({op: "top_n", n: 5, by: "mean"}), total: got({op: "top_n", n: 5, by: "total"}), y2019: got({op: "top_n", n: 5, by: "2019"}),
        wantLatest: top(s => at(s, "2025")), wantMean: top(mean), wantTotal: top(sum), want2019: top(s => at(s, "2019"))})
    """)
    assert out["latest"]["items"] == out["wantLatest"] and "by 2025 value." in out["latest"]["note"]
    assert out["mean"]["items"] == out["wantMean"] and "by average from 2019 to 2025." in out["mean"]["note"]
    assert out["total"]["items"] == out["wantTotal"]
    assert out["y2019"]["items"] == out["want2019"] and "by 2019 value." in out["y2019"]["note"]


def test_bump_keeps_rank_logic():
    out = run(load("samples", "MOCK_ai_patent_rank_countries_2015_2025.csv"), """
      const base = fitsKind("bump", {filters: []});
      if (!base) null; else {
        const rows = buildSpec(base).rows;
        const best = new Map(); rows.forEach(x => best.set(x.cat, Math.min(best.get(x.cat) ?? Infinity, x.v)));
        const want = [...best].sort((a, b) => a[1] - b[1]).slice(0, 4).map(e => e[0]).sort();
        const s = buildSpec(applyChange(base, {ops: [{op: "top_n", n: 4, by: "mean"}]}));
        ({got: [...new Set(s.rows.map(x => x.cat))].sort(), want, note: s.autoNote});
      }
    """)
    if out is None:
        pytest.skip("no bump for this file")
    assert out["got"] == out["want"] and "by best rank" in out["note"]


def test_top_n_ranks_within_the_picked_size_class_and_year():
    out = run(stress(), f"""
      let r = fitsKind("bar", {{filters: []}});
      r = applyChange(r, {{ops: [{{op: "filter", column: "{SIZE}", keep: ["250 persons employed or more"]}}, {{op: "filter", column: "Year", keep: ["2023"]}}, {{op: "top_n", n: 5}}]}});
      const s = buildSpec(r);
      const src = state.data.rows.filter(x => x["{SIZE}"] === "250 persons employed or more" && String(x.Year) === "2023" && !isAggregate(x.GEO) && typeof x.Value === "number");
      const want = src.sort((a, b) => b.Value - a.Value).slice(0, 5).map(x => [x.GEO, x.Value]);
      ({{got: s.rows.filter(x => !isAggregate(x.cat)).map(x => [x.cat, x.v]), want, note: s.autoNote}})
    """)
    assert out["got"] == out["want"]
    assert out["note"].startswith("Showing: 250 persons employed or more, 2023. Top 5 of ")


def test_guard_holds_with_top_n():
    code = CHECK.replace("const s = buildSpec(r), map = r.roles;",
                         "const r0 = r; r = applyChange(r0, {ops: [{op: \"top_n\", n: 3}]}); const s = buildSpec(r), map = r.roles;")
    for name in (STRESS, VC, VAC):
        out = run(load("samples", name), code)
        assert not out["problems"], name + "\n" + "\n".join(out["problems"][:8])


def test_slider_steps_rank_per_year():
    out = run(load("samples", VAC), """
      let r = applyChange(fitsKind("bar", {filters: []}), {ops: [{op: "top_n", n: 3}], set: {controls: [{type: "slider", column: "Year"}]}});
      const s = buildSpec(r);
      const k = Object.keys(s.variants)[0];
      const y = s.controls[0].options[0];
      const want = state.data.rows.filter(x => String(x.Year) === y && typeof x.Value === "number").sort((a, b) => b.Value - a.Value).slice(0, 3).map(x => x.region).sort();
      ({got: s.variants[k].rows.map(x => x.cat).sort(), want, note: s.variants[k].autoNote, y})
    """)
    assert out["got"] == out["want"]
    assert f"by {out['y']} value." in out["note"]


def test_by_is_validated():
    ch = validate_change({"reply": "ok", "ops": [{"op": "top_n", "n": 5, "by": "Average"}]}, COLUMNS, [])
    assert ch["ops"][0] == {"op": "top_n", "n": 5, "other": False, "by": "mean"}
    ch = validate_change({"reply": "ok", "ops": [{"op": "top_n", "n": 5, "by": 2023}]}, COLUMNS, [])
    assert ch["ops"][0]["by"] == "2023"
    ch = validate_change({"reply": "ok", "ops": [{"op": "top_n", "n": 5}]}, COLUMNS, [])
    assert "by" not in ch["ops"][0]
    with pytest.raises(ChangeError):
        validate_change({"reply": "ok", "ops": [{"op": "top_n", "n": 5, "by": "2030"}]}, COLUMNS, [])
    with pytest.raises(ChangeError):
        validate_change({"reply": "ok", "ops": [{"op": "top_n", "n": 5, "by": "2023"}]}, [COLUMNS[0], COLUMNS[2]], [])


def test_prompt_knows_top_n_and_country_lists():
    assert '"by": "mean"' in SYSTEM and "never count toward N" in SYSTEM
    assert 'values_are is "rates"' in SYSTEM
    assert "lists each member country found in the column's values" in SYSTEM


def test_keep_list_matches_case_loosely():
    ch = validate_change({"reply": "ok", "ops": [{"op": "filter", "column": "country", "keep": ["belgium", "SPAIN"]}]}, COLUMNS, [])
    assert ch["ops"][0]["keep"] == ["Belgium", "Spain"]


def test_rate_ranking_never_says_total():
    out = run(stress(), """
      const heat = applyChange(fitsKind("heatmap", {filters: []}), {ops: [{op: "top_n", n: 10}]});
      const bar = applyChange(fitsKind("bar", {filters: []}), {ops: [{op: "top_n", n: 10}]});
      ({heat: buildSpec(heat).autoNote, bar: buildSpec(bar).autoNote, rate: isRate(heat)})
    """)
    assert out["rate"] is True
    assert "by the sum of their 2025 values." in out["heat"] and "total" not in out["heat"].split(".")[0]
    assert "by 2025 value." in out["bar"]


def test_amounts_still_rank_by_total():
    out = run(load("samples", VC), """
      const base = fitsKind("stacked_bar", {filters: []});
      if (!base) null; else { const r = applyChange(base, {ops: [{op: "top_n", n: 3}]}); ({rate: isRate(r), note: buildSpec(r).autoNote}); }
    """)
    assert out and out["rate"] is False
    assert re.search(r"Top 3 of \d+ \w+, by (\S+ )?total\.", out["note"])


def test_rate_flag_reaches_the_chart():
    out = run(stress(), """
      ({rate: buildSpec(fitsKind("bar", {filters: []})).rate})
    """)
    vc = run(load("samples", VC), """({rate: buildSpec(fitsKind("bar", {filters: []})).rate ?? null})""")
    assert out["rate"] is True and vc["rate"] is None


def _cat_values(rows, rate):
    src = (ROOT / "web" / "charts.js").read_text()
    body = src[src.index("  function sumBy(rows, key) {"):src.index("  function pivot(rows, rowKey, colKey) {")]
    js = (f"const d3 = require({json.dumps(str(ROOT / 'web' / 'vendor' / 'd3.min.js'))});\nconst OTHER = \"Other\";\n{body}\n"
          f"const d = catValues({json.dumps(rows)}, 40, false, {json.dumps(rate)});\n"
          "process.stdout.write(JSON.stringify({rows: d.map(e => [e.cat, e.v]), cut: d.cut ?? null}));")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_bar_cap_sums_counts_into_other():
    rows = [{"cat": f"c{i}", "v": 100 - i} for i in range(45)]
    out = _cat_values(rows, False)
    assert len(out["rows"]) == 41 and out["rows"][-1] == ["Other", sum(100 - i for i in range(40, 45))]


def test_bar_cap_leaves_other_out_for_rates():
    rows = [{"cat": f"c{i}", "v": 50 - i} for i in range(45)]
    out = _cat_values(rows, True)
    assert len(out["rows"]) == 40 and "Other" not in [c for c, _ in out["rows"]] and out["cut"] == 5
    assert [c for c, _ in out["rows"]] == [f"c{i}" for i in range(40)]
