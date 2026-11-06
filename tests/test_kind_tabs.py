import shutil

import pytest

from tests.test_app_logic import ADOPTION, ADOPTION_JEV, js, load

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def test_tabs_list_every_fitting_kind_even_when_jev_rates_it_low():
    ranked = [["bar", 0.7], ["map", 0.2], ["treemap", 0.04], ["donut", 0.01], ["dot_range", 0.001]]
    out = js(load(ADOPTION), f"""
      const opts = kindOptions("bar", {ranked!r});
      const every = Object.keys(KIND_NAMES).filter(k => fitsKind(k, {{filters: []}}));
      ({{opts, every}})
    """.replace("'", '"'), ADOPTION_JEV)
    assert out["opts"][0] == "bar"
    assert set(out["opts"]) == set(out["every"]) | {"bar"}
    assert "treemap" not in out["opts"] and "donut" in out["opts"] and "dot_range" in out["opts"]
    assert out["opts"].index("donut") < out["opts"].index("dot_range")
    assert len(out["opts"]) > 6


def test_tabs_keep_jev_order_and_put_unrated_kinds_last():
    out = js(load(ADOPTION), """
      kindOptions("treemap", [["donut", 0.5], ["bar", 0.3]])
    """, ADOPTION_JEV)
    assert out[:3] == ["treemap", "donut", "bar"]
    assert len(out) == len(set(out))


def test_tabs_without_jev_still_list_every_fitting_kind():
    out = js(load(ADOPTION), """
      const opts = kindOptions("bar", null);
      [opts[0], opts.length === new Set(opts).size, opts.every(k => k === "bar" || fitsKind(k, {filters: []}))]
    """)
    assert out == ["bar", True, True]


def test_treemap_of_rates_is_never_offered_or_drawn():
    out = js(load(ADOPTION), """
      const bar = fitsKind("bar", {filters: []});
      let msg = "";
      try { applyChange(bar, {set: {kind: "treemap"}}); } catch (e) { msg = e.message; }
      const shares = applyChange(bar, {ops: [{op: "percent_share", within: "total"}]});
      const whole = applyChange(shares, {set: {kind: "treemap"}});
      ({fits: fitsKind("treemap", {filters: []}), tabs: kindOptions("bar", [["treemap", 0.9]]).includes("treemap"),
        alt: [...new Set([...kindOptions("bar", null), ...KIND_ORDER])].find(k => k !== "bar" && fitsKind(k, {filters: []})),
        msg, whole: whole.kind, total: Math.round(buildSpec(whole).rows.reduce((a, r) => a + r.v, 0))})
    """, ADOPTION_JEV)
    assert out["fits"] is None and out["tabs"] is False and out["alt"] != "treemap"
    assert out["msg"] == "A treemap adds the values up, and these are rates, so the tiles would mean nothing. Nothing was changed."
    assert out["whole"] == "treemap" and out["total"] == 100


def test_treemap_of_counts_is_still_offered():
    out = js(load("MOCK_ai_venture_capital_by_technology_semicolon.csv"), """
      const r = fitsKind("treemap", {filters: []});
      ({kind: r && r.kind, rate: r ? isRate(r) : null})
    """)
    assert out == {"kind": "treemap", "rate": False}


def companies():
    from app import viz_reading
    from app.viz_parse import parse_file
    from tests.test_parse_ai import COMPANY_ITEMS
    raw = viz_reading.wide_csv([{**it, "unsure": False} for it in COMPANY_ITEMS], ["Revenue", "Profit", "Employees"])
    out = parse_file(raw, "picture.csv")
    names = [c["name"] for c in out["columns"]]
    return {**out, "cols": out["columns"], "rows": [{n: ("" if v is None else v) for n, v in zip(names, r)} for r in out["rows"]], "name": "companies.png"}


COMPANY_NAMES = {"title": "Largest companies by revenue", "unit": "$", "columns": {"Label": "Company", "Revenue": "Revenue (USD bn)"}}
START = """
  state.recipe = withAutoControls(fitsKind("bar", {filters: []}));
  state.names = {...state.names, forKey: namesKey(state.recipe.roles)};
  state.opts = kindOptions("bar", null); state.view = 3;
  const before = buildSpec(state.recipe);
  const blocks = () => colBlocks(state.recipe).map(b => [b.name, !!b.on, b.tip || ""]);
"""


def test_columns_row_lists_every_column_and_marks_the_drawn_ones():
    out = js(companies(), START + "({roles: state.recipe.roles, blocks: blocks(), y: before.yLabel, title: before.title})", None, COMPANY_NAMES)
    assert out["roles"] == {"cat": "Label", "v": "Revenue"}
    assert out["blocks"] == [["Label", True, ""], ["Revenue", True, ""], ["Profit", False, ""], ["Employees", False, ""]]
    assert out["y"] == "Revenue (USD bn)" and out["title"] == "Largest companies by revenue"


def test_clicking_a_number_column_makes_it_the_value_with_no_ai_call():
    out = js(companies(), START + """
      let calls = 0; fetch = u => { if (String(u).includes("api/viz")) calls++; return Promise.reject(new Error("offline")); };
      const pick = n => { const b = colBlocks(state.recipe).find(x => x.name === n); localChange(b.change, b.label); return buildSpec(state.recipe); };
      const p = pick("Profit"), e = pick("Employees"), back = pick("Revenue");
      ({roles: state.recipe.roles, calls, blocks: blocks(), note: state.chat.at(-1).text,
        p: [p.title, p.yLabel, p.unit], e: [e.title, e.yLabel, e.unit], back: [back.title, back.yLabel, back.unit]})
    """, None, COMPANY_NAMES)
    assert out["calls"] == 0 and out["note"] == "Showing Revenue"
    assert out["p"] == ["Profit by company", "Profit", ""]
    assert out["e"] == ["Employees by company", "Employees", ""]
    assert out["back"] == ["Largest companies by revenue", "Revenue (USD bn)", "$"]
    assert out["blocks"][1] == ["Revenue", True, ""] and out["blocks"][2] == ["Profit", False, ""]


def test_a_column_click_drops_axis_text_set_for_the_old_column():
    out = js(companies(), START + """
      state.recipe = applyChange(state.recipe, {set: {title: "Revenue of the giants", yLabel: "Revenue in USD bn", valueMax: 900}});
      const b = colBlocks(state.recipe).find(x => x.name === "Profit");
      localChange(b.change, b.label);
      const s = buildSpec(state.recipe);
      [s.title, s.yLabel, s.valueMax ?? null]
    """, None, COMPANY_NAMES)
    assert out == ["Profit by company", "Profit", None]


def test_value_columns_are_added_and_removed_within_the_limit():
    out = js(companies(), START + """
      const h = withAutoControls(applyChange(state.recipe, {set: {kind: "heatmap"}, ops: [{op: "roles", columns: ["Revenue", "Profit"]}]}));
      state.recipe = h;
      const two = blocks();
      const add = colBlocks(h).find(x => x.name === "Employees");
      localChange(add.change, add.label);
      const three = blocks();
      const rev = colBlocks(state.recipe).find(x => x.name === "Revenue");
      localChange(rev.change, rev.label);
      ({two, three, wide: state.recipe.roles.wide, s: buildSpec(state.recipe).yLabel})
    """, None, COMPANY_NAMES)
    assert out["two"][1:] == [["Revenue", True, "This chart needs at least two value columns."],
                              ["Profit", True, "This chart needs at least two value columns."], ["Employees", False, ""]]
    assert out["three"][1:] == [["Revenue", True, ""], ["Profit", True, ""], ["Employees", True, ""]]
    assert out["wide"] == ["Profit", "Employees"]


def test_text_columns_become_the_labels_and_misfits_say_why():
    out = js(load(ADOPTION), """
      state.recipe = withAutoControls(fitsKind("bar", {filters: []}));
      const g = colBlocks(state.recipe).find(x => x.name === "iso3");
      const next = applyChange(state.recipe, g.change);
      const group = colBlocks(state.recipe).find(x => x.name === "country_group");
      const hist = colBlocks(applyChange(state.recipe, {set: {kind: "histogram"}})).filter(b => b.tip).map(b => [b.name, b.tip]);
      ({cat: next.roles.cat, label: g.label, group: [group.on, group.change || null, group.tip], hist})
    """, ADOPTION_JEV)
    assert out["cat"] == "iso3" and out["label"] == "iso3 as the labels"
    assert out["group"] == [False, None, "Each label would mix several rows. Ask in the chat to sum or average them."]
    assert ["country", "A histogram chart draws numbers only."] in out["hist"]


def test_chat_value_swaps_update_the_columns_row():
    out = js(companies(), START + """
      const profit = withAutoControls(applyChange(state.recipe, {ops: [{op: "roles", v: "Profit"}]}));
      let refused = "";
      try { applyChange(state.recipe, {ops: [{op: "roles", columns: ["Revenue", "Profit"]}]}); } catch (e) { refused = e.message; }
      const both = withAutoControls(applyChange(state.recipe, {set: {kind: "heatmap"}, ops: [{op: "roles", columns: ["Revenue", "Profit"]}]}));
      ({profit: colBlocks(profit).filter(b => b.on).map(b => b.name), y: buildSpec(profit).yLabel, refused,
        both: colBlocks(both).filter(b => b.on).map(b => b.name), title: buildSpec(both).title})
    """, None, COMPANY_NAMES)
    assert out["profit"] == ["Label", "Profit"] and out["y"] == "Profit"
    assert out["refused"] == "A bar chart cannot show Revenue, Profit as its value columns. Nothing was changed."
    assert out["both"] == ["Label", "Revenue", "Profit"] and out["title"] == "Revenue (USD bn) and profit by company"


def test_chat_ops_for_use_profit_and_show_revenue_and_profit_pass_the_server(client, monkeypatch):
    from tests.test_patches import fake_chat
    c = client
    cols = [{"name": "Label", "type": "category"}] + [{"name": n, "type": "number"} for n in ("Revenue", "Profit", "Employees")]
    body = {"message": "use profit instead", "columns": cols, "chart_names": ["Walmart", "Amazon"],
            "recipe": {"kind": "bar", "roles": {"cat": "Label", "v": "Revenue"}}}
    fake_chat(monkeypatch, [{"reply": "Showing profit.", "ops": [{"op": "roles", "v": "profit"}]}])
    j = c.post("/api/viz/chat", json=body).json()
    assert j["ops"] == [{"op": "roles", "v": "Profit"}]
    both = {"reply": "Revenue and profit side by side.", "set": {"kind": "heatmap"}, "ops": [{"op": "roles", "columns": ["Revenue", "Profit"]}]}
    fake_chat(monkeypatch, [both])
    j = c.post("/api/viz/chat", json={**body, "message": "show revenue and profit"}).json()
    assert j["set"]["kind"] == "heatmap" and j["ops"] == [{"op": "roles", "columns": ["Revenue", "Profit"]}]


def director_table():
    import json

    from app import viz_reading
    from app.viz_parse import parse_file
    from tests.test_parse_ai import director_rows
    t = viz_reading.table_rows(json.dumps(director_rows(), ensure_ascii=False))
    out = parse_file(viz_reading.table_csv(viz_reading.merge_tables([t])), "picture.csv")
    names = [c["name"] for c in out["columns"]]
    return {**out, "cols": out["columns"], "rows": [{n: ("" if v is None else v) for n, v in zip(names, r)} for r in out["rows"]], "name": "companies.png"}


def director_long():
    from app import viz_reading
    from app.viz_parse import parse_file
    from tests.test_parse_ai import COMPANY_ITEMS
    out = parse_file(viz_reading.picture_csv(COMPANY_ITEMS, "Rank"), "picture.csv")
    names = [c["name"] for c in out["columns"]]
    return {**out, "cols": out["columns"], "rows": [{n: ("" if v is None else v) for n, v in zip(names, r)} for r in out["rows"]], "name": "companies.png"}


SWITCH_ASK = "Add a button to switch between Revenue, Proft, Employees"
SWITCH_REPLY = {"reply": "Added buttons for the three measures.", "set": {"controls": [{"type": "switch", "label": "Measure", "options": [
    {"label": x, "ops": [{"op": "roles", "v": x}]} for x in ("Revenue", "Proft", "Employees")]}]}}


def chat_columns(data):
    return [{"name": c["name"], "type": c["type"], "distinct": c["distinct"],
             **({} if c["type"] == "number" else {"values": list(dict.fromkeys(str(r[c["name"]]) for r in data["rows"]))})} for c in data["cols"]]


def draw_control(data, control, roles):
    import json
    return js(data, f"""
      const r = fitsKind("bar", {{filters: []}});
      r.roles = {{...r.roles, ...{json.dumps(roles)}}};
      r.controls = [{json.dumps(control)}];
      const s = buildSpec(r);
      ({{type: s.controls[0].type, labels: s.controls[0].options,
        tops: Object.keys(s.variants).sort().map(k => Math.max(...s.variants[k].rows.map(x => x.v)))}})
    """)


def test_a_switch_over_the_three_split_columns_passes_and_draws(client, monkeypatch):
    from tests.test_patches import fake_chat
    data = director_table()
    assert [c["name"] for c in data["cols"]] == ["Name", "Industry", "Revenue (USD bn)", "Profit (USD bn)", "Employees", "Headquarters", "State-owned"]
    c = client
    sent = fake_chat(monkeypatch, [SWITCH_REPLY])
    body = {"message": SWITCH_ASK, "columns": chat_columns(data), "chart_names": [r["Name"] for r in data["rows"]],
            "recipe": {"kind": "bar", "roles": {"cat": "Name", "v": "Revenue (USD bn)"}}}
    r = c.post("/api/viz/chat", json=body)
    assert r.status_code == 200, r.text
    ctl = r.json()["set"]["controls"][0]
    assert len(sent) == 1 and ctl["type"] == "select" and ctl["style"] == "buttons"
    assert [o["ops"] for o in ctl["options"]] == [[{"op": "roles", "v": v}] for v in ("Revenue (USD bn)", "Profit (USD bn)", "Employees")]
    out = draw_control(data, ctl, {"cat": "Name", "v": "Revenue (USD bn)"})
    assert out["labels"] == ["Revenue", "Profit", "Employees"] and out["tops"] == [716, 88.9, 2100000]


def test_the_same_switch_on_the_long_shape_filters_the_series(client, monkeypatch):
    from app.viz_chat import ChangeError, validate_change
    from tests.test_patches import fake_chat
    data = director_long()
    cols = chat_columns(data)
    assert [c["name"] for c in cols] == ["Label", "Series", "Rank"]
    assert validate_change({"reply": "x", "ops": [{"op": "roles", "v": "Proft"}]}, cols, [])["ops"] == [
        {"op": "filter", "column": "Series", "keep": ["Profit"]}]
    with pytest.raises(ChangeError, match='There is no column "Sales"'):
        validate_change({"reply": "x", "ops": [{"op": "roles", "v": "Sales"}]}, cols, [])
    c = client
    fake_chat(monkeypatch, [SWITCH_REPLY])
    body = {"message": SWITCH_ASK, "columns": cols, "chart_names": [], "recipe": {"kind": "bar", "roles": {"cat": "Label", "v": "Rank"}}}
    r = c.post("/api/viz/chat", json=body)
    assert r.status_code == 200, r.text
    ctl = r.json()["set"]["controls"][0]
    assert ctl["type"] == "select" and [o["ops"] for o in ctl["options"]] == [
        [{"op": "filter", "column": "Series", "keep": [v]}] for v in ("Revenue", "Profit", "Employees")]
    out = draw_control(data, ctl, {"cat": "Label", "v": "Rank", "series": None})
    assert out["tops"] == [716, 88.9, 2100000]
