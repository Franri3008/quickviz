import shutil

import pytest

from tests.test_app_logic import ADOPTION, ADOPTION_JEV, js, load

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")

SETUP = """
  const calls = [];
  globalThis.fetch = p => { calls.push(String(p)); return Promise.reject(new Error("offline")); };
  const puts = [], drops = [];
  globalThis.QVKeep = {put: (o, p) => { puts.push([o, Object.keys(p).sort()]); return Promise.resolve(); },
    drop: o => { drops.push(o); return Promise.resolve(); }, get: () => Promise.resolve(null), prune: () => Promise.resolve()};
  state.keepId = "browser-1";
  state.recipe = withAutoControls(fitsKind("bar", {filters: []}));
  state.auto = "done"; state.opts = ["bar", "donut"]; state.reached = 3; state.view = 3;
  localChange({set: {kind: "donut"}, autoTime: true}, "Switched to donut chart");
  state.chat.push({role: "user", text: "only Belgium"}, {role: "assistant", text: "Done.", applied: true});
  const snap = JSON.parse(JSON.stringify(snapshot()));
  const fresh = () => { resetChart(); state.data = null; state.view = 1; state.reached = 1; keepBox.data = null; keepBox.id = null; calls.length = 0; };
"""


def test_restore_brings_back_chart_chat_and_step_without_calls():
    out = js(load(ADOPTION), SETUP + """
      const before = {kind: state.recipe.kind, chat: state.chat.map(m => m.text), undo: state.undo.length};
      fresh();
      const ok = restoreFrom(snap.ui, snap.data);
      ({ok, before, kind: state.recipe && state.recipe.kind, chat: state.chat.map(m => m.text), undo: state.undo.length,
        view: state.view, reached: state.reached, auto: state.auto, rows: state.data.rows.length, spec: !!state.spec, calls})
    """, ADOPTION_JEV)
    assert out["ok"] is True
    assert out["kind"] == "donut" == out["before"]["kind"]
    assert out["chat"] == out["before"]["chat"]
    assert out["undo"] == out["before"]["undo"] == 1
    assert out["view"] == 3 and out["reached"] == 3 and out["auto"] == "done"
    assert out["rows"] > 0 and out["spec"] is True
    assert out["calls"] == []


def test_old_wrong_or_broken_saves_are_ignored():
    out = js(load(ADOPTION), SETUP + """
      const tries = {
        version: [{...snap.ui, v: 0}, snap.data],
        old: [{...snap.ui, at: Date.now() - 8 * 864e5}, snap.data],
        other: [{...snap.ui, id: "x"}, snap.data],
        broken: [{...snap.ui, chat: "nope"}, snap.data],
        nodata: [snap.ui, {...snap.data, data: null}],
        empty: [null, null],
      };
      const res = {};
      for (const [k, [u, d]] of Object.entries(tries)) { fresh(); res[k] = [restoreFrom(u, d), state.data === null, state.chat.length]; }
      res
    """, ADOPTION_JEV)
    for k, v in out.items():
        assert v == [False, True, 0], k


def test_saves_data_once_and_skips_busy_and_clears_on_start_over():
    out = js(load(ADOPTION), SETUP + """
      keepBox.data = null; puts.length = 0;
      keepNow(); keepNow();
      state.busy = true; keepNow(); state.busy = false;
      const wrote = puts.map(p => p[1]);
      startOver();
      ({wrote, drops, timer: !!keepBox.timer, pending: snapshot().ui.chat.some(m => m.pending)})
    """, ADOPTION_JEV)
    assert out["wrote"] == [["data", "ui"], ["ui"]]
    assert out["drops"] and out["drops"][0] == "browser-1"
    assert out["timer"] is False


def test_pending_bubble_and_unfinished_pick_are_not_saved():
    out = js(load(ADOPTION), SETUP + """
      state.chat.push({role: "assistant", text: "", pending: true});
      state.auto = "running";
      const s = snapshot().ui;
      ({pending: s.chat.some(m => m.pending), view: s.view, reached: s.reached, auto: s.auto})
    """, ADOPTION_JEV)
    assert out == {"pending": False, "view": 1, "reached": 1, "auto": None}


def test_other_readings_after_reload_shows_load_it_again():
    out = js(load(ADOPTION), SETUP + """
      const els = {};
      document.getElementById = id => els[id] || (els[id] = __stub());
      globalThis.fetch = p => { calls.push(String(p)); return Promise.resolve({status: 409, ok: false,
        json: () => Promise.resolve({detail: {reason: "gone", message: "The file is no longer on the server. Load it again."}})}); };
      fresh();
      restoreFrom(snap.ui, {...snap.data, data: {...snap.data.data, file_id: "abc"}});
      const kind = state.recipe.kind;
      rereadWith({header_row: 0}, -1).then(() => ({err: els.err.textContent, kind: state.recipe && state.recipe.kind, before: kind,
        view: state.view, calls}))
    """, ADOPTION_JEV)
    assert out["err"] == "The file is no longer on the server. Load it again."
    assert out["kind"] == out["before"] == "donut"
    assert out["view"] == 3
    assert out["calls"] == ["/api/viz/reread"]
