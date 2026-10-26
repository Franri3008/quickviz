import json
import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from app import llm
from app.viz_chat import PATCH_MAX, SYSTEM, ChangeError, build_messages, check_patch, validate_change

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = [
    {"name": "country", "type": "category", "distinct": 3, "values": ["Spain", "Belgium", "EU27"]},
    {"name": "rate", "type": "number", "distinct": 12, "min": 1.0, "max": 40.0},
]
GOOD = """const dot = svg.selectAll(".qv-plot circle").filter(d => d && d.cat === "Belgium");
const label = svg.selectAll(".qv-plot text").filter(function () { return this.textContent === "Belgium"; });
if (dot.empty() || label.empty()) return;
label.attr("x", +dot.attr("cx") - 9).attr("text-anchor", "end");"""


def examples():
    part = SYSTEM.split("Patch examples (code shown unescaped):", 1)[1]
    blocks = re.split(r'\n"[^\n]*" (?:on a [a-z ]+ )?->\n', "\n" + part)
    return [b.strip("\n") for b in blocks if b.strip()]


def test_the_prompt_examples_pass_the_check():
    ex = examples()
    assert len(ex) == 4
    for code in ex:
        assert check_patch(code) == code.strip()


@pytest.mark.parametrize("code", [
    "fetch('https://x.eu')",
    "new XMLHttpRequest()",
    "const s = new WebSocket('wss://x')",
    "import('https://x.eu/a.js')",
    "eval('1')",
    "new Function('return 1')()",
    "Function('return this')()",
    "svg.text(document.cookie)",
    "parent.postMessage('x', '*')",
    "top.location = 'https://x.eu'",
    "const p = parent; p.x = 1",
    "localStorage.setItem('a', 1)",
    "window.open('https://x.eu')",
    "setTimeout(() => 1, 10)",
    "svg.select('rect').transition().attr('x', 1)",
    "d3.json('https://x.eu/a.json')",
    "navigator.sendBeacon('https://x.eu', '1')",
    "[].constructor.constructor('return 1')()",
    "location.href = 'https://x.eu'",
    "const margin = {top: 4}",
])
def test_banned_patch_code(code):
    with pytest.raises(ChangeError):
        check_patch(code)


@pytest.mark.parametrize("code", [
    "svg.selectAll('text').each(function () { const b = this.getBoundingClientRect(); this.parentNode.appendChild(this); return b.top; })",
    "svg.selectAll('text').attr('dominant-baseline', 'text-top')",
    "// move the label to the top\nsvg.select('.qv-title').attr('y', 20)",
    "svg.select('.qv-title').text('Window of time, top 10 by location')",
])
def test_allowed_patch_code(code):
    assert check_patch(code)


def test_patch_too_long():
    with pytest.raises(ChangeError, match="limit is 4096"):
        check_patch("svg;\n" * (PATCH_MAX // 4))


def test_change_carries_patch():
    ch = validate_change({"reply": "Moved the label.", "patch": {"code": GOOD, "note": "Belgium label left"}}, COLUMNS, ["Belgium"])
    assert ch["patch"] == {"code": GOOD, "note": "Belgium label left"}
    assert ch["set"] == {} and ch["ops"] == []


def test_patch_note_defaults_to_reply_and_fences_are_stripped():
    ch = validate_change({"reply": "Added lines.", "patch": {"code": "```js\n" + GOOD + "\n```"}}, COLUMNS, [])
    assert ch["patch"]["note"] == "Added lines."
    assert ch["patch"]["code"] == GOOD


def test_patch_with_kind_change_is_refused():
    with pytest.raises(ChangeError, match="kind change"):
        validate_change({"reply": "x", "set": {"kind": "bar"}, "patch": {"code": GOOD}}, COLUMNS, [])


def test_patch_with_extra_keys_is_refused():
    with pytest.raises(ChangeError):
        validate_change({"reply": "x", "patch": {"code": GOOD, "run": "now"}}, COLUMNS, [])


def test_messages_carry_outline_and_patch_error():
    msgs = build_messages("move it", {"kind": "scatter"}, COLUMNS, [], [], [], [], outline="svg width=760\n  circle x3")
    ctx = json.loads(msgs[-1]["content"].split("\n", 1)[1].rsplit("\n\nRequest:", 1)[0])
    assert ctx["svg_outline"].startswith("svg width=760")
    msgs = build_messages("move it", {"kind": "scatter"}, COLUMNS, [], [], [], [], outline="x", patch_error={"code": GOOD, "error": "dot is null"})
    assert msgs[-2]["role"] == "assistant" and "Belgium" in msgs[-2]["content"]
    assert msgs[-1]["role"] == "user" and "dot is null" in msgs[-1]["content"]


def test_prompt_says_when_to_refuse():
    assert "Refuse only for things outside a flat 2D chart" in SYSTEM
    assert "never with a kind change" in SYSTEM


def fake_chat(monkeypatch, replies):
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        content = replies[min(len(sent) - 1, len(replies) - 1)]
        return httpx.Response(200, json={"id": f"gen-{len(sent)}", "model": body.get("model") or body["models"][0],
                                         "choices": [{"message": {"content": json.dumps(content)}}], "usage": {"cost": 0.0002}})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    return sent


CHAT = {"message": "Put Belgium's label left of the dot", "recipe": {"kind": "scatter", "roles": {}}, "columns": COLUMNS,
        "chart_names": ["Belgium", "Spain"], "outline": "svg width=760 height=520\n  g.qv-plot"}


def test_chat_endpoint_returns_a_patch_and_sends_the_outline(client, monkeypatch):
    c = client
    sent = fake_chat(monkeypatch, [{"reply": "Moved it.", "patch": {"code": GOOD, "note": "Belgium label left"}}])
    r = c.post("/api/viz/chat", json=CHAT)
    assert r.status_code == 200, r.text
    assert r.json()["patch"]["code"] == GOOD
    assert "svg_outline" in sent[0]["messages"][-1]["content"]


def test_chat_endpoint_retries_a_banned_patch(client, monkeypatch):
    c = client
    sent = fake_chat(monkeypatch, [{"reply": "x", "patch": {"code": "fetch('https://x.eu')"}},
                                   {"reply": "Moved it.", "patch": {"code": GOOD}}])
    r = c.post("/api/viz/chat", json=CHAT)
    assert r.status_code == 200, r.text
    assert r.json()["tries"] == 2
    assert "fetch" in sent[1]["messages"][-1]["content"]


def test_chat_endpoint_passes_the_patch_error_back(client, monkeypatch):
    c = client
    sent = fake_chat(monkeypatch, [{"reply": "Fixed.", "patch": {"code": GOOD}}])
    r = c.post("/api/viz/chat", json={**CHAT, "patch_error": {"code": "svg.select('x').node().remove()", "error": "null has no remove"}})
    assert r.status_code == 200, r.text
    assert "null has no remove" in sent[0]["messages"][-1]["content"]



def test_chat_uses_one_model_and_the_charts_have_no_logo(client, monkeypatch):
    sent = fake_chat(monkeypatch, [{"reply": "Added the logo.", "set": {"logo": {"show": True}}}])
    r = client.post("/api/viz/chat", json={**CHAT, "message": "add the logo", "model": "openai/gpt-6-luna", "style": "ceps"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["set"] == {} and j["reply"] == "These charts have no logo, so nothing changed." and j["style"] == "franri"
    assert sent[0]["model"] == "anthropic/claude-haiku-5.5" and "models" not in sent[0]
    system = sent[0]["messages"][0]["content"]
    assert "these charts have no logo" in system and "AI World logo" not in system and "CEPS researcher" not in system

def guard_js():
    src = (ROOT / "web" / "charts.js").read_text()
    start = src.index("  function guardLoops(code) {")
    end = src.index("\n  }\n", start) + 4
    return src[start:end]


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_loop_guard_stops_endless_loops():
    code = guard_js() + """
    const run = c => { const end = Date.now() + 200; const g = () => { if (Date.now() > end) throw new Error("limit"); return true; };
      try { new Function("__qvGuard", '"use strict";\\n' + guardLoops(c))(g); return "ok"; } catch (e) { return e.message; } };
    console.log(JSON.stringify([
      run("while (true) {}"),
      run("for (;;) {}"),
      run("let i = 0; do { i++; } while (i >= 0);"),
      run("for (let i = 0; i < 3; i++) { for (const k of [1, 2]) {} }"),
      run("const s = 'while (true) {}'; let n = 0; for (let i = 0; i < 5; i++) n += i; if (n !== 10) throw new Error('bad');"),
      guardLoops("for (let i = 0; i < n; i++) x(i)"),
    ]));
    """
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out[:3] == ["limit", "limit", "limit"]
    assert out[3] == "ok" and out[4] == "ok"
    assert out[5] == "for (let i = 0; __qvGuard() && ( i < n);  i++) x(i)"


FADE_TICKS = """svg.selectAll(".qv-plot text").filter(function () { return +this.textContent >= 2026; }).attr("opacity", 0.35);"""


def test_prompt_keeps_patches_off_the_axes():
    assert "selects marks only, by these classes: rect.bar, g.s rect, rect.cell, path.area, path.qv-line" in SYSTEM
    assert "A box, band or overlay stays inside the plot box" in SYSTEM
    assert "change that effect and keep it" in SYSTEM


def test_outline_shows_ticks_a_patch_faded(tmp_path):
    from tests.test_viz_look import KOREA, draw_shaded
    spec = {"kind": "stacked_area", "rows": KOREA, "xLabel": "Year", "yLabel": "TWh"}
    plain = draw_shaded(spec, tmp_path)
    out = draw_shaded(spec, tmp_path, [{"code": FADE_TICKS, "note": "fade projection years"}])
    assert "faded" not in plain["outline"]
    line = next(ln for ln in out["outline"].split("\n") if "g.tick x" in ln and "faded" in ln)
    assert '"2026"' in line.split("faded", 1)[1] and '"2016"' not in line.split("faded", 1)[1]
    shaded = draw_shaded({**spec, "shade": [{"from": 2026}]}, tmp_path)
    assert "faded" not in shaded["outline"] and "rect.qv-shade-band" in shaded["outline"]
