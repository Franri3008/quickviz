import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QUICKVIZ_ENV_FILE"] = str(Path(__file__).parent / "no-such.env")
DB_FILE = Path(tempfile.mkdtemp(prefix="quickviz-tests-")) / "test.db"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, db, guard, llm  # noqa: E402
from app.config import get_settings  # noqa: E402

ORIGIN = "http://localhost:8011"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    values = {
        "OPENROUTER_API_KEY": "sk-test-server-key",
        "GLOBAL_DAY_USD": "3",
        "FALLBACK_COST_USD": "0.01",
        "CREDITS_ANON_DAY": "100",
        "CREDITS_USER_DAY": "1000",
        "DATABASE_URL": f"sqlite:///{DB_FILE}",
        "PUBLIC_URL": ORIGIN,
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "ADMIN_EMAIL", "PRODUCTION"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    db.reset_caches()
    db.initialize()
    guard.reset()
    monkeypatch.setattr(llm, "GENERATION_WAIT", 0)
    monkeypatch.setattr(llm, "transport", None)
    monkeypatch.setattr(auth, "transport", None)
    yield
    guard.reset()
    get_settings.cache_clear()


def new_client(ip: str | None = None):
    from app.main import app

    headers = {"Origin": ORIGIN}
    if ip:
        headers["X-Forwarded-For"] = ip
    return TestClient(app, base_url=ORIGIN, headers=headers)


@pytest.fixture
def client():
    with new_client() as c:
        yield c


@pytest.fixture
def clock(monkeypatch):
    state = {"t": 1_791_460_800.0}
    monkeypatch.setattr(guard, "now", lambda: state["t"])
    return state


def spend(who: str, usd: float, day: str | None = None):
    from app.models import Spend

    with db.session() as s, s.begin():
        s.add(Spend(day=day or guard.today(), who=who, at=time.time(), path="test", status="ok", source="usage", cost_usd=usd))


def sign_in(c, email: str = "ana@example.com", **fields) -> str:
    from app.models import LoginSession, User

    with db.session() as s, s.begin():
        user = s.query(User).filter_by(email=email).first()
        if user is None:
            user = User(email=email, **fields)
            s.add(user)
            s.flush()
        token = f"tok-{user.id}"
        s.add(LoginSession(token=auth.digest(token), user_id=user.id, expires=time.time() + 3600))
        uid = user.id
    c.cookies.set(auth.COOKIE, token)
    return uid


def spent_rows(who: str):
    from app.models import Spend

    with db.session() as s:
        return list(s.query(Spend).filter_by(who=who))
