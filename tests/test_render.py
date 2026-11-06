import asyncio
import base64

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
