import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app import auth, db, guard, llm
from app.config import get_settings, key_from_files
from app.models import LoginSession, OAuthState, User
from conftest import ORIGIN, new_client, sign_in, spend

COLUMNS = [{"name": "country", "type": "category", "distinct": 2, "samples": ["Belgium", "Spain"]},
           {"name": "value", "type": "number", "distinct": 2, "samples": [1, 2]}]


def fake_jev(monkeypatch, cost=0.001):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"answers": {"kind": {"choice": "bar", "probabilities": {"bar": 1}}}, "usage": {"cost": cost}})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    return sent


def decide(c):
    return c.post("/api/viz/decide", json={"text": "", "columns": COLUMNS})


def test_page_works_without_sign_in(client, monkeypatch):
    fake_jev(monkeypatch)
    assert client.get("/").status_code == 200
    assert decide(client).status_code == 200
    for gone in ("/login.html", "/admin.html", "/admin", "/invite.html", "/account.js"):
        assert client.get(gone).status_code == 404, gone
    me = client.get("/api/me").json()
    assert me["signed_in"] is False and me["email"] is None and me["credits_day"] == 100 and me["credits_left"] == 99


def test_page_has_no_ceps_account_parts(client):
    html = client.get("/").text
    for word in ("feedback", "style-pick", "model-pick", "ceps-logo", "budget"):
        assert word not in html, word
    assert 'id="credits"' in html and 'id="signin"' in html and 'id="signout"' in html


def test_anonymous_credits_per_ip(monkeypatch):
    sent = fake_jev(monkeypatch, cost=0.03)
    with new_client("9.9.9.9") as a, new_client("8.8.8.8") as b:
        assert [decide(a).status_code for _ in range(4)] == [200] * 4
        assert a.get("/api/me").json()["credits_left"] == 0
        r = decide(a)
        assert r.status_code == 429
        d = r.json()["detail"]
        assert d["reason"] == "credits" and d["sign_in"] is False and d["left"] == 0
        assert "used up today's credits" in d["message"] and "midnight UTC" in d["message"]
        assert decide(b).status_code == 200
    assert len(sent) == 5


def test_out_of_credits_offers_sign_in_when_google_is_set(monkeypatch):
    google_on(monkeypatch)
    fake_jev(monkeypatch)
    spend("ip:4.3.2.1", 0.1)
    with new_client("4.3.2.1") as c:
        r = decide(c)
    assert r.status_code == 429 and r.json()["detail"]["sign_in"] is True


def test_signed_in_users_get_more_credits(monkeypatch):
    fake_jev(monkeypatch)
    spend("ip:7.7.7.7", 0.1)
    with new_client("7.7.7.7") as c:
        assert decide(c).status_code == 429
        uid = sign_in(c)
        assert decide(c).status_code == 200
        me = c.get("/api/me").json()
        assert me["signed_in"] and me["email"] == "ana@example.com" and me["credits_day"] == 1000 and me["credits_left"] == 999
        spend(f"u:{uid}", 0.999)
        r = decide(c)
    assert r.status_code == 429 and r.json()["detail"]["sign_in"] is False


def test_admin_set_number_overrides_the_default(monkeypatch):
    fake_jev(monkeypatch)
    with new_client("6.6.6.1") as c:
        uid = sign_in(c, "bo@example.com", credits_day=10)
        assert c.get("/api/me").json()["credits_day"] == 10
        spend(f"u:{uid}", 0.01)
        assert decide(c).status_code == 429
    with new_client("6.6.6.2") as c:
        sign_in(c, "cy@example.com", credits_day=5000)
        assert c.get("/api/me").json()["credits_left"] == 5000


def test_global_cap_stops_everyone(monkeypatch):
    sent = fake_jev(monkeypatch)
    spend("ip:1.1.1.1", 3.0)
    with new_client("2.2.2.2") as c:
        r = decide(c)
        sign_in(c)
        r2 = decide(c)
    for x in (r, r2):
        d = x.json()["detail"]
        assert x.status_code == 429 and d["reason"] == "site" and "busy today" in d["message"]
    assert sent == []


def test_redraw_needs_three_calls_of_credits(monkeypatch):
    sent = fake_jev(monkeypatch)
    spend("ip:3.3.3.3", 0.086)
    with new_client("3.3.3.3") as c:
        r = c.post("/api/viz/redraw?name=chart.png", content=b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                   headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 429 and r.json()["detail"]["reason"] == "credits" and sent == []
        assert decide(c).status_code == 200


def test_redraw_gives_back_unused_reservations(client, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    r = client.post("/api/viz/redraw?name=chart.png", content=b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 502
    assert guard.summary()["spent_usd"] == 0.03


def test_credits_reset_at_midnight_utc(clock, monkeypatch):
    fake_jev(monkeypatch)
    clock["t"] = 1_791_504_000.0 - 10
    spend("ip:4.4.4.4", 0.2)
    spend("ip:5.5.5.5", 3.0)
    with new_client("4.4.4.4") as c:
        assert decide(c).json()["detail"]["reason"] == "site"
        assert c.get("/api/me").json()["resets_at"].endswith("T00:00:00Z")
        clock["t"] += 20
        assert guard.summary()["spent_usd"] == 0
        assert c.get("/api/me").json()["credits_left"] == 100
        assert decide(c).status_code == 200


def test_timeouts_and_errors_still_cost(client, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    assert decide(client).status_code == 502
    assert guard.summary()["spent_usd"] == 0.01
    assert client.get("/api/me").json()["credits_left"] == 90


def test_key_comes_from_the_first_file_that_has_it(tmp_path):
    a, b = tmp_path / "a.env", tmp_path / "b.env"
    b.write_text('OTHER=1\nOPENROUTER_API_KEY="sk-from-b"\n')
    assert key_from_files([a, b]) == "sk-from-b"
    a.write_text("OPENROUTER_API_KEY=sk-from-a\n")
    assert key_from_files([a, b]) == "sk-from-a"
    assert key_from_files([tmp_path / "none.env"]) == ""


@pytest.mark.parametrize("path,body", [("/api/pick", {"text": "coffee prices"}), ("/api/fill", {"text": "coffee prices", "kind": "bar"}),
                                       ("/api/web-data", {"text": "coffee prices", "kind": "bar"})])
def test_mock_routes_use_credits(monkeypatch, path, body):
    from app import mock

    monkeypatch.setattr(mock, "WEB_CACHE", mock.WebCache())
    monkeypatch.setattr(mock, "LIMIT", mock.RateLimit())
    monkeypatch.setenv("CREDITS_ANON_DAY", "1")
    get_settings.cache_clear()
    sent = fake_jev(monkeypatch)
    with new_client("5.5.5.5") as c:
        c.post(path, json=body)
        r = c.post(path, json={**body, "text": body["text"] + " again"})
    assert r.status_code == 429 and r.json()["detail"]["reason"] == "credits" and len(sent) == 1
    spend("ip:6.6.6.6", 3.0)
    with new_client("7.7.7.7") as c:
        r = c.post(path, json=body)
    assert r.status_code == 429 and r.json()["detail"]["reason"] == "site" and len(sent) == 1


def google_on(monkeypatch, admin=""):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    if admin:
        monkeypatch.setenv("ADMIN_EMAIL", admin)
    get_settings.cache_clear()


def id_token(**over):
    claims = {"iss": "https://accounts.google.com", "aud": "cid.apps.googleusercontent.com", "sub": "g-123",
              "email": "Dee@Example.com", "email_verified": True, "name": "Dee", "exp": time.time() + 600, **over}
    part = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"e30.{part}.sig"


def fake_google(monkeypatch, **over):
    seen = []

    def handler(request):
        form = parse_qs(request.content.decode())
        seen.append({k: v[0] for k, v in form.items()})
        return httpx.Response(200, json={"access_token": "at", "id_token": id_token(**over)})

    monkeypatch.setattr(auth, "transport", httpx.MockTransport(handler))
    return seen


def start(c):
    r = c.get("/auth/google/login", follow_redirects=False)
    assert r.status_code == 303
    url = urlsplit(r.headers["location"])
    return r, url, {k: v[0] for k, v in parse_qs(url.query).items()}


def test_sign_in_is_hidden_when_google_is_unset(client):
    assert client.get("/api/me").json()["sign_in"] is False
    assert client.get("/auth/google/login", follow_redirects=False).status_code == 404
    assert client.get("/auth/google/callback?code=x&state=y", follow_redirects=False).status_code == 404


def test_google_login_sends_state_and_pkce(client, monkeypatch):
    google_on(monkeypatch)
    assert client.get("/api/me").json()["sign_in"] is True
    r, url, q = start(client)
    assert url.netloc == "accounts.google.com"
    assert q["scope"] == "openid email profile" and q["response_type"] == "code" and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == ORIGIN + "/auth/google/callback" and q["client_id"] == "cid.apps.googleusercontent.com"
    cookie = r.headers["set-cookie"]
    assert auth.STATE_COOKIE + "=" + q["state"] in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    with db.session() as s:
        row = s.get(OAuthState, auth.digest(q["state"]))
    assert auth.challenge(row.verifier) == q["code_challenge"] and row.verifier not in r.headers["location"]


def test_callback_checks_state(client, monkeypatch):
    google_on(monkeypatch)
    seen = fake_google(monkeypatch)
    _, _, q = start(client)
    r = client.get(f"/auth/google/callback?code=c1&state={q['state']}x", follow_redirects=False)
    assert r.headers["location"] == "/?signin=failed"
    client.cookies.delete(auth.STATE_COOKIE, path="/auth")
    r = client.get(f"/auth/google/callback?code=c1&state={q['state']}", follow_redirects=False)
    assert r.headers["location"] == "/?signin=failed"
    with new_client() as other:
        other.cookies.set(auth.STATE_COOKIE, "made-up", path="/auth")
        r = other.get("/auth/google/callback?code=c1&state=made-up", follow_redirects=False)
    assert r.headers["location"] == "/?signin=failed"
    assert seen == [] and auth.COOKIE not in client.cookies


def test_callback_creates_the_user_and_signs_in(client, monkeypatch):
    google_on(monkeypatch)
    seen = fake_google(monkeypatch)
    _, _, q = start(client)
    r = client.get(f"/auth/google/callback?code=c1&state={q['state']}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith(auth.COOKIE + "=")][0]
    assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower() and "Secure" not in cookie
    assert seen[0]["code"] == "c1" and auth.challenge(seen[0]["code_verifier"]) == q["code_challenge"]
    assert seen[0]["grant_type"] == "authorization_code" and seen[0]["redirect_uri"] == ORIGIN + "/auth/google/callback"
    me = client.get("/api/me").json()
    assert me["signed_in"] and me["email"] == "dee@example.com" and me["credits_day"] == 1000 and not me["is_admin"]
    with db.session() as s:
        users = s.query(User).all()
    assert [(u.email, u.google_sub, u.name) for u in users] == [("dee@example.com", "g-123", "Dee")]
    again = client.get(f"/auth/google/callback?code=c1&state={q['state']}", follow_redirects=False)
    assert again.headers["location"] == "/?signin=failed"


@pytest.mark.parametrize("over", [{"aud": "someone-else"}, {"email_verified": False}, {"iss": "https://evil.example"},
                                  {"exp": time.time() - 5}])
def test_callback_refuses_bad_tokens(client, monkeypatch, over):
    google_on(monkeypatch)
    fake_google(monkeypatch, **over)
    _, _, q = start(client)
    r = client.get(f"/auth/google/callback?code=c1&state={q['state']}", follow_redirects=False)
    assert r.headers["location"] == "/?signin=failed" and client.get("/api/me").json()["signed_in"] is False


def test_blocked_user_is_refused(client, monkeypatch):
    google_on(monkeypatch)
    fake_google(monkeypatch)
    with new_client() as old:
        uid = sign_in(old, "dee@example.com")
        with db.session() as s, s.begin():
            s.get(User, uid).active = False
        assert old.get("/api/me").json()["signed_in"] is False
    _, _, q = start(client)
    r = client.get(f"/auth/google/callback?code=c1&state={q['state']}", follow_redirects=False)
    assert r.headers["location"] == "/?signin=blocked" and auth.COOKIE not in client.cookies


def test_secure_cookie_in_production(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://quickviz.franri.dev")
    google_on(monkeypatch)
    with new_client() as c:
        r = c.get("/auth/google/login", follow_redirects=False)
    assert "Secure" in r.headers["set-cookie"]
    assert parse_qs(urlsplit(r.headers["location"]).query)["redirect_uri"] == ["https://quickviz.franri.dev/auth/google/callback"]


def test_sign_out(client):
    sign_in(client)
    assert client.get("/api/me").json()["signed_in"] is True
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").json()["signed_in"] is False
    with db.session() as s:
        assert s.query(LoginSession).count() == 0


def test_writes_need_our_origin(client, monkeypatch):
    sign_in(client)
    assert client.post("/api/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/logout", headers={"Origin": ""}).status_code == 403
    assert client.get("/api/me").json()["signed_in"] is True
    monkeypatch.setenv("PRODUCTION", "true")
    get_settings.cache_clear()
    assert client.post("/api/logout", headers={"Origin": "http://localhost:9999"}).status_code == 403
    assert client.post("/api/logout").status_code == 200


def test_admin_page_and_api_need_the_admin(monkeypatch):
    google_on(monkeypatch, admin="Boss@Example.com")
    with new_client() as anon:
        assert anon.get("/admin").status_code == 404 and anon.get("/api/admin/users").status_code == 401
    with new_client() as c:
        sign_in(c, "ana@example.com")
        assert c.get("/admin").status_code == 404 and c.get("/admin.html").status_code == 404
        assert c.get("/api/admin/users").status_code == 403
        assert c.patch("/api/admin/users/x", json={"active": False}).status_code == 403
    with new_client() as c:
        sign_in(c, "boss@example.com")
        assert c.get("/api/me").json()["is_admin"] is True
        page = c.get("/admin")
        assert page.status_code == 200 and "People" in page.text and "__VERSION__" not in page.text


def test_admin_lists_use_and_sets_credits(clock, monkeypatch):
    google_on(monkeypatch, admin="boss@example.com")
    clock["t"] = 1_791_504_000.0 + 3600
    with new_client("1.0.0.1") as user, new_client("1.0.0.2") as boss:
        uid = sign_in(user, "ana@example.com")
        bid = sign_in(boss, "boss@example.com")
        spend(f"u:{uid}", 0.005)
        spend(f"u:{uid}", 0.010, guard.days_ago(3))
        spend(f"u:{uid}", 0.500, guard.days_ago(7))
        spend("ip:1.0.0.1", 0.050)
        d = boss.get("/api/admin/users").json()
        rows = {u["email"]: u for u in d["users"]}
        assert d["credits_user_day"] == 1000
        assert rows["ana@example.com"]["used_today"] == 5 and rows["ana@example.com"]["used_week"] == 15
        assert rows["ana@example.com"]["credits_day"] == 1000 and rows["ana@example.com"]["credits_own"] is False
        assert rows["boss@example.com"]["is_admin"] and rows["boss@example.com"]["me"]
        assert boss.patch(f"/api/admin/users/{uid}/credits", json={"credits_day": 5}).json()["credits_day"] == 5
        assert user.get("/api/me").json()["credits_left"] == 0
        assert boss.patch(f"/api/admin/users/{uid}/credits", json={"credits_day": -1}).status_code == 422
        assert boss.patch(f"/api/admin/users/{uid}/credits", json={"credits_day": None}).json()["credits_day"] == 1000
        assert boss.patch(f"/api/admin/users/{bid}", json={"active": False}).status_code == 400
        assert boss.patch(f"/api/admin/users/{uid}", json={"active": False}).json()["active"] is False
        assert user.get("/api/me").json()["signed_in"] is False
        assert boss.get("/api/admin/users").json()["users"][0]["active"] is False
        assert boss.patch(f"/api/admin/users/{uid}", json={"active": True}).status_code == 200
        assert boss.patch("/api/admin/users/nobody/credits", json={"credits_day": 3}).status_code == 404
