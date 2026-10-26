import asyncio
import logging
from dataclasses import dataclass, field

import httpx
from fastapi import HTTPException, Request

from app import auth, guard
from app.config import get_settings
from app.models import User

log = logging.getLogger("quickviz.llm")
transport: httpx.AsyncBaseTransport | None = None
GENERATION_TRIES = 3
GENERATION_WAIT = 1.0
REASONING = {"anthropic/claude-haiku-5.5": {"enabled": False}, "google/gemini-3.8-flash": {"effort": "minimal"}}
DEFAULT_REASONING = REASONING["anthropic/claude-haiku-5.5"]


def reasoning(model: str) -> dict | None:
    return REASONING.get(model)


@dataclass
class Visitor:
    ip: str
    user: User | None = None
    prepaid: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.ip

    @property
    def who(self) -> str:
        return guard.who(self.ip, self.user)

    def reserve(self, path: str, calls: int = 1) -> list[str]:
        can = self.user is None and get_settings().google_on
        return guard.reserve(self.who, guard.limit_for(self.user), path, calls, can)


def visitor(request: Request) -> Visitor:
    return Visitor(guard.client_ip(request), auth.session_user(request))


def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=get_settings().openrouter_base_url, timeout=timeout, transport=transport)


def _headers() -> dict:
    s = get_settings()
    return {
        "Authorization": f"Bearer {s.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": s.openrouter_referer,
        "X-Title": s.openrouter_title,
    }


def _usage_cost(data: dict) -> float | None:
    usage = data.get("usage") if isinstance(data, dict) else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
        return float(cost)
    return None


async def _generation_cost(client: httpx.AsyncClient, gen_id: str) -> float | None:
    for attempt in range(GENERATION_TRIES):
        if attempt:
            await asyncio.sleep(GENERATION_WAIT)
        try:
            r = await client.get("/api/v1/generation", params={"id": gen_id}, headers=_headers())
        except httpx.HTTPError:
            continue
        if r.status_code != 200:
            continue
        try:
            cost = (r.json().get("data") or {}).get("total_cost")
        except ValueError:
            continue
        if isinstance(cost, (int, float)) and cost >= 0:
            return float(cost)
    return None


async def openrouter(user: Visitor, path: str, body: dict, timeout: float = 30) -> dict:
    s = get_settings()
    if not s.openrouter_api_key:
        raise HTTPException(503, detail="The server has no OpenRouter key configured.")
    if not path.startswith("/api/"):
        raise HTTPException(400, detail="Bad OpenRouter path.")
    body = {k: v for k, v in body.items() if k != "stream"}
    if path.endswith("/chat/completions"):
        body["usage"] = {"include": True}
    spend_id = user.prepaid.pop() if user.prepaid else user.reserve(path)[0]
    fallback = s.fallback_cost_usd
    async with _client(timeout) as client:
        try:
            r = await client.post(path, json=body, headers=_headers())
        except httpx.TimeoutException:
            guard.settle(spend_id, fallback, "estimate", "timeout")
            raise HTTPException(504, detail="OpenRouter took too long to answer.")
        except httpx.HTTPError as e:
            guard.settle(spend_id, fallback, "estimate", "neterror")
            raise HTTPException(502, detail=f"Could not reach OpenRouter: {type(e).__name__}")
        except BaseException:
            guard.settle(spend_id, fallback, "estimate", "aborted")
            raise
        try:
            data = r.json()
        except ValueError:
            data = None
        gen_id = data.get("id") if isinstance(data, dict) and isinstance(data.get("id"), str) else None
        if r.status_code >= 400 or not isinstance(data, dict):
            cost = _usage_cost(data) if isinstance(data, dict) else None
            guard.settle(spend_id, cost or 0.0, "usage" if cost else "error", "error")
            msg = r.text[:300]
            raise HTTPException(502, detail=f"OpenRouter {r.status_code}: {msg}")
        source = "usage"
        cost = _usage_cost(data)
        if cost is None and gen_id:
            source = "generation"
            cost = await _generation_cost(client, gen_id)
        if cost is None:
            source = "estimate"
            cost = fallback
            log.warning("No cost returned for %s, recorded the fallback estimate", path)
    guard.settle(spend_id, cost, source, "ok")
    return data
