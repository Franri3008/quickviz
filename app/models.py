import time
from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

STYLES = ("franri", "aiw", "ceps")
DEFAULT_STYLE = "franri"


def parse_styles(value) -> list[str]:
    items = value.split(",") if isinstance(value, str) else list(value or [])
    picked = {str(s).strip().lower() for s in items}
    return [s for s in STYLES if s in picked]


def uid():
    return uuid4().hex


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    credits_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    styles: Mapped[str] = mapped_column(String(40), default=DEFAULT_STYLE, server_default=DEFAULT_STYLE)
    chart_style: Mapped[str | None] = mapped_column(String(8), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created: Mapped[float] = mapped_column(Float, default=time.time)
    last_seen: Mapped[float | None] = mapped_column(Float, nullable=True)


class LoginSession(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires: Mapped[float] = mapped_column(Float, index=True)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(60), default="")
    prefix: Mapped[str] = mapped_column(String(16))
    digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created: Mapped[float] = mapped_column(Float, default=time.time)
    last_used: Mapped[float | None] = mapped_column(Float, nullable=True)


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    verifier: Mapped[str] = mapped_column(String(128))
    expires: Mapped[float] = mapped_column(Float, index=True)


class Spend(Base):
    __tablename__ = "spend"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    day: Mapped[str] = mapped_column(String(10))
    who: Mapped[str] = mapped_column(String(80))
    at: Mapped[float] = mapped_column(Float)
    path: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    source: Mapped[str] = mapped_column(String(16), default="reserve")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (Index("ix_spend_day_who", "day", "who"),)
