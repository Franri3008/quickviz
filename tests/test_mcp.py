import base64
import json
import re

import httpx
import pytest

from app import db, llm, pipeline, render
from app.models import ApiKey, User
from conftest import new_client, sign_in, spend, spent_rows

ROOT = pipeline.WEB_DIR.parent
CSV = (ROOT / "samples" / "MOCK_ai_adoption_eu_countries_2025.csv").read_text()
PNG = b"\x89PNG\r\n\x1a\n"


def role_for(name):
    n = name.lower()
    if re.search(r"pct|share|patent|spend", n):
        return "value"
    if re.search(r"iso|code", n):
        return "ignore"
    return "group" if "group" in n else "name"


def fake_llm(monkeypatch, change=None):
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append((request.url.path, body))
        if request.url.path.endswith("/alpha/decisions"):
            answers = {"kind": {"choice": "bar", "confidence": 0.9, "probabilities": {"bar": 0.9, "dot_range": 0.1}}}
            for k, q in body["questions"].items():
                if k.startswith("col"):
                    col = re.search(r'the column "([^"]+)"', q["instructions"]).group(1)
                    answers[k] = {"choice": role_for(col), "confidence": 0.9}
            return httpx.Response(200, json={"answers": answers, "usage": {"cost": 0.001}, "id": "gen-dec"})
        if body["messages"][0]["content"].startswith("You check a chart"):
            content = {"title": "AI use by EU country, 2025", "unit": "%", "columns": {}, "roles": {}}
        else:
            content = change or {"reply": "Nothing to do."}
        return httpx.Response(200, json={"id": "gen-x", "model": "m", "choices": [{"message": {"content": json.dumps(content)}}],
                                         "usage": {"cost": 0.001}})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    return sent


def make_key(c, name="laptop"):
    r = c.post("/api/keys", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()


def rpc(c, key, method, params=None):
    headers = {"Accept": "application/json, text/event-stream"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}, headers=headers)


def tool(c, key, name, **args):
    r = rpc(c, key, "tools/call", {"name": name, "arguments": args})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def error_of(res):
    assert res["isError"], res
    return res["structuredContent"]["error"]


def test_keys_are_shown_once_stored_hashed_and_revocable():
    with new_client() as c:
        assert c.post("/api/keys", json={"name": "x"}).status_code == 401
        uid = sign_in(c)
        made = make_key(c, "My laptop")
        assert made["key"].startswith("qv_") and made["prefix"] == made["key"][:9] and made["name"] == "My laptop"
        listed = c.get("/api/keys").json()["keys"]
        assert [k["id"] for k in listed] == [made["id"]] and "key" not in listed[0]
        with db.session() as s:
            row = s.get(ApiKey, made["id"])
            assert row.user_id == uid and made["key"] not in (row.digest, row.prefix) and len(row.digest) == 64
        assert rpc(c, made["key"], "tools/list").status_code == 200
        with new_client() as other:
            assert other.get("/api/keys", headers={"Authorization": f"Bearer {made['key']}"}).status_code == 401
        assert c.delete(f"/api/keys/{made['id']}").status_code == 200
        assert rpc(c, made["key"], "tools/list").status_code == 401


def test_someone_else_cannot_revoke_my_key():
    with new_client() as c:
        sign_in(c)
        made = make_key(c)
        sign_in(c, "bo@example.com")
        assert c.delete(f"/api/keys/{made['id']}").status_code == 404


def test_mcp_needs_a_valid_key_of_an_active_account():
    with new_client() as c:
        r = rpc(c, None, "tools/list")
        assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Bearer")
        assert rpc(c, "qv_not-a-real-key", "tools/list").status_code == 401
        uid = sign_in(c)
        key = make_key(c)["key"]
        assert rpc(c, None, "tools/list").status_code == 401
        names = [t["name"] for t in rpc(c, key, "tools/list").json()["result"]["tools"]]
        assert names == ["list_styles", "make_chart", "edit_chart"]
        with db.session() as s, s.begin():
            s.get(User, uid).active = False
        assert rpc(c, key, "tools/list").status_code == 401


def test_mcp_rejects_a_foreign_origin():
    with new_client() as c:
        sign_in(c)
        key = make_key(c)["key"]
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                   headers={"Authorization": f"Bearer {key}", "Origin": "https://evil.example", "Accept": "application/json, text/event-stream"})
        assert r.status_code == 403


def test_list_styles_shows_the_account_styles_and_default():
    with new_client() as c:
        sign_in(c, styles="franri,ceps", chart_style="ceps")
        res = tool(c, make_key(c)["key"], "list_styles")
    assert not res["isError"]
    data = res["structuredContent"]
    assert [s["id"] for s in data["styles"]] == ["franri", "ceps"] and data["default"] == "ceps" and data["credits_left"] == 1000


def test_make_chart_refuses_a_style_the_account_lacks_before_any_ai_call(monkeypatch):
    sent = fake_llm(monkeypatch)
    with new_client() as c:
        sign_in(c)
        err = error_of(tool(c, make_key(c)["key"], "make_chart", data=CSV, style="ceps"))
    assert err["reason"] == "style" and err["status"] == 403 and "franri" in err["message"]
    assert not sent


def test_make_chart_says_when_credits_are_gone(monkeypatch):
    sent = fake_llm(monkeypatch)
    with new_client() as c:
        uid = sign_in(c)
        key = make_key(c)["key"]
        spend(f"u:{uid}", 1.0)
        res = tool(c, key, "make_chart", data=CSV)
    err = error_of(res)
    assert err["reason"] == "credits" and err["status"] == 429 and "Resets at" in res["content"][0]["text"]
    assert not sent


def test_make_chart_explains_bad_data_and_bad_chart_type(monkeypatch):
    fake_llm(monkeypatch)
    with new_client() as c:
        sign_in(c)
        key = make_key(c)["key"]
        assert error_of(tool(c, key, "make_chart", data="  "))["reason"] == "data"
        assert error_of(tool(c, key, "make_chart", data=CSV, chart_type="pie3d"))["reason"] == "chart_type"
        assert error_of(tool(c, key, "edit_chart", spec={"kind": "bar", "rows": []}, instruction="x"))["reason"] == "spec"


def test_render_timeout_is_reported(monkeypatch):
    fake_llm(monkeypatch)

    async def slow(name, payload):
        raise render.RenderTimeout("Drawing took longer than 25 s")

    monkeypatch.setattr(pipeline, "stage", slow)
    with new_client() as c:
        sign_in(c)
        res = tool(c, make_key(c)["key"], "make_chart", data=CSV, chart_type="bar")
    assert error_of(res)["reason"] == "timeout" and res["content"][0]["text"].startswith("Render timeout.")


def test_tool_calls_share_the_render_rate_limit(monkeypatch):
    monkeypatch.setattr(render.LIMIT, "limits", {"render": 1})
    monkeypatch.setattr(render.LIMIT, "_hits", type(render.LIMIT._hits)(render.LIMIT._hits.default_factory))
    fake_llm(monkeypatch)
    with new_client() as c:
        sign_in(c)
        key = make_key(c)["key"]
        tool(c, key, "make_chart", data="  ")
        assert error_of(tool(c, key, "make_chart", data="  "))["reason"] == "rate"


def _chrome():
    try:
        return render.chrome_path()
    except render.RenderError:
        return None


@pytest.mark.skipif(_chrome() is None, reason="needs chromium")
def test_make_then_edit_runs_the_web_pipeline_and_charges_the_account(monkeypatch):
    sent = fake_llm(monkeypatch, {"reply": "Kept the top 10.", "set": {}, "ops": [{"op": "top_n", "n": 10}]})
    try:
        with new_client() as c:
            uid = sign_in(c, styles="franri,aiw")
            key = make_key(c)["key"]
            made = tool(c, key, "make_chart", data=CSV, description="AI use by EU country", style="aiw")
            assert not made["isError"], made
            image, summary, spec_text = made["content"]
            assert image["type"] == "image" and base64.b64decode(image["data"]).startswith(PNG)
            spec = json.loads(spec_text["text"])
            assert spec["kind"] == "bar" and spec["style"] == "aiw" and spec["title"] == "AI use by EU country, 2025"
            assert len(spec["rows"]) > 20 and spec["quickviz"]["recipe"]["roles"]["cat"] == "country"
            assert "html=true" in summary["text"]
            paths = [p for p, _ in sent]
            assert paths == ["/api/alpha/decisions", "/api/v1/chat/completions"]
            assert "The user says: AI use by EU country" in sent[0][1]["questions"]["kind"]["instructions"]
            edited = tool(c, key, "edit_chart", spec=spec, instruction="only the top 10", html=True)
            assert not edited["isError"], edited
            spec2 = json.loads(edited["content"][2]["text"])
            assert len({r["cat"] for r in spec2["rows"]}) <= 11 and spec2["style"] == "aiw"
            assert "Kept the top 10." in edited["content"][1]["text"]
            html = edited["content"][3]["resource"]
            assert html["mimeType"] == "text/html" and html["text"].startswith("<!doctype html>")
            assert sent[-1][1]["response_format"] == {"type": "json_object"}
        assert {r.path for r in spent_rows(f"u:{uid}")} == {"/api/alpha/decisions", "/api/v1/chat/completions"}
    finally:
        import asyncio
        asyncio.run(render.RENDERER.stop())
