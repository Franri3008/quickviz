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
