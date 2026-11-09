import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app import guard
from app.config import get_settings
from app.db import session
from app.models import DEFAULT_STYLE, STYLES, ApiKey, LoginSession, OAuthState, User, parse_styles

COOKIE = "quickviz_session"
STATE_COOKIE = "quickviz_oauth"
NEXT_COOKIE = "quickviz_next"
RETURN_PATH = re.compile(r"^/mcp/files/[A-Za-z0-9_-]{40,64}\.html$")
STATE_SECONDS = 600
KEY_PREFIX = "qv_"
KEY_SEEN_EVERY = 60
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


def allowed_styles(user: User | None) -> list[str]:
    if user is None:
        return [DEFAULT_STYLE]
    if is_admin(user):
        return list(STYLES)
    return parse_styles(user.styles) or [DEFAULT_STYLE]


def default_style(user: User | None) -> str:
    allowed = allowed_styles(user)
    chosen = user.chart_style if user else None
    return chosen if chosen in allowed else allowed[0]


def check_style(user: User | None, style: str | None) -> str:
    if not style:
        return default_style(user)
    if style not in allowed_styles(user):
        raise HTTPException(403, detail={"reason": "style", "message": "That chart style is not open to your account."})
    return style


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


def bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def key_user(token: str) -> User | None:
    if not token.startswith(KEY_PREFIX) or len(token) > 200:
        return None
    with session() as db, db.begin():
        key = db.scalar(select(ApiKey).where(ApiKey.digest == digest(token)))
        if not key:
            return None
        user = db.get(User, key.user_id)
        if not user or not user.active:
            return None
        t = time.time()
        if not key.last_used or t - key.last_used > KEY_SEEN_EVERY:
            key.last_used = t
            user.last_seen = t
        return user


def token_user(request: Request) -> User | None:
    token = bearer_token(request)
    return key_user(token) if token else None


def new_key() -> tuple[str, str, str]:
    token = KEY_PREFIX + secrets.token_urlsafe(32)
    return token, token[:len(KEY_PREFIX) + 6], digest(token)


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
            "resets_at": guard.next_reset(), "styles": allowed_styles(user), "style": default_style(user)}


@router.get("/api/me")
def me(request: Request):
    return me_payload(request)


class StyleInput(BaseModel):
    style: str = Field(min_length=1, max_length=8)


@router.put("/api/me/style")
def set_style(body: StyleInput, user: User = Depends(current_user)):
    style = check_style(user, body.style)
    with session() as db, db.begin():
        db.get(User, user.id).chart_style = style
    return {"style": style}


@router.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE, "")
    if token:
        with session() as db, db.begin():
            db.execute(delete(LoginSession).where(LoginSession.token == digest(token)))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


def safe_next(value: str) -> str:
    return value if isinstance(value, str) and RETURN_PATH.fullmatch(value) else ""


def back(reason: str | None = None, to: str = "") -> RedirectResponse:
    r = RedirectResponse(safe_next(to) or ("/" + (f"?signin={reason}" if reason else "")), 303)
    r.delete_cookie(STATE_COOKIE, path="/auth")
    r.delete_cookie(NEXT_COOKIE, path="/auth")
    return r


@router.get("/auth/google/login", include_in_schema=False)
def google_login(next: str = ""):
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
    if safe_next(next):
        _cookie(r, NEXT_COOKIE, next, STATE_SECONDS, "/auth")
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
    r = back(to=request.cookies.get(NEXT_COOKIE, ""))
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
