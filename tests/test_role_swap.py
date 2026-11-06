import pytest

from app.viz_chat import ChangeError, validate_change
from app.viz_parse import parse_file
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


def companies():
    rows = ["country,ai_companies,all_companies,ai_recent_companies,recent_companies",
            "Belgium,120,9000,40,2100", "France,800,61000,260,15000", "Germany,950,72000,300,17000", "Spain,400,38000,150,9800"]
    out = parse_file("\n".join(rows).encode(), "companies.csv", None)
    names = [c["name"] for c in out["columns"]]
    return {**out, "rows": [dict(zip(names, r)) for r in out["rows"]], "cols": out["columns"], "name": "companies.csv"}


def test_chat_picks_the_value_columns_of_a_stacked_bar():
    out = run(companies(), """
      const ALL = ["ai_companies", "all_companies", "ai_recent_companies", "recent_companies"];
      const r = withAutoControls(applyChange(fitsKind("stacked_bar", {filters: []}), {ops: [{op: "roles", cat: "country", columns: ALL}]}));
      const two = applyChange(r, {ops: [{op: "roles", columns: ["ai_recent_companies", "recent_companies"]}]});
      const s = buildSpec(two);
      ({before: r.roles.wide, seen: recipeForAI(two).value_columns, labels: recipeForAI(two).value_column_labels, roles: two.roles,
        targets: [...new Set(s.rows.map(x => x.series))]})
    """)
    assert len(out["before"]) == 4
    assert out["roles"]["cat"] == "country" and out["roles"]["series"] == "(columns)"
    assert out["roles"]["wide"] == ["ai_recent_companies", "recent_companies"]
    assert out["seen"] == ["ai_recent_companies", "recent_companies"]
    assert sorted(out["labels"].values()) == sorted(out["targets"]) and len(out["targets"]) == 2


def test_sankey_is_not_offered_for_overlapping_value_columns():
    out = run(companies(), """
      const ALL = ["ai_companies", "all_companies", "ai_recent_companies", "recent_companies"];
      const bar = fitsKind("stacked_bar", {filters: []});
      let asked = null;
      try { applyChange(bar, {set: {kind: "sankey"}, ops: [{op: "roles", cat: "country", columns: ALL}]}); } catch (e) { asked = e.message; }
      ({sankey: fitsKind("sankey", {filters: []}), opts: kindOptions("bar", [["sankey", 0.9]]), asked})
    """)
    assert out["sankey"] is None and "sankey" not in out["opts"]
    assert out["asked"]


def test_long_form_sankey_is_still_offered():
    rows = ["source,target,amount"] + [f"{s},{t},{i + j + 1}" for i, s in enumerate(["Belgium", "France", "Spain"]) for j, t in enumerate(["Software", "Hardware"])]
    out = parse_file("\n".join(rows).encode(), "flows.csv", None)
    names = [c["name"] for c in out["columns"]]
    data = {**out, "rows": [dict(zip(names, r)) for r in out["rows"]], "cols": out["columns"], "name": "flows.csv"}
    got = run(data, """const r = fitsKind("sankey", {filters: []}); ({roles: r && r.roles, opts: kindOptions("bar", [])})""")
    assert got["roles"] == {"cat": "source", "series": "target", "v": "amount"}
    assert "sankey" in got["opts"]


def test_value_columns_must_be_numbers():
    cols = [{"name": "country", "type": "category"}, {"name": "ai_companies", "type": "number"}, {"name": "recent_companies", "type": "number"}]
    with pytest.raises(ChangeError) as e:
        validate_change({"reply": "ok", "ops": [{"op": "roles", "columns": ["country", "ai_companies"]}]}, cols, [], "stacked_bar")
    assert '"country"' in str(e.value)
    with pytest.raises(ChangeError):
        validate_change({"reply": "ok", "ops": [{"op": "roles", "columns": ["ai_companies"]}]}, cols, [], "stacked_bar")
    ok = validate_change({"reply": "ok", "ops": [{"op": "roles", "columns": ["AI companies", "recent_companies"]}]}, cols, [], "stacked_bar")
    assert ok["ops"][0]["columns"] == ["ai_companies", "recent_companies"]


WIDE_COLS = [{"name": "country", "type": "category"}] + [{"name": n, "type": "number"} for n in ("ai_use_small", "ai_use_large", "ai_use_all")]
SHOWN = {"ai_use_small": "Small firms", "ai_use_large": "Large firms", "ai_use_all": "All firms"}


def test_chat_drops_a_drawn_series_by_its_chart_name():
    for column in ("(columns)", "series"):
        out = validate_change({"reply": "ok", "ops": [{"op": "filter", "column": column, "drop": ["All firms"]}]}, WIDE_COLS, [], "stacked_bar", shown=SHOWN)
        assert out["ops"] == [{"op": "roles", "columns": ["ai_use_small", "ai_use_large"]}]
    out = validate_change({"reply": "ok", "ops": [{"op": "filter", "column": "(columns)", "keep": ["small firms", "ai_use_all"]}]}, WIDE_COLS, [], "stacked_bar", shown=SHOWN)
    assert out["ops"] == [{"op": "roles", "columns": ["ai_use_small", "ai_use_all"]}]
    out = validate_change({"reply": "ok", "ops": [{"op": "roles", "columns": ["Small firms", "Large firms"]}]}, WIDE_COLS, [], "stacked_bar", shown=SHOWN)
    assert out["ops"][0]["columns"] == ["ai_use_small", "ai_use_large"]
    with pytest.raises(ChangeError, match="Small firms"):
        validate_change({"reply": "ok", "ops": [{"op": "filter", "column": "(columns)", "drop": ["Tiny firms"]}]}, WIDE_COLS, [], "stacked_bar", shown=SHOWN)
    with pytest.raises(ChangeError, match="roles op with v"):
        validate_change({"reply": "ok", "ops": [{"op": "filter", "column": "(columns)", "keep": ["Small firms"]}]}, WIDE_COLS, [], "stacked_bar", shown=SHOWN)
    with pytest.raises(ChangeError, match="no column"):
        validate_change({"reply": "ok", "ops": [{"op": "filter", "column": "(columns)", "drop": ["All firms"]}]}, WIDE_COLS, [], "stacked_bar")


def test_chat_cannot_draw_a_sankey_from_value_columns():
    with pytest.raises(ChangeError, match="source column and one target column"):
        validate_change({"reply": "ok", "set": {"kind": "sankey"}, "ops": [{"op": "roles", "columns": ["ai_use_small", "ai_use_large"]}]}, WIDE_COLS, [], "stacked_bar")


WIDE_CHAT = {"message": "Drop all firms", "columns": WIDE_COLS, "chart_names": list(SHOWN.values()),
             "recipe": {"kind": "stacked_bar", "title": "AI use by firm size, all firms included", "roles": {"cat": "country", "series": "(columns)", "v": "(value)"},
                        "value_columns": list(SHOWN), "value_column_labels": SHOWN}}


def test_chat_asks_for_a_title_when_it_hides_series(client, monkeypatch):
    from tests.test_patches import fake_chat
    c = client
    drop = {"reply": "Dropped all firms.", "ops": [{"op": "filter", "column": "(columns)", "drop": ["All firms"]}]}
    titled = {**drop, "set": {"title": "AI use in small and large firms"}}
    sent = fake_chat(monkeypatch, [drop, titled])
    j = c.post("/api/viz/chat", json=WIDE_CHAT).json()
    assert j["tries"] == 2 and j["set"]["title"] == "AI use in small and large firms"
    assert j["ops"] == [{"op": "roles", "columns": ["ai_use_small", "ai_use_large"]}]
    assert "title" in sent[1]["messages"][-1]["content"]
    sent = fake_chat(monkeypatch, [titled])
    assert c.post("/api/viz/chat", json=WIDE_CHAT).json()["tries"] == 1
    sent = fake_chat(monkeypatch, [{"reply": "Bigger font.", "set": {"fontSize": "large"}}])
    assert c.post("/api/viz/chat", json=WIDE_CHAT).json()["tries"] == 1
