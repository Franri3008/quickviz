import json
import re
from pathlib import Path

import pytest

from app.capabilities import CAPS, honoured, unsupported
from app.viz_chat import KINDS, SpecEdits

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "web" / "charts.js").read_text()
FIELDS = set(SpecEdits.model_fields)
NUM = {"decimals", "thousands", "decimalMark", "numberStyle"}
REF = re.compile(r"\b(?:C\.spec|C\.raw|spec|s)\.(\w+)")
CALL = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
MARK = re.compile(r"\bmark\(\"(\w+)\"\)")


def _helpers():
    out, lines = {}, SRC.split("\n")
    rx = re.compile(r"^  (?:async )?(?:function (\w+)\(|const (\w+) = )")
    tops = [i for i, ln in enumerate(lines) if re.match(r"^  \S", ln)] + [len(lines)]
    for i, ln in enumerate(lines):
        m = rx.match(ln)
        if m:
            end = next(t for t in tops if t > i)
            out[m.group(1) or m.group(2)] = "\n".join(lines[i:end])
    return out


def _renderers():
    block = SRC[SRC.index("  const R = {"):]
    block = block[:block.index("\n  };\n")]
    parts = re.split(r"\n    (\w+)\(C\) \{\n", block)
    return dict(zip(parts[1::2], parts[2::2]))


HELPERS = _helpers()
RENDERERS = _renderers()


def _clean(body):
    return body.replace("legend(C, [], null)", "")


def _reach(body):
    seen, todo, text = set(), [body], []
    while todo:
        b = _clean(todo.pop())
        text.append(b)
        for name in CALL.findall(b):
            if name in HELPERS and name not in seen and name not in ("render", "rerender", "redrawWaiting"):
                seen.add(name)
                todo.append(HELPERS[name])
    return seen, "\n".join(text)


def _evidence(body):
    called, text = _reach(body)
    found = {f for f in REF.findall(text) if f in FIELDS} | {f for f in MARK.findall(text) if f in FIELDS}
    if called & {"short", "full"}:
        found |= NUM
    if "nt" in called:
        found.add("ticks")
    if "vScale" in called:
        found -= {"valueLog", "xMin", "xMax", "xLog"} - set(REF.findall(_clean(body)))
        calls = re.findall(r"vScale\(C,[^;]*", body)
        xs, vs = [c for c in calls if 'axis: "x"' in c], [c for c in calls if 'axis: "x"' not in c]
        if xs:
            found |= {"xMin", "xMax"}
        if any("noLog" not in c for c in xs):
            found.add("xLog")
        if any("noLog" not in c for c in vs):
            found.add("valueLog")
    found.discard("textHalo")
    if 'append("text")' in text and "textHalo" in HELPERS["finish"]:
        found.add("textHalo")
    return found


def test_every_kind_has_a_row():
    assert set(CAPS["kinds"]) == set(KINDS) == set(RENDERERS)


def test_every_field_is_known_and_labelled():
    listed = set(CAPS["always"]) | set(CAPS["common"]) | {f for v in CAPS["kinds"].values() for f in v}
    assert listed <= FIELDS
    assert FIELDS - listed == set()
    for f in FIELDS - set(CAPS["always"]):
        assert CAPS["labels"].get(f), f


@pytest.mark.parametrize("kind", KINDS)
def test_renderer_honours_what_the_table_claims(kind):
    found = _evidence(RENDERERS[kind])
    missing = sorted(set(CAPS["kinds"][kind]) - found)
    assert not missing, f"charts.js {kind} no longer reads {missing}, but web/capabilities.json says it does"


@pytest.mark.parametrize("kind", KINDS)
def test_table_lists_what_the_renderer_reads(kind):
    found = _evidence(RENDERERS[kind]) - set(CAPS["common"]) - set(CAPS["always"])
    extra = sorted(found - set(CAPS["kinds"][kind]) - {"rows", "geo", "sourceUrl"})
    allowed = {"heatmap": {"yLabel"}, "map": {"xLabel", "yLabel"}}
    extra = [f for f in extra if f not in allowed.get(kind, set())]
    assert not extra, f"charts.js {kind} reads {extra}, add them to web/capabilities.json or stop reading them"


def test_common_fields_are_applied_for_every_kind():
    body = HELPERS["render"] + HELPERS["header"] + HELPERS["drawFoot"] + HELPERS["finish"] + HELPERS["noteLines"]
    found = _evidence(body) | set(re.findall(r"\bspec\.(\w+)", HELPERS["render"]))
    assert set(CAPS["common"]) - found == set()


def test_treemap_legend_is_drawn_from_the_legend_field():
    body = RENDERERS["treemap"]
    assert 'legend(C, spec.legend === "on"' in body


def test_legend_helper_reads_nothing_when_there_are_no_items():
    body = HELPERS["legend"]
    assert body.index("if (!items.length)") < body.index("C.spec.legend")


def test_frame_reports_the_fields_it_used():
    runtime = (ROOT / "web" / "frame-runtime.js").read_text()
    host = (ROOT / "web" / "frame-host.js").read_text()
    assert "used: Array.isArray(st.used)" in runtime
    assert "used: Array.isArray(m.used)" in host
    assert "st.used = C.blank ? null : [...used]" in SRC


def test_helpers_agree_with_the_table():
    assert "legend" in honoured("treemap")
    assert "legend" not in honoured("histogram")
    assert unsupported({"legend": "on", "title": "x", "legendPos": None}, "histogram") == ["legend"]
    assert unsupported({"valueLabels": "on"}, "map") == ["valueLabels"]
    assert unsupported({"thousands": "space"}, "bump") == ["thousands"]


def test_json_is_the_one_the_server_loads():
    assert CAPS == json.loads((ROOT / "web" / "capabilities.json").read_text())


from app.viz_chat import MAP_LABELS, build_messages, honest_reply, validate_change  # noqa: E402
from tests.test_patches import COLUMNS, GOOD, fake_chat  # noqa: E402


def test_validate_change_drops_fields_the_kind_does_not_draw():
    out = validate_change({"reply": "Turned the legend on.", "set": {"legend": "on", "legendPos": "top"}}, COLUMNS, [], kind="histogram", caps=True)
    assert out["set"] == {} and out["dropped"] == ["legend", "legendPos"]
    out = validate_change({"reply": "Turned the legend on.", "set": {"legend": "on", "legendPos": "bottom"}}, COLUMNS, [], kind="treemap", caps=True)
    assert out["set"] == {"legend": "on", "legendPos": "bottom"} and "dropped" not in out


def test_new_kind_decides_and_resets_pass():
    out = validate_change({"reply": "x", "set": {"kind": "treemap", "tickAngle": 30, "legendPos": None}}, COLUMNS, [], kind="bar", caps=True)
    assert out["set"] == {"kind": "treemap", "legendPos": None} and out["dropped"] == ["tickAngle"]


def test_map_labels_keep_their_own_reply():
    out = validate_change({"reply": "Labels on.", "set": {"valueLabels": "on"}}, COLUMNS, [], kind="map", caps=True)
    assert out["reply"] == MAP_LABELS and "dropped" not in out


def test_honest_reply_says_what_did_not_change():
    assert honest_reply({"reply": "Done", "set": {}, "ops": []}, ["thousands"], "bump") == "A ranking chart cannot show thousands separator, so that part did not change."
    assert honest_reply({"reply": "Made it bigger.", "set": {"fontSize": "large"}, "ops": []}, ["legend"], "sankey").startswith("A flow chart cannot show legend")


def test_prompt_gets_the_fields_of_the_current_kind():
    msgs = build_messages("legend", {"kind": "treemap"}, COLUMNS, [], [], [], [])
    assert '"fields_this_chart_draws"' in msgs[-1]["content"] and '"legendPos"' in msgs[-1]["content"]
    assert "fields_this_chart_draws" in msgs[0]["content"]


CHAT = {"message": "Add a legend at the top", "recipe": {"kind": "histogram", "roles": {}}, "columns": COLUMNS, "chart_names": ["Belgium", "Spain"]}


def test_chat_asks_again_then_tells_the_truth(client, monkeypatch):
    c = client
    claim = {"reply": "Added a legend at the top.", "set": {"legend": "on", "legendPos": "top"}}
    sent = fake_chat(monkeypatch, [claim, claim])
    r = c.post("/api/viz/chat", json=CHAT)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["tries"] == 2 and j["set"] == {}
    assert "do nothing on a histogram" in sent[1]["messages"][-1]["content"]
    assert j["reply"] == "A histogram cannot show legend or legend position, so that part did not change."


def test_chat_takes_the_patch_on_the_second_try(client, monkeypatch):
    c = client
    fake_chat(monkeypatch, [{"reply": "Added a legend.", "set": {"legend": "on"}}, {"reply": "Drew a small legend above the bars.", "patch": {"code": GOOD}}])
    j = c.post("/api/viz/chat", json=CHAT).json()
    assert j["patch"]["code"] == GOOD and j["reply"] == "Drew a small legend above the bars."


def _app(code):
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("needs node")
    caps = json.dumps(CAPS)
    r = subprocess.run(["node", str(ROOT / "tests" / "app_harness.js")], input=f"CAPS = {caps};\n" + code, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_client_flags_a_field_the_frame_did_not_use():
    out = _app('missedFields({legend: "on", legendPos: "top", title: "T", colors: {}, valueMin: null, kind: "treemap"}, {used: ["title", "kind"]})')
    assert out == ["legend", "legendPos"]
    assert _app('missedFields({legend: "on"}, {superseded: true})') == []
    assert _app('missedFields({legend: "on"}, {used: null})') == []


def test_client_correction_reads_plainly():
    assert _app('sayMissed(["legend", "legendPos"], "histogram", false)') == "The legend and legend position did not show on this histogram, so that part did not change."
    assert _app('sayMissed(["thousands"], "bump", true)').endswith("The rest of the change was applied.")


def test_stacked_bar_takes_orientation_and_the_prompt_says_so():
    assert "orientation" in CAPS["kinds"]["stacked_bar"] and "orientation" in honoured("stacked_bar")
    assert unsupported({"orientation": "vertical"}, "stacked_bar") == []
    from app.viz_chat import SYSTEM
    assert '"horizontal" (bar and stacked bar charts)' in SYSTEM
    assert "The reply may only describe what the fields, ops or patch in this same JSON actually do. Never claim a change that is not in them." in SYSTEM


def _chrome():
    import shutil
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    found = next((p for p in (shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser", "chrome")) if p), None)
    return found or (mac if Path(mac).exists() else None)


def _draw(spec, tmp_path):
    import html
    import subprocess
    chrome = _chrome()
    if not chrome:
        pytest.skip("needs chrome")
    web = (ROOT / "web").as_uri()
    page = tmp_path / "draw.html"
    page.write_text(f"""<!doctype html><html><head><meta charset="utf-8"></head><body><svg id="chart"></svg><pre id="out"></pre>
<script src="{web}/vendor/d3.min.js"></script><script src="{web}/ceps-theme.js"></script><script src="{web}/charts.js"></script>
<script>
const svg = document.getElementById("chart");
QV.render(svg, {json.dumps(spec)}, {{still: true}});
const box = e => ({{x: +e.getAttribute("x"), y: +e.getAttribute("y"), w: +e.getAttribute("width"), h: +e.getAttribute("height")}});
const ticks = sel => [...svg.querySelectorAll(sel)].map(t => t.textContent);
document.getElementById("out").textContent = JSON.stringify({{orient: svg.__qv.orient, segs: [...svg.querySelectorAll("g.s rect")].map(box),
  labels: ticks("text.seg"), tots: [...svg.querySelectorAll("text.tot")].map(t => ({{x: +t.getAttribute("x"), y: +t.getAttribute("y"), text: t.textContent}})),
  ticks: [...svg.querySelectorAll(".qv-plot .axis")].map(a => [...a.querySelectorAll(".tick text")].map(t => t.textContent)),
  titles: ticks(".qv-axis-title"), tips: [...svg.querySelectorAll("g.s rect title")].length}});
</script></body></html>""")
    r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--allow-file-access-from-files", "--dump-dom",
                        "--virtual-time-budget=3000", page.as_uri()], capture_output=True, text=True, timeout=60)
    m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
    assert m and m.group(1), r.stderr[-500:]
    return json.loads(html.unescape(m.group(1)))


FUEL = [{"cat": str(y), "series": s, "v": v + i} for i, y in enumerate(range(2010, 2016)) for s, v in (("LNG", 20), ("Oil", 35), ("Coal", 15), ("Nuclear", 10))]


def test_vertical_stacked_bar_draws_columns(tmp_path):
    out = _draw({"kind": "stacked_bar", "orientation": "vertical", "title": "Fuel mix", "xLabel": "Year", "yLabel": "Share of total", "rows": FUEL}, tmp_path)
    segs = out["segs"]
    assert out["orient"] == "vertical" and len(segs) == 24 and out["tips"] == 24
    assert len({round(s["w"], 3) for s in segs}) == 1 and len({round(s["x"], 3) for s in segs}) == 6
    for col in {round(s["x"], 3) for s in segs}:
        mine = sorted((s for s in segs if round(s["x"], 3) == col), key=lambda s: s["y"])
        assert all(abs(a["y"] + a["h"] - b["y"]) < 0.01 for a, b in zip(mine, mine[1:]))
    assert ["2010", "2011", "2012", "2013", "2014", "2015"] in out["ticks"]
    assert any(t and t[0] == "0%" and t[-1] == "100%" for t in out["ticks"])
    assert out["titles"] == ["Share of total", "Year"] and out["labels"] and not out["tots"]


def test_vertical_absolute_stack_puts_totals_above_columns(tmp_path):
    out = _draw({"kind": "stacked_bar", "orientation": "vertical", "stack": "absolute", "rows": FUEL}, tmp_path)
    assert len(out["tots"]) == 6
    for t in out["tots"]:
        top = min(s["y"] for s in out["segs"] if abs(s["x"] + s["w"] / 2 - t["x"]) < 0.01)
        assert t["y"] < top


def test_auto_stacked_bar_stays_horizontal(tmp_path):
    for orientation in (None, "auto"):
        spec = {"kind": "stacked_bar", "rows": FUEL, **({"orientation": orientation} if orientation else {})}
        out = _draw(spec, tmp_path)
        segs = out["segs"]
        assert out["orient"] == "horizontal"
        assert len({round(s["h"], 3) for s in segs}) == 1 and len({round(s["y"], 3) for s in segs}) == 6
