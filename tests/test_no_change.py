import json
import shutil

import pytest

from app.viz_chat import build_messages
from tests.test_app_logic import ADOPTION, ADOPTION_JEV, js, load
from tests.test_patches import CHAT, COLUMNS, GOOD, fake_chat

node = pytest.mark.skipif(not shutil.which("node"), reason="needs node")

SETUP = """
state.recipe = fitsKind("bar", {filters: []});
render();
state.chat = []; state.undo = [];
const sent = [];
let sigCalls = 0;
globalThis.__replies = [];
api = async (path, opts) => {
  if (path !== "/api/viz/chat") return {};
  sent.push(opts.json);
  return globalThis.__replies[Math.min(sent.length - 1, globalThis.__replies.length - 1)];
};
"""


def run(sig, replies, tail="({texts: state.chat.map(m => m.text), applied: state.chat.map(m => !!m.applied), undo: state.undo.length, sent: sent.length,"
        " noEffect: sent.map(b => b.no_effect || null), valueLabels: state.recipe.valueLabels ?? null, patches: (state.recipe.patches || []).length,"
        " pending: state.chat.some(m => m.pending)})"):
    code = SETUP + f"globalThis.__replies = {json.dumps(replies)};\nchart.sig = {sig};\n" + "(async () => { await sendChat('Show the values'); return " + tail + "; })()"
    return js(load(ADOPTION), code, ADOPTION_JEV)


SAME = "async () => { sigCalls++; return 'aaaaaaaaaaaaaaaa:1'; }"
BY_PATCH = "async (spec, patches) => { sigCalls++; return 'aaaaaaaaaaaaaaaa:' + (patches.length + 1); }"
BY_SPEC = "async spec => { sigCalls++; return 'aaaaaaaaaaaaaaaa:' + JSON.stringify(spec).length; }"


@node
def test_a_change_that_draws_the_same_chart_asks_again_then_says_nothing_changed():
    out = run(SAME, [{"reply": "Turned on value labels.", "set": {"valueLabels": "on"}, "ops": []},
                     {"reply": "Value labels are now on.", "set": {"valueLabels": "on"}, "ops": []}])
    assert out["sent"] == 2
    assert out["noEffect"][0] is None
    ne = out["noEffect"][1]
    assert ne["change"]["set"] == {"valueLabels": "on"}
    assert "identical" in ne["detail"] and "valueLabels" in ne["detail"]
    assert out["texts"] == ["Show the values", "The chart did not change, so nothing was applied."]
    assert out["applied"] == [False, False]
    assert out["undo"] == 0
    assert out["valueLabels"] is None
    assert not out["pending"]


@node
def test_the_follow_up_patch_is_kept_when_it_changes_the_chart():
    out = run(BY_PATCH, [{"reply": "Turned on value labels.", "set": {"valueLabels": "on"}, "ops": []},
                         {"reply": "Wrote the share inside each bar.", "set": {}, "ops": [], "patch": {"code": "svg.attr('a', 1)", "note": "shares"}}])
    assert out["sent"] == 2
    assert out["texts"][-1] == "Wrote the share inside each bar."
    assert out["patches"] == 1
    assert out["undo"] == 1
    assert out["valueLabels"] is None


@node
def test_a_follow_up_with_no_change_also_ends_in_the_plain_line():
    out = run(SAME, [{"reply": "Turned on value labels.", "set": {"valueLabels": "on"}, "ops": []},
                     {"reply": "They already show.", "set": {}, "ops": []}])
    assert out["texts"][-1] == "The chart did not change, so nothing was applied."
    assert out["undo"] == 0


@node
def test_a_visible_change_keeps_the_reply_and_asks_nothing_more():
    out = run(BY_SPEC, [{"reply": "Turned on value labels.", "set": {"valueLabels": "on"}, "ops": []}])
    assert out["sent"] == 1
    assert out["texts"][-1] == "Turned on value labels."
    assert out["undo"] == 1
    assert out["valueLabels"] == "on"


@node
def test_no_signature_means_no_check():
    out = run("async () => null", [{"reply": "Turned on value labels.", "set": {"valueLabels": "on"}, "ops": []}])
    assert out["sent"] == 1
    assert out["texts"][-1] == "Turned on value labels."
    assert out["undo"] == 1


@node
def test_a_patch_that_changes_nothing_is_not_kept_and_not_retried():
    out = run(SAME, [{"reply": "Added leader lines.", "set": {}, "ops": [], "patch": {"code": "svg.attr('a', 1)", "note": "x"}}])
    assert out["sent"] == 1
    assert out["texts"][-1] == "The chart did not change, so nothing was applied."
    assert out["patches"] == 0
    assert out["undo"] == 0


@node
def test_tabs_resize_and_controls_never_take_a_signature():
    code = SETUP + """
chart.sig = async () => { sigCalls++; return 'aaaaaaaaaaaaaaaa:1'; };
(async () => {
  localChange({set: {kind: "donut"}}, "Switched to donut chart");
  localChange({set: {legendPos: "bottom"}}, "Legend at the bottom");
  await drawChart({fitH: 600});
  await drawChart({fitH: null});
  await render();
  return {sigCalls, undo: state.undo.length};
})()
"""
    out = js(load(ADOPTION), code, ADOPTION_JEV)
    assert out == {"sigCalls": 0, "undo": 2}


def test_no_effect_goes_back_to_the_model():
    msgs = build_messages("show the % in each slice", {"kind": "donut"}, COLUMNS, [], [], [], [], outline="x",
                          no_effect={"change": {"reply": "Turned on labels.", "set": {"valueLabels": "on"}, "ops": []},
                                     "detail": "valueLabels went from auto to \"on\", and the renderer read it but drew exactly the same chart"})
    assert json.loads(msgs[-2]["content"])["set"] == {"valueLabels": "on"}
    assert msgs[-2]["role"] == "assistant"
    assert "no visible effect" in msgs[-1]["content"] and "patch" in msgs[-1]["content"]
    assert "drew exactly the same chart" in msgs[-1]["content"]


def test_chat_endpoint_accepts_no_effect(client, monkeypatch):
    c = client
    sent = fake_chat(monkeypatch, [{"reply": "Drew it.", "patch": {"code": GOOD, "note": "x"}}])
    r = c.post("/api/viz/chat", json={**CHAT, "no_effect": {"change": {"set": {"valueLabels": "on"}}, "detail": "came out identical"}})
    assert r.status_code == 200, r.text
    assert "came out identical" in sent[0]["messages"][-1]["content"]
    assert r.json()["patch"]["code"]
