import shutil

import pytest

from tests.test_app_logic import ADOPTION, ADOPTION_JEV, js, load

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def test_patches_stack_in_order_and_keep_through_spec_edits():
    out = js(load(ADOPTION), """
      let r = fitsKind("scatter", {filters: []});
      r = applyChange(r, {patch: {code: "svg.attr('a', 1)", note: "first"}});
      r = applyChange(r, {set: {title: "New"}, patch: {code: "svg.attr('b', 2)", note: "second"}});
      r = applyChange(r, {set: {legendPos: "top"}});
      ({notes: r.patches.map(p => p.note), title: r.title, ai: recipeForAI(r).patches})
    """, ADOPTION_JEV)
    assert out["notes"] == ["first", "second"]
    assert out["title"] == "New"
    assert out["ai"] == ["first", "second"]


def test_switching_kind_drops_every_patch():
    out = js(load(ADOPTION), """
      let r = fitsKind("scatter", {filters: []});
      r = applyChange(r, {patch: {code: "svg.attr('a', 1)", note: "first"}});
      const bar = applyChange(r, {set: {kind: "bar"}});
      [r.patches.length, bar.patches === undefined, recipeForAI(bar).patches === undefined]
    """, ADOPTION_JEV)
    assert out == [1, True, True]


def test_kind_switch_adds_one_chat_line_and_undo_brings_patches_back():
    out = js(load(ADOPTION), """
      state.recipe = applyChange(fitsKind("scatter", {filters: []}), {patch: {code: "svg.attr('a', 1)", note: "first"}});
      state.chat = [];
      localChange({set: {kind: "bar"}}, "Switched to bar chart");
      const lines = state.chat.map(m => m.text);
      undo();
      ({lines, back: state.recipe.patches.map(p => p.note), kind: state.recipe.kind})
    """, ADOPTION_JEV)
    assert out["lines"] == ["Switched to bar chart", "The drawn change was removed with the chart type switch."]
    assert out["back"] == ["first"]
    assert out["kind"] == "scatter"


def test_undo_removes_the_latest_patch():
    out = js(load(ADOPTION), """
      state.recipe = fitsKind("scatter", {filters: []});
      state.chat = [];
      localChange({patch: {code: "svg.attr('a', 1)", note: "first"}}, "Drew it");
      const before = state.recipe.patches.length;
      undo();
      [before, (state.recipe.patches || []).length]
    """, ADOPTION_JEV)
    assert out == [1, 0]


def test_mockup_data_is_marked_once_through_draws_kind_switches_and_exports():
    from tests.test_app_logic import js

    out = js(None, """
      const spec = QV.mock("bar", {title: "Coffee", categories: ["Brazil", "Vietnam", "Colombia"], range: [1, 40]}, "s");
      const table = QV.mockTable(spec);
      showData(toData(table));
      const seen = [];
      chart.render = (s, o) => { seen.push(o.patches.map(p => p.note)); return Promise.resolve({errors: []}); };
      state.decide = null;
      state.recipe = fitsKind("bar", {filters: [], roles: table.described.roles, source: table.source_hint, note: table.notes[0]});
      state.recipe.patches = [{code: "svg;", note: "mine"}];
      state.spec = buildSpec(state.recipe);
      drawChart({});
      state.recipe = applyChange(state.recipe, {set: {kind: "treemap"}});
      state.spec = buildSpec(state.recipe);
      drawChart({});
      const s = buildSpec(state.recipe);
      const chatted = buildSpec(applyChange(state.recipe, {set: {source: "Eurostat", note: "My note"}}));
      const mocked = {seen, file: fileName(), stored: JSON.stringify(state.recipe).includes("Mockup data tag"), source: s.source, note: s.note,
        html: withMock(state.recipe.patches).map(p => p.note), restart: !!$("describe"), chatted: [chatted.source, chatted.note],
        preview: [spec.source, spec.note, QV.mockTable(spec).notes]};
      state.data = {...state.data, mock: false};
      ({...mocked, real: withMock([{code: "svg;", note: "mine"}]).map(p => p.note), realFile: fileName().startsWith("mockup-")})
    """)
    assert out["seen"] == [["mine"], []]
    assert out["file"].startswith("mockup-"), out["file"]
    assert out["stored"] is False
    assert out["source"] == "Mockup data, not real numbers" and out["note"] == ""
    assert out["html"] == []
    assert out["chatted"] == ["Mockup data, not real numbers", "My note"]
    assert out["preview"] == ["Mockup data, not real numbers", "", []]
    assert out["real"] == ["mine"] and out["realFile"] is False


def test_described_mockup_opens_step_two_without_asking_jev():
    from tests.test_app_logic import js

    out = js(None, """
      const calls = [];
      globalThis.fetch = p => { calls.push(String(p)); return Promise.reject(new Error("offline")); };
      const table = QV.mockTable(QV.mock("line", {title: "Coffee prices", series: ["Arabica", "Robusta"], times: ["2020", "2021", "2022", "2023"]}, "s"));
      showData(toData(table));
      autoChart().then(() => ({kind: state.recipe.kind, title: state.spec.title, calls, mock: state.data.mock}))
    """)
    assert out == {"kind": "line", "title": "Coffee prices", "calls": [], "mock": True}
