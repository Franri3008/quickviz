import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select

from app import guard
from app.config import get_settings
from app.db import session
from app.models import LoginSession, OAuthState, User

COOKIE = "quickviz_session"
STATE_COOKIE = "quickviz_oauth"
STATE_SECONDS = 600
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
transport: httpx.AsyncBaseTransport | None = None
router = APIRouter()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def challenge(verifier: str) -> str:
    return b64url(hashlib.sha256(verifier.encode()).digest())


def redirect_uri() -> str:
    return get_settings().public_url.rstrip("/") + "/auth/google/callback"


def is_admin(user: User | None) -> bool:
    admin = get_settings().admin
    return bool(user and admin and user.email.lower() == admin)


def session_user(request: Request) -> User | None:
    token = request.cookies.get(COOKIE, "")
    if not token:
        return None
    with session() as db:
        record = db.get(LoginSession, digest(token))
        if not record or record.expires <= time.time():
            return None
        user = db.get(User, record.user_id)
        if not user or not user.active:
            return None
        return user


def current_user(request: Request) -> User:
    user = session_user(request)
    if not user:
        raise HTTPException(401, detail="Please sign in.")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(403, detail="Administrator access required.")
    return user


def revoke_sessions(db, user_id: str):
    db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))


def _cookie(response: Response, name: str, value: str, seconds: int, path: str = "/"):
    response.set_cookie(name, value, max_age=seconds, httponly=True, secure=get_settings().secure_cookies,
                        samesite="lax", path=path)


def start_session(db, response: Response, user: User):
    token = secrets.token_urlsafe(32)
    seconds = get_settings().session_hours * 3600
    db.add(LoginSession(token=digest(token), user_id=user.id, expires=time.time() + seconds))
    _cookie(response, COOKIE, token, seconds)


def me_payload(request: Request) -> dict:
    s = get_settings()
    user = session_user(request)
    limit = guard.limit_for(user)
    key = guard.who(guard.client_ip(request), user)
    return {"signed_in": user is not None, "email": user.email if user else None, "is_admin": is_admin(user),
            "sign_in": s.google_on, "credits_left": guard.left(key, limit), "credits_day": limit,
            "resets_at": guard.next_reset()}


@router.get("/api/me")
def me(request: Request):
    return me_payload(request)


@router.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE, "")
    if token:
        with session() as db, db.begin():
            db.execute(delete(LoginSession).where(LoginSession.token == digest(token)))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


def back(reason: str | None = None) -> RedirectResponse:
    r = RedirectResponse("/" + (f"?signin={reason}" if reason else ""), 303)
    r.delete_cookie(STATE_COOKIE, path="/auth")
    return r


@router.get("/auth/google/login", include_in_schema=False)
def google_login():
    s = get_settings()
    if not s.google_on:
        raise HTTPException(404, detail="Sign-in is off.")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    t = time.time()
    with session() as db, db.begin():
        db.execute(delete(OAuthState).where(OAuthState.expires < t))
        db.add(OAuthState(state=digest(state), verifier=verifier, expires=t + STATE_SECONDS))
    query = urlencode({"client_id": s.google_client_id, "redirect_uri": redirect_uri(), "response_type": "code",
                       "scope": "openid email profile", "state": state, "code_challenge": challenge(verifier),
                       "code_challenge_method": "S256", "prompt": "select_account"})
    r = RedirectResponse(f"{GOOGLE_AUTH}?{query}", 303)
    _cookie(r, STATE_COOKIE, state, STATE_SECONDS, "/auth")
    return r


def claims(id_token: str) -> dict:
    try:
        part = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError):
        return {}


def valid_claims(c: dict) -> bool:
    s = get_settings()
    aud = c.get("aud")
    auds = aud if isinstance(aud, list) else [aud]
    return (c.get("iss") in GOOGLE_ISSUERS and s.google_client_id in auds and isinstance(c.get("exp"), (int, float))
            and c["exp"] > time.time() and isinstance(c.get("sub"), str) and isinstance(c.get("email"), str)
            and c.get("email_verified") in (True, "true"))


async def exchange(code: str, verifier: str) -> dict:
    s = get_settings()
    async with httpx.AsyncClient(timeout=15, transport=transport) as client:
        r = await client.post(GOOGLE_TOKEN, data={"client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                                   "code": code, "code_verifier": verifier, "grant_type": "authorization_code",
                                                   "redirect_uri": redirect_uri()})
    if r.status_code != 200:
        return {}
    try:
        return claims(r.json().get("id_token") or "")
    except ValueError:
        return {}


@router.get("/auth/google/callback", include_in_schema=False)
async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if not get_settings().google_on:
        raise HTTPException(404, detail="Sign-in is off.")
    if error:
        return back("cancelled")
    cookie = request.cookies.get(STATE_COOKIE, "")
    if not code or not state or not cookie or not hmac.compare_digest(cookie, state):
        return back("failed")
    with session() as db, db.begin():
        row = db.get(OAuthState, digest(state))
        verifier = row.verifier if row and row.expires > time.time() else None
        if row:
            db.delete(row)
    if not verifier:
        return back("failed")
    c = await exchange(code, verifier)
    if not valid_claims(c):
        return back("failed")
    email = c["email"].strip().lower()[:254]
    r = back()
    with session() as db, db.begin():
        user = db.scalar(select(User).where(User.google_sub == c["sub"])) or db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, google_sub=c["sub"], name=str(c.get("name") or "")[:200])
            db.add(user)
            db.flush()
        if not user.active:
            return back("blocked")
        user.google_sub = c["sub"]
        user.email = email
        user.last_seen = time.time()
        start_session(db, r, user)
    return r


def origin_allowed(origin: str) -> bool:
    s = get_settings()
    origin = origin.rstrip("/")
    if origin and origin == s.public_origin:
        return True
    if s.production:
        return False
    return (urlsplit(origin).hostname or "") in {"localhost", "127.0.0.1"}
