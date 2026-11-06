import asyncio
import base64
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import render
from conftest import new_client, sign_in

BAR = {"kind": "bar", "title": "AI adoption", "rows": [{"cat": c, "v": v} for c, v in [("Denmark", 27.6), ("Sweden", 25.1), ("Belgium", 24.7)]]}
MAP = {"kind": "map", "title": "AI use", "rows": [{"cat": c, "v": v} for c, v in [("Germany", 20), ("France", 10), ("Japan", 14)]]}
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def fake_render(monkeypatch):
    seen = []

    async def fake(spec, width, scale):
        seen.append((spec, width, scale))
        return {"png": PNG + b"x", "html": "<!doctype html><svg></svg>", "width": width, "height": 520, "geo": None, "ms": 5}

    monkeypatch.setattr(render.RENDERER, "render", fake)
    monkeypatch.setattr(render, "LIMIT", render.RateLimit({"render": 3}))
    return seen


def test_render_needs_sign_in(fake_render):
    with new_client() as c:
        r = c.post("/api/render", json={"spec": BAR})
    assert r.status_code == 401 and not fake_render


def test_render_returns_base64_png_and_html(fake_render):
    with new_client() as c:
        sign_in(c, styles="franri,aiw")
        r = c.post("/api/render", json={"spec": {**BAR, "patches": [{"code": "x"}]}, "style": "aiw", "width": 600})
        assert c.post("/api/render", json={"spec": BAR, "style": "ceps"}).status_code == 403
    assert r.status_code == 200
    out = r.json()
    assert base64.b64decode(out["png"]).startswith(PNG) and out["html"].startswith("<!doctype html>")
    assert out["style"] == "aiw" and out["width"] == 600 and out["scale"] == 2
    spec, width, scale = fake_render[0]
    assert spec["style"] == "aiw" and "patches" not in spec and width == 600


def test_render_rejects_bad_input_and_rate_limits(fake_render):
    with new_client() as c:
        sign_in(c)
        assert c.post("/api/render", json={"spec": {"kind": "bar"}}).status_code == 422
        r = c.post("/api/render", json={"spec": BAR, "style": "nope"})
        assert r.status_code == 403 and r.json()["detail"]["reason"] == "style"
        assert c.post("/api/render", json={"spec": BAR, "scale": 9}).status_code == 422
        codes = [c.post("/api/render", json={"spec": BAR}).status_code for _ in range(3)]
    assert codes[0] == 200 and codes[-1] == 429


def test_spec_defaults_to_house_style_and_assets_stay_inside_web():
    assert render.clean_spec(BAR, None)["style"] == "franri"
    assert render.clean_spec({**BAR, "style": "ceps"}, None)["style"] == "ceps"
    assert render.asset("/charts.js") and render.asset("/export/charts.min.js")
    for bad in ("/../app/config.py", "/app.js", "/vendor/../../.env", "/fonts/../index.html"):
        assert render.asset(bad) is None


def _chrome():
    try:
        return render.chrome_path()
    except render.RenderError:
        return None


@pytest.mark.skipif(_chrome() is None, reason="needs chromium")
def test_server_draws_each_style_and_a_map():
    async def run():
        try:
            outs = [await render.render_chart(BAR, s) for s in ("franri", "aiw", "ceps")]
            outs.append(await render.render_chart(MAP, "ceps", width=600, scale=1))
            return outs
        finally:
            await render.RENDERER.stop()

    outs = asyncio.run(run())
    for out, style in zip(outs, ("franri", "aiw", "ceps", "ceps")):
        assert out["png"].startswith(PNG) and out["style"] == style
        assert out["html"].startswith("<!doctype html>") and "QV.render" in out["html"]
    assert outs[0]["width"] == 760 and int.from_bytes(outs[0]["png"][16:20], "big") == 1520
    assert outs[3]["geo"] == "world" and int.from_bytes(outs[3]["png"][16:20], "big") == 600
    assert len({o["png"] for o in outs[:3]}) == 3


FD_SCRIPT = """
import fcntl, os, subprocess, sys
from app import render
mode = sys.argv[1]
if mode == "high":
    junk = [os.open(os.devnull, os.O_RDONLY) for _ in range(12)]
    to_r, to_w = os.pipe()
    from_r, from_w = os.pipe()
    assert min(to_r, to_w, from_r, from_w) > 9
else:
    ar, aw = os.pipe()
    br, bw = os.pipe()
    assert (ar, aw) == (3, 4)
    to_r, to_w, from_r, from_w = (fcntl.fcntl(f, fcntl.F_DUPFD, 20) for f in (ar, aw, br, bw))
    for f in (ar, aw, br, bw):
        os.close(f)
    os.dup2(to_r, 4, inheritable=False)
    os.dup2(from_w, 3, inheritable=False)
    os.close(to_r)
    os.close(from_w)
    to_r, from_w = 4, 3
child = "import os; os.write(4, os.read(3, 100).upper())"
proc = subprocess.Popen([sys.executable, "-c", child], preexec_fn=render.fd_mover(to_r, from_w), pass_fds=(3, 4))
os.close(to_r)
os.close(from_w)
os.write(to_w, b"ping")
os.close(to_w)
print(os.read(from_r, 100).decode(), proc.wait())
"""


@pytest.mark.parametrize("mode", ["high", "swapped"])
def test_pipe_ends_land_on_fd_3_and_4(mode):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root)}
    out = subprocess.run([sys.executable, "-c", FD_SCRIPT, mode], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["PING", "0"]


@pytest.mark.skipif(_chrome() is None, reason="needs chromium")
def test_server_draws_when_pipe_fds_are_above_9():
    junk = [os.open(os.devnull, os.O_RDONLY) for _ in range(12)]

    async def run():
        try:
            out = await render.render_chart(BAR, "franri", scale=1)
            return out, render.RENDERER.browser.err_task is not None
        finally:
            await render.RENDERER.stop()

    try:
        out, logs_stderr = asyncio.run(run())
    finally:
        for fd in junk:
            os.close(fd)
    assert out["png"].startswith(PNG) and logs_stderr
