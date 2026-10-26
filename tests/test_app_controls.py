import shutil

import pytest

from tests.test_app_logic import ADOPTION, ADOPTION_JEV, ROOT, js, load

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")
VC = "MOCK_ai_venture_capital_by_technology_semicolon.csv"


def test_year_slider_makes_one_version_per_step():
    out = js(load(VC), """
      const r = fitsKind("bar", {filters: []});
      r.controls = [{type: "slider", column: "quarter", label: "Quarter", play: true}];
      const s = buildSpec(r);
      const c = s.controls[0];
      ({n: c.options.length, first: c.options[0], last: c.options.at(-1), initial: c.initial, play: c.play,
        keys: Object.keys(s.variants).length, cats: new Set(s.variants["0"].rows.map(x => x.cat)).size,
        differs: JSON.stringify(s.variants["0"].rows) !== JSON.stringify(s.variants[String(c.options.length - 1)].rows),
        latestSame: JSON.stringify(s.variants[String(c.initial)].rows) === JSON.stringify(s.rows)})
    """)
    assert out["n"] == 20
    assert out["first"] == "2021-Q1" and out["last"] == "2025-Q4"
    assert out["initial"] == 19
    assert out["play"] is True
    assert out["keys"] == 20
    assert out["cats"] == 6
    assert out["differs"] is True
    assert out["latestSame"] is True


def test_slider_on_the_time_axis_reveals_steps():
    out = js(load(VC), """
      const r = fitsKind("line", {filters: []});
      r.controls = [{type: "slider", column: "quarter"}];
      const s = buildSpec(r);
      [new Set(s.variants["0"].rows.map(x => x.t)).size, new Set(s.variants["4"].rows.map(x => x.t)).size]
    """)
    assert out == [1, 5]


def test_switch_between_two_value_columns():
    out = js(load(ADOPTION), """
      const r = fitsKind("bar", {filters: []});
      r.controls = [{type: "switch", options: [
        {label: "All firms", ops: [{op: "roles", v: "ai_use_pct_all_firms"}]},
        {label: "Large firms", ops: [{op: "roles", v: "ai_use_pct_large_firms"}], set: {yLabel: "Large firms (%)"}}]}];
      const s = buildSpec(r);
      const a = s.variants["0"], b = s.variants["1"];
      ({initial: s.controls[0].initial, labels: s.controls[0].options, aMax: Math.max(...a.rows.map(x => x.v)), bMax: Math.max(...b.rows.map(x => x.v)),
        bLabel: b.yLabel, aSame: JSON.stringify(a.rows) === JSON.stringify(s.rows)})
    """, ADOPTION_JEV)
    assert out["labels"] == ["All firms", "Large firms"]
    assert out["initial"] == 0
    assert out["aSame"] is True
    assert out["bMax"] > out["aMax"]
    assert out["bLabel"] == "Large firms (%)"


def test_initial_follows_the_drawn_option():
    out = js(load(ADOPTION), """
      const r = fitsKind("bar", {filters: []});
      r.controls = [{type: "select", style: "buttons", options: [
        {label: "Large", ops: [{op: "roles", v: "ai_use_pct_large_firms"}]},
        {label: "All", ops: [{op: "roles", v: "ai_use_pct_all_firms"}]}]}];
      buildSpec(r).controls[0].initial
    """, ADOPTION_JEV)
    assert out == 1


def test_checkbox_and_legend_need_no_versions():
    out = js(load(VC), """
      const r = fitsKind("line", {filters: []});
      r.controls = [{type: "legend"}, {type: "checkbox", label: "Technologies"}];
      const s = buildSpec(r);
      ({types: s.controls.map(c => c.type), field: s.controls[1].field, items: s.controls[1].items.length, variants: s.variants || null})
    """)
    assert out == {"types": ["legend", "checkbox"], "field": "series", "items": 6, "variants": None}


def test_select_on_a_category_column_filters_each_value():
    out = js(load(VC), """
      const r = fitsKind("line", {filters: []});
      r.controls = [{type: "select", column: "technology"}];
      const s = buildSpec(r);
      ({opts: s.controls[0].options.length, style: s.controls[0].style, one: new Set(s.variants["2"].rows.map(x => x.series)).size})
    """)
    assert out == {"opts": 6, "style": "dropdown", "one": 1}


def test_too_many_versions_is_refused():
    out = js(load(VC), """
      const r = fitsKind("bar", {filters: []});
      let msg = "";
      try { applyChange(r, {set: {controls: [{type: "slider", column: "quarter"}, {type: "select", column: "technology"}]}}); } catch (e) { msg = e.message; }
      msg
    """)
    assert "120 versions" in out


def test_controls_survive_a_chat_change_and_reach_the_ai():
    out = js(load(VC), """
      let r = fitsKind("bar", {filters: []});
      r = applyChange(r, {set: {controls: [{type: "slider", column: "quarter"}]}});
      r = applyChange(r, {set: {title: "VC by technology"}});
      ({controls: r.controls, ai: recipeForAI(r).layout.controls})
    """)
    assert out["controls"] == [{"type": "slider", "column": "quarter"}]
    assert out["ai"] == out["controls"]


def test_year_slider_chip_is_offered_once():
    out = js(load(VC), """
      state.recipe = fitsKind("bar", {filters: []}); state.spec = buildSpec(state.recipe);
      const first = controlChip(state.recipe, state.spec);
      state.recipe = applyChange(state.recipe, first.change); state.spec = buildSpec(state.recipe);
      ({text: first.text, after: controlChip(state.recipe, state.spec)})
    """)
    assert out == {"text": "Add a time slider", "after": None}


def test_every_chart_is_franri_with_no_logo():
    out = js(load(ADOPTION), """
      const calls = [];
      globalThis.fetch = (p, o) => { calls.push(String(p)); return Promise.reject(new Error("offline")); };
      state.recipe = fitsKind("bar", {filters: []});
      const spec = buildSpec(state.recipe);
      ({style: spec.style, calls})
    """, ADOPTION_JEV)
    assert out == {"style": "franri", "calls": []}


def test_logo_stays_off_and_never_counts_as_missed():
    out = js(load(ADOPTION), """
      const r = applyChange(fitsKind("bar", {filters: []}), {set: {logo: {show: true, pos: "top-left"}}});
      ({logo: buildSpec(r).logo, missed: missedFields({logo: {show: true}, title: "x"}, {used: ["title"]})})
    """, ADOPTION_JEV)
    assert out["missed"] == []
    theme = (ROOT / "web" / "franri-theme.js").read_text()
    assert "logo: null," in theme and "spec.logo" not in (ROOT / "web" / "app.js").read_text()
