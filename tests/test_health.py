from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app import health, llm
from conftest import spend


ROOT = Path(__file__).resolve().parent.parent

def utc(*args):
    return datetime(*args, tzinfo=timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    health.reset_cache()
    yield
    health.reset_cache()


def openrouter(monkeypatch, key=None, credits=None, key_status=200, fail=False):
    calls = []
    key = {"data": {"label": "sk-or-v1-abc", "limit": 100, "limit_remaining": 42.3456, "usage": 57.65}} if key is None else key
    credits = {"data": {"total_credits": 150.0, "total_usage": 37.123}} if credits is None else credits

    def handler(request: httpx.Request):
        calls.append(request)
        if fail:
            raise httpx.ConnectError("down", request=request)
        if request.url.path == "/api/v1/key":
            return httpx.Response(key_status, json=key if key_status == 200 else {"error": {"message": "No auth"}})
        if request.url.path == "/api/v1/credits":
            return httpx.Response(200, json=credits)
        return httpx.Response(404, json={})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    return calls


def test_healthy(client, clock, monkeypatch):
    calls = openrouter(monkeypatch)
    clock["t"] = utc(2026, 10, 8, 12, 0)
    spend("ip:1.2.3.4", 0.5)
    spend("u:abc", 0.25)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["schemaVersion"] == "1"
    assert body["service"] == "quickviz"
    assert body["ok"] is True
    assert body["error"] is None
    v = (ROOT / "VERSION").read_text().strip()
    assert body["version"] == v
    assert body["metrics"] == {"version": v, "spendTodayUsd": 0.75, "capTodayUsd": 3.0, "visitorsToday": 2,
                               "keyRemainingUsd": 42.35, "accountRemainingUsd": 112.88}
    assert body["checks"]["openrouter"]["ok"] is True
    paths = sorted(c.url.path for c in calls)
    assert paths == ["/api/v1/credits", "/api/v1/key"]
    assert all(c.headers["authorization"] == "Bearer sk-test-server-key" for c in calls)
    assert "sk-test-server-key" not in r.text
    assert "1.2.3.4" not in r.text
    assert "sk-or-v1-abc" not in r.text


def test_timestamps_end_in_z(client, monkeypatch):
    openrouter(monkeypatch)
    body = client.get("/api/health").json()
    for value in (body["checkedAt"], body["updatedAt"], body["checks"]["openrouter"]["updatedAt"]):
        assert value.endswith("Z")
        datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_never_used_is_healthy(client, monkeypatch):
    openrouter(monkeypatch)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["spendTodayUsd"] == 0
    assert body["metrics"]["visitorsToday"] == 0


def test_version_route(client):
    assert client.get("/api/version").json() == {"version": (ROOT / "VERSION").read_text().strip()}


def test_key_rejected(client, monkeypatch):
    openrouter(monkeypatch, key_status=401)
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "KEY_REJECTED"
    assert body["checks"]["openrouter"]["ok"] is False
    assert body["metrics"]["keyRemainingUsd"] is None


def test_openrouter_unreachable(client, monkeypatch):
    openrouter(monkeypatch, fail=True)
    r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "OPENROUTER_DOWN"


def test_low_key_balance(client, monkeypatch):
    openrouter(monkeypatch, key={"data": {"limit": 20, "limit_remaining": 0.49}})
    r = client.get("/api/health")
    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "LOW_KEY_BALANCE"
    assert body["metrics"]["keyRemainingUsd"] == 0.49
    assert body["checks"]["openrouter"]["ok"] is False


def test_key_without_limit(client, monkeypatch):
    openrouter(monkeypatch, key={"data": {"limit": None, "limit_remaining": None}},
               credits={"data": {"total_credits": 3.0, "total_usage": 1.0}})
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["keyRemainingUsd"] is None
    assert body["metrics"]["accountRemainingUsd"] == 2.0


def test_cache_skips_second_call(client, monkeypatch):
    calls = openrouter(monkeypatch)
    now = {"t": 1000.0}
    monkeypatch.setattr(health, "clock", lambda: now["t"])
    client.get("/api/health")
    assert len(calls) == 2
    now["t"] += 299
    client.get("/api/health")
    assert len(calls) == 2
    now["t"] += 2
    client.get("/api/health")
    assert len(calls) == 4


def test_privacy_page_needs_no_sign_in(client):
    r = client.get("/privacy")
    assert r.status_code == 200
    assert "What is kept" in r.text and "__VERSION__" not in r.text
