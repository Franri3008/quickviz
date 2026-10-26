from tests.test_no_blending import STRESS, load, run

SIZE = "Size classes in number of persons employed"
EU = "European Union - 27 countries (from 2020)"
EA = "Euro area – 20 countries (from 2023)"
GAP = "MOCK_ai_use_gap_small_vs_large_firms.csv"


def stress():
    return load("samples", STRESS)


def start(kind):
    return f"""
      let r = withAutoControls(applyChange(fitsKind("{kind}", {{filters: []}}), {{ops: [{{op: "roles", cat: "GEO", series: "{SIZE}"}}]}}));
      r = withAutoControls(applyChange(r, {{ops: [{{op: "top_n", n: 10, other: true}}]}}));
      const before = buildSpec(r);
      const swapped = withAutoControls(applyChange(r, {{set: {{xLabel: "Country"}}, ops: [{{op: "roles", cat: "{SIZE}", series: "GEO"}}]}}));
      const after = buildSpec(swapped);
    """


def test_heatmap_swap_keeps_the_top_10_countries():
    out = run(stress(), start("heatmap") + """
      ({roles: swapped.roles, top: swapped.top, filters: swapped.filters.map(f => f.column),
        cats: [...new Set(after.rows.map(x => x.cat))], series: [...new Set(after.rows.map(x => x.series))],
        beforeCats: [...new Set(before.rows.map(x => x.cat))], note: after.autoNote})
    """)
    assert out["roles"] == {"cat": SIZE, "series": "GEO", "v": "Value"}
    assert out["top"]["column"] == "GEO" and out["top"]["n"] == 10
    assert "flag" not in out["roles"].values()
    assert out["filters"] == ["Year"]
    assert sorted(out["series"]) == sorted(out["beforeCats"])
    assert len(out["series"]) == 12 and EU in out["series"] and EA in out["series"]
    assert len(out["cats"]) == 3
    assert "Top 10 of 29 " in out["note"]


def test_stacked_bar_swap_keeps_the_top_10_countries():
    out = run(stress(), start("stacked_bar") + """
      ({roles: swapped.roles, series: [...new Set(after.rows.map(x => x.series))], beforeCats: [...new Set(before.rows.map(x => x.cat))]})
    """)
    assert out["roles"]["cat"] == SIZE and out["roles"]["series"] == "GEO"
    assert len(out["series"]) == 10
    assert set(out["series"]) <= set(out["beforeCats"])


def test_top_n_set_on_the_wider_axis_and_follows_back():
    out = run(stress(), f"""
      let r = withAutoControls(applyChange(fitsKind("heatmap", {{filters: []}}), {{ops: [{{op: "roles", cat: "{SIZE}", series: "GEO"}}, {{op: "top_n", n: 8}}]}}));
      const a = buildSpec(r);
      const back = applyChange(r, {{ops: [{{op: "roles", cat: "GEO", series: "{SIZE}"}}]}});
      const b = buildSpec(back);
      ({{column: r.top.column, a: [...new Set(a.rows.map(x => x.series))].filter(v => !isAggregate(v)).sort(), b: [...new Set(b.rows.map(x => x.cat))].filter(v => !isAggregate(v)).sort()}})
    """)
    assert out["column"] == "GEO"
    assert len(out["a"]) == 8 and out["a"] == out["b"]


def test_line_top_n_rests_while_its_column_is_off_the_chart():
    out = run(stress(), f"""
      let r = withAutoControls(applyChange(fitsKind("line", {{filters: []}}), {{ops: [{{op: "roles", series: "GEO"}}, {{op: "top_n", n: 5, by: "latest"}}]}}));
      const a = [...new Set(buildSpec(r).rows.map(x => x.series))].filter(v => !isAggregate(v)).sort();
      const other = applyChange(r, {{ops: [{{op: "roles", series: "{SIZE}"}}]}});
      const mid = buildSpec(other);
      const back = applyChange(other, {{ops: [{{op: "roles", series: "GEO"}}]}});
      const b = [...new Set(buildSpec(back).rows.map(x => x.series))].filter(v => !isAggregate(v)).sort();
      ({{a, b, mid: [...new Set(mid.rows.map(x => x.series))].length, midNote: mid.autoNote, column: back.top.column}})
    """)
    assert len(out["a"]) == 5 and out["a"] == out["b"]
    assert out["mid"] == 3 and "Top 5" not in out["midNote"]
    assert out["column"] == "GEO"


def test_too_many_columns_is_refused_plainly():
    out = run(stress(), f"""
      const r = withAutoControls(applyChange(fitsKind("heatmap", {{filters: []}}), {{ops: [{{op: "roles", cat: "GEO", series: "{SIZE}"}}]}}));
      let msg = "";
      try {{ applyChange(r, {{ops: [{{op: "roles", cat: "{SIZE}", series: "GEO"}}]}}); }} catch (e) {{ msg = e.message; }}
      msg
    """)
    assert out.startswith("GEO has 32 values, too many for the columns of a heatmap chart.")
    assert "top" in out and "Nothing was changed." in out


def test_dot_range_swap_needs_two_dots():
    out = run(load("samples", GAP), """
      const r = withAutoControls(fitsKind("dot_range", {filters: []}));
      let msg = "";
      try { applyChange(r, {ops: [{op: "roles", cat: "firm_size", series: "country"}]}); } catch (e) { msg = e.message; }
      const two = applyChange(r, {ops: [{op: "filter", column: "country", keep: ["Belgium", "Sweden"]}, {op: "roles", cat: "firm_size", series: "country"}]});
      const s = buildSpec(two);
      ({start: r.roles, msg, roles: two.roles, rows: s.rows.map(x => [x.cat, x.series])})
    """)
    assert out["start"]["cat"] == "country" and out["start"]["series"] == "firm_size"
    assert out["msg"].startswith("A dot range needs exactly two values for its dots, and country has 28.")
    assert out["roles"]["cat"] == "firm_size" and out["roles"]["series"] == "country"
    assert len(out["rows"]) == 4


def test_flag_column_is_never_guessed():
    out = run(stress(), f"""
      inRoom(new Map(), () => heuristicMap("heatmap", state.data.cols, {{cat: "{SIZE}", series: "GEO", v: "Value"}}))
    """)
    assert out["series"] != "flag"


def test_refused_change_reply_says_only_what_happened():
    out = run(stress(), f"""
      state.recipe = withAutoControls(applyChange(fitsKind("heatmap", {{filters: []}}), {{ops: [{{op: "roles", cat: "GEO", series: "{SIZE}"}}]}}));
      const m = {{}};
      const res = {{reply: "Swapped the axes so countries run across the columns.", set: {{xLabel: "Country"}}, ops: [{{op: "roles", cat: "{SIZE}", series: "GEO"}}]}};
      applyReply(state.recipe, res, m, "swap", 0).then(o => ({{text: m.text, applied: !!m.applied, out: o, roles: state.recipe.roles}}))
    """)
    assert "Swapped" not in out["text"]
    assert out["text"].startswith("GEO has 32 values")
    assert not out["applied"]
    assert out["roles"]["cat"] == "GEO"
