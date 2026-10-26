import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app import guard
from app.config import WEB_DIR
from app.llm import Visitor, openrouter, visitor
from app.web_data import FIELDS, WebCache, WebDataError, web_reply, web_request

JEV_MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
FILL_MODELS = [m for m in os.environ.get("FILL_MODELS", "google/gemini-3.8-flash,google/gemini-2.5-flash-lite").split(",") if m]
WEB_MODEL = os.environ.get("WEB_MODEL", FILL_MODELS[0])
MAX_TEXT = 2000
MIN_TEXT = 4
DECISIONS = "/api/alpha/decisions"
CHAT = "/api/v1/chat/completions"

FILL_PROMPT = """The user describes data they have. It will be drawn as a {kind} chart. Invent plausible names for a sample chart of it.
Reply with JSON only, no prose, in this shape:
{"title": short chart title, "x": x-axis or category label, "y": value label, "unit": unit symbol or "",
"categories": short names for the main items (countries, products...), as many as the user asks for, else 6, at most 12,
"series": short names for sub-groups, as many as the user asks for, else 3, at most 8. If several items are tracked over time, they are the series,
"times": 6 to 12 consecutive time labels at the grain the user describes (e.g. "Jan 2025" for monthly, "2019" for yearly, "2024-Q1" for quarterly),
"range": [typical min value, typical max value],
"number": "integer" when the value is a count that cannot be fractional (titles won, people, cars sold), "percent" for shares and rates, else "decimal",
"sources": for a sankey only, the names things flow from,
"targets": for a sankey only, the names things flow to}
Use real, plausible names, never placeholders like "Country A". For a map, categories are real country names, or the real region names of one country, and then also
"country": that country's ISO 3166 alpha-3 code, such as "CHL" or "USA"."""

CHARTABLE = ("Could someone want a chart about this text? Any real-world topic, place, product, "
             "organisation, market or quantity counts, even a single word such as bitcoin or coffee. "
             "Only gibberish, greetings, thanks, filler words or small talk do not.\n\nText: ")

WEB_SCORE = ("Would a public online source likely contain enough exact numeric observations to answer this "
             "chart request without inventing or estimating values? Answer yes only if the measure "
             "and scope are specific enough to identify a real public record or dataset. "
             "For example, historical World Cup wins by country since 1950 are recorded online. "
             "A bare request for coffee prices since 2015 is too vague without a market or price "
             "benchmark. Private sales, personal activity and imagined scenarios are not public data."
             "\n\nText: ")


class MockError(ValueError):
    pass


def load_presets(path):
    presets = json.loads(Path(path).read_text())
    return [p for p in presets if p.get("id") in FIELDS]


def clean_text(text):
    text = str(text or "").strip()
    if len(text) < MIN_TEXT:
        raise MockError("empty")
    return text[:MAX_TEXT]


def pick_request(text, presets):
    text = clean_text(text)
    body = {
        "model": JEV_MODEL, "state": "",
        "questions": {
            "answer": {
                "type": "choice",
                "instructions": "A user describes the data they have. Pick the chart type that best shows it.\n\n" + text,
                "criteria": {p["id"]: p["description"] for p in presets},
            },
            "chartable": {"type": "noul", "instructions": CHARTABLE + text},
            "web_data": {"type": "noul", "instructions": WEB_SCORE + text},
        },
    }
    return DECISIONS, body, 20


def pick_reply(data, ms=None):
    answers = data.get("answers", {}) if isinstance(data, dict) else {}
    a = answers.get("answer", {})
    ranked = sorted((a.get("probabilities") or {}).items(), key=lambda kv: -kv[1])
    choice = a.get("choice")
    if choice not in FIELDS:
        choice = next((k for k, _ in ranked if k in FIELDS), "bar")
    return {"choice": choice, "confidence": a.get("confidence"), "ranked": [[k, p] for k, p in ranked if k in FIELDS],
            "chartable": answers.get("chartable", {}).get("noul"), "web_data": answers.get("web_data", {}).get("noul"),
            "ms": ms, "cost": (data.get("usage") or {}).get("cost")}


def fill_request(text, kind):
    text = clean_text(text)
    kind = kind if kind in FIELDS else "bar"
    body = {
        "models": FILL_MODELS, "max_tokens": 800, "temperature": 0.2,
        "reasoning": {"effort": "minimal"}, "provider": {"sort": "latency"},
        "messages": [{"role": "system", "content": FILL_PROMPT.replace("{kind}", kind)}, {"role": "user", "content": text}],
    }
    return CHAT, body, 20


def _list(value, most):
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        s = str(v).strip()[:60]
        if s and s not in out:
            out.append(s)
    return out[:most]


def fill_reply(data, ms=None):
    raw = data["choices"][0]["message"].get("content") or ""
    if isinstance(raw, list):
        raw = "".join(part.get("text", "") for part in raw if isinstance(part, dict))
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        got = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        got = {}
    if not isinstance(got, dict):
        got = {}
    out = {k: str(got.get(k) or "")[:90] for k in ("title", "x", "y")}
    out["unit"] = str(got.get("unit") or "")[:8]
    out["categories"] = _list(got.get("categories"), 60)
    out["series"] = _list(got.get("series"), 8)
    out["times"] = _list(got.get("times"), 12)
    out["sources"] = _list(got.get("sources"), 6)
    out["targets"] = _list(got.get("targets"), 6)
    rg = got.get("range")
    if isinstance(rg, list) and len(rg) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in rg) and rg[1] > rg[0]:
        out["range"] = rg
    if got.get("number") in ("integer", "percent", "decimal"):
        out["number"] = got["number"]
    if isinstance(got.get("country"), str) and re.fullmatch(r"[A-Z]{3}", got["country"]):
        out["country"] = got["country"]
    out.update(model=data.get("model"), ms=ms, cost=(data.get("usage") or {}).get("cost"))
    return out


def web_data_request(text, kind):
    return web_request(clean_text(text), kind, WEB_MODEL)


def web_data_reply(data, kind):
    return web_reply(data, kind, WEB_MODEL)


LIMITS = {"pick": int(os.environ.get("RATE_PICK", 60)), "fill": int(os.environ.get("RATE_FILL", 60)),
          "web": int(os.environ.get("RATE_WEB", 12))}


class RateLimit:
    def __init__(self, limits=None, window=60):
        self.limits = dict(limits or LIMITS)
        self.window = window
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, ip, bucket):
        now = time.time()
        with self._lock:
            q = self._hits[(ip, bucket)]
            while q and q[0] < now - self.window:
                q.popleft()
            if len(q) >= self.limits[bucket]:
                return False, int(self.window + 1 - (now - q[0]))
            q.append(now)
            if len(self._hits) > 5000:
                for k in [k for k, v in self._hits.items() if not v or v[-1] < now - self.window]:
                    del self._hits[k]
            return True, 0


PRESETS = load_presets(WEB_DIR / "presets.json")
LIMIT = RateLimit()
WEB_CACHE = WebCache()
router = APIRouter(prefix="/api")


def admit(request: Request, body, bucket: str) -> str:
    if not isinstance(body, dict):
        raise HTTPException(400, detail="The request needs a JSON object.")
    if len(str(body.get("text") or "").strip()) < MIN_TEXT:
        raise HTTPException(400, detail=f"Type at least {MIN_TEXT} characters.")
    ok, wait = LIMIT.allow(guard.client_ip(request), bucket)
    if not ok:
        raise HTTPException(429, detail={"reason": "rate", "message": f"Too many requests. Please wait {wait} s and try again.", "retry_after": wait})
    return str(body["text"])


async def ask(user: Visitor, made: tuple) -> tuple[dict, int]:
    t0 = time.time()
    data = await openrouter(user, *made)
    return data, round((time.time() - t0) * 1000)


@router.post("/pick")
async def api_pick(request: Request, body=Body(...), user: Visitor = Depends(visitor)):
    text = admit(request, body, "pick")
    try:
        made = pick_request(text, PRESETS)
    except MockError as e:
        raise HTTPException(422, detail=str(e))
    return pick_reply(*await ask(user, made))


@router.post("/fill")
async def api_fill(request: Request, body=Body(...), user: Visitor = Depends(visitor)):
    text = admit(request, body, "fill")
    try:
        made = fill_request(text, body.get("kind"))
    except MockError as e:
        raise HTTPException(422, detail=str(e))
    data, ms = await ask(user, made)
    try:
        return fill_reply(data, ms)
    except (KeyError, IndexError, TypeError):
        raise HTTPException(502, detail="The model gave no labels.")


@router.post("/web-data")
async def api_web_data(request: Request, body=Body(...), user: Visitor = Depends(visitor)):
    text = admit(request, body, "web")
    kind = body.get("kind")
    hit = WEB_CACHE.get(text, kind, WEB_MODEL)
    if hit:
        return hit
    try:
        made = web_data_request(text, kind)
        data, _ = await ask(user, made)
        return WEB_CACHE.put(text, kind, WEB_MODEL, web_data_reply(data, kind))
    except (MockError, WebDataError) as e:
        raise HTTPException(422, detail=str(e))
    except (KeyError, IndexError, TypeError):
        raise HTTPException(502, detail="The web search gave no usable answer.")
