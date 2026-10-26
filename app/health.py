import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app import llm
from app.config import get_settings

log = logging.getLogger("quickviz.health")
SERVICE = "quickviz"
OPENROUTER_TTL = 300
OPENROUTER_TIMEOUT = 3.0
LOW_KEY_USD = 0.5
_cache: dict = {}


def clock() -> float:
    return time.monotonic()


def utc(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def money(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 2)
    return None


def reset_cache():
    _cache.clear()


async def _fetch_openrouter() -> dict:
    started = time.perf_counter()
    out = {"ok": False, "rejected": False, "reached": False, "key_left": None, "account_left": None,
           "detail": None, "at": time.time()}
    if not get_settings().openrouter_api_key:
        out["detail"] = "No server key configured"
        out["ms"] = 0
        return out
    try:
        async with llm._client(OPENROUTER_TIMEOUT) as client:
            key, credits = await asyncio.gather(
                client.get("/api/v1/key", headers=llm._headers()),
                client.get("/api/v1/credits", headers=llm._headers()),
                return_exceptions=True,
            )
    except Exception:
        log.exception("Health OpenRouter check failed")
        key = credits = None
    out["ms"] = round((time.perf_counter() - started) * 1000)
    if not isinstance(key, httpx.Response):
        if isinstance(key, BaseException):
            log.warning("Health OpenRouter key call failed: %s", type(key).__name__)
        out["detail"] = "OpenRouter could not be reached"
        return out
    out["reached"] = True
    if key.status_code in (401, 403):
        out["rejected"] = True
        out["detail"] = "OpenRouter rejected the key"
        return out
    try:
        data = key.json().get("data") or {}
    except (ValueError, AttributeError):
        data = None
    if key.status_code != 200 or not isinstance(data, dict):
        out["detail"] = f"OpenRouter answered {key.status_code}"
        return out
    out["ok"] = True
    out["key_left"] = money(data.get("limit_remaining"))
    if isinstance(credits, httpx.Response) and credits.status_code == 200:
        try:
            info = credits.json().get("data") or {}
            total = info.get("total_credits")
            used = info.get("total_usage")
            if money(total) is not None and money(used) is not None:
                out["account_left"] = money(total - used)
        except (ValueError, AttributeError, TypeError):
            pass
    if out["account_left"] is None:
        out["detail"] = "Key accepted, account credit unknown"
    else:
        out["detail"] = "Key accepted"
    return out


async def openrouter_state() -> dict:
    hit = _cache.get("openrouter")
    if hit and clock() - hit[0] < OPENROUTER_TTL:
        return hit[1]
    result = await _fetch_openrouter()
    _cache["openrouter"] = (clock(), result)
    return result


def assess(ai: dict, spent: dict, version: str) -> tuple[bool, dict, dict, dict | None]:
    low = ai["key_left"] is not None and ai["key_left"] < LOW_KEY_USD
    error = None
    if ai["rejected"]:
        error = {"code": "KEY_REJECTED", "message": "OpenRouter rejected the server key"}
    elif not ai["ok"]:
        error = {"code": "OPENROUTER_DOWN", "message": ai["detail"] or "OpenRouter check failed"}
    elif low:
        error = {"code": "LOW_KEY_BALANCE", "message": f"Key has under {LOW_KEY_USD:g} USD left"}
    metrics = {
        "version": version,
        "spendTodayUsd": spent["spent_usd"],
        "capTodayUsd": spent["cap_usd"],
        "visitorsToday": spent["visitors"],
        "keyRemainingUsd": ai["key_left"],
        "accountRemainingUsd": ai["account_left"],
    }
    checks = {
        "openrouter": {"ok": ai["ok"] and not low, "ms": ai["ms"], "updatedAt": utc(ai["at"]),
                       "detail": "Key balance low" if ai["ok"] and low else ai["detail"]},
    }
    return error is None, metrics, checks, error
