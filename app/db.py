from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_url(url: str) -> str:
    if url.startswith(("postgres://", "postgresql://")):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    return url


@lru_cache
def engine():
    url = normalize_url(get_settings().database_url)
    if url.startswith("sqlite:"):
        return create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=240)


@lru_cache
def _factory():
    return sessionmaker(bind=engine(), expire_on_commit=False)


def session():
    return _factory()()


def is_postgres() -> bool:
    return engine().dialect.name == "postgresql"


def initialize():
    from app import models  # noqa: F401

    with engine().begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(58201378)"))
        Base.metadata.create_all(connection)


def reset_caches():
    if engine.cache_info().currsize:
        engine().dispose()
    _factory.cache_clear()
    engine.cache_clear()
