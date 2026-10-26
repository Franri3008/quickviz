import math
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select, text, update

from app.config import get_settings
from app.db import is_postgres, session
from app.models import LoginSession, OAuthState, Spend, User

WEEK_DAYS = 7
_lock = threading.Lock()

SITE_BUSY = ("QuickViz is busy today and has used its AI budget for the day. It opens again at midnight UTC. "
             "Your chart, the chart type tabs, undo and the downloads still work.")
CREDITS_OUT = ("You have used up today's credits. They come back at midnight UTC. "
               "Your chart, the chart type tabs, undo and the downloads still work.")


def now() -> float:
    return time.time()


def today(t: float | None = None) -> str:
    return datetime.fromtimestamp(now() if t is None else t, timezone.utc).strftime("%Y-%m-%d")


def days_ago(n: int, t: float | None = None) -> str:
    d = datetime.fromtimestamp(now() if t is None else t, timezone.utc) - timedelta(days=n)
    return d.strftime("%Y-%m-%d")


def next_reset(t: float | None = None) -> str:
    d = datetime.fromtimestamp(now() if t is None else t, timezone.utc).date() + timedelta(days=1)
    return d.isoformat() + "T00:00:00Z"


def reset():
    with _lock, session() as db, db.begin():
        for table in (Spend, LoginSession, OAuthState, User):
            db.execute(delete(table))


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else ""
    return (ip or (request.client.host if request.client else "") or "unknown")[:64]


def who(ip: str, user: User | None) -> str:
    return f"u:{user.id}" if user else f"ip:{ip}"


def limit_for(user: User | None) -> int:
    s = get_settings()
    if user is None:
        return s.credits_anon_day
    return s.credits_user_day if user.credits_day is None else user.credits_day


def credits(usd: float) -> float:
    return usd / get_settings().usd_per_credit


def whole(value: float) -> int:
    return max(0, math.floor(value + 1e-9))


def _used_usd(db, key: str, day: str) -> float:
    return db.scalar(select(func.coalesce(func.sum(Spend.cost_usd), 0.0)).where(Spend.day == day, Spend.who == key)) or 0.0


def _site_usd(db, day: str) -> float:
    return db.scalar(select(func.coalesce(func.sum(Spend.cost_usd), 0.0)).where(Spend.day == day)) or 0.0


def left(key: str, limit: int) -> int:
    with session() as db:
        return whole(limit - credits(_used_usd(db, key, today())))


def reserve(key: str, limit: int, path: str = "", calls: int = 1, can_sign_in: bool = False) -> list[str]:
    s = get_settings()
    with _lock, session() as db, db.begin():
        if is_postgres():
            db.execute(text("SELECT pg_advisory_xact_lock(58201379)"))
        t = now()
        day = today(t)
        if _site_usd(db, day) >= s.global_day_usd:
            raise HTTPException(429, detail={"reason": "site", "message": SITE_BUSY, "resets_at": next_reset(t)})
        room = limit - credits(_used_usd(db, key, day))
        if room <= 0 or (calls > 1 and room < calls * s.call_credits):
            raise HTTPException(429, detail={"reason": "credits", "message": CREDITS_OUT, "left": whole(room),
                                             "sign_in": can_sign_in, "resets_at": next_reset(t)})
        rows = [Spend(day=day, who=key, at=t, path=path[:120], cost_usd=s.call_credits * s.usd_per_credit)
                for _ in range(calls)]
        db.add_all(rows)
        db.flush()
        return [r.id for r in rows]


def settle(spend_id: str, usd: float, source: str, status: str):
    with session() as db, db.begin():
        db.execute(update(Spend).where(Spend.id == spend_id).values(cost_usd=max(0.0, usd), source=source, status=status))


def release(ids: list[str]):
    if not ids:
        return
    with session() as db, db.begin():
        db.execute(delete(Spend).where(Spend.id.in_(ids), Spend.status == "pending"))


def summary() -> dict:
    s = get_settings()
    day = today()
    with session() as db:
        spent = _site_usd(db, day)
        visitors = db.scalar(select(func.count(func.distinct(Spend.who))).where(Spend.day == day)) or 0
    return {"day": day, "spent_usd": round(spent, 4), "cap_usd": s.global_day_usd, "visitors": visitors}


def user_usage() -> dict[str, dict]:
    day, start = today(), days_ago(WEEK_DAYS - 1)
    out: dict[str, dict] = {}
    with session() as db:
        rows = db.execute(select(Spend.who, Spend.day, func.sum(Spend.cost_usd))
                          .where(Spend.day >= start, Spend.who.like("u:%")).group_by(Spend.who, Spend.day)).all()
    for key, d, usd in rows:
        hit = out.setdefault(key[2:], {"today": 0.0, "week": 0.0})
        hit["week"] += credits(usd or 0.0)
        if d == day:
            hit["today"] += credits(usd or 0.0)
    return {k: {"today": round(v["today"]), "week": round(v["week"])} for k, v in out.items()}
