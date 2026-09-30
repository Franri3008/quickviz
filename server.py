"""QuickViz: tiny local server. Serves index.html and proxies Jev + a label-filler model on OpenRouter."""
import json, os, re, threading, time, urllib.request, urllib.error
from collections import defaultdict, deque
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
PORT = int(os.environ.get("PORT", 8799))
# Render sets PORT and needs 0.0.0.0. Locally we stay on 127.0.0.1.
HOST = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
JEV_MODEL = "typesafe/jev-1.13"
# OpenRouter tries these in order, so a rate-limited model falls through to the next.
FILL_MODELS = os.environ.get("FILL_MODELS", "qwen/qwen3-8b,mistralai/mistral-small-3.2-24b-instruct,google/gemma-4-26b-a4b-it").split(",")


def load_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    # Local only. On Render the key comes from the environment.
    for p in [ROOT / ".env", Path.home() / "Documents/github/observatory-site/.env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No OPENROUTER_API_KEY found")


KEY = load_key()
PRESETS = json.loads((ROOT / "presets.json").read_text())


# ---------- demo cache: record with CACHE_RECORD=1, replay when OpenRouter fails ----------
CACHE_PATH = ROOT / "demo" / "cache.json"
CACHE_RECORD = os.environ.get("CACHE_RECORD") == "1"
_cache_lock = threading.Lock()
try:
    CACHE = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
except Exception:
    CACHE = {}


def cache_key(path, body):
    return path + " " + json.dumps(body, sort_keys=True)


def openrouter(path, body, timeout=20):
    """Returns (data, cached). On failure replays demo/cache.json if it has this exact call."""
    key = cache_key(path, body)
    req = urllib.request.Request(
        "https://openrouter.ai" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception:
        if key in CACHE:
            return CACHE[key], True
        raise
    if CACHE_RECORD:
        with _cache_lock:
            CACHE[key] = data
            CACHE_PATH.parent.mkdir(exist_ok=True)
            tmp = CACHE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(CACHE, indent=1))
            tmp.replace(CACHE_PATH)
    return data, False


# ---------- per-visitor rate limit, in memory ----------
LIMITS = {"jev": int(os.environ.get("RATE_JEV", 60)), "fill": int(os.environ.get("RATE_FILL", 20))}
_hits = defaultdict(deque)
_hits_lock = threading.Lock()


def allow(ip, bucket):
    now = time.time()
    with _hits_lock:
        q = _hits[(ip, bucket)]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= LIMITS[bucket]:
            return False, int(61 - (now - q[0]))
        q.append(now)
        if len(_hits) > 5000:  # drop idle visitors so memory stays small
            for k in [k for k, v in _hits.items() if not v or v[-1] < now - 60]:
                del _hits[k]
        return True, 0


def pick(text):
    t0 = time.time()
    data, cached = openrouter("/api/alpha/decisions", {
        "model": JEV_MODEL, "state": "",
        "questions": {"answer": {
            "type": "choice",
            "instructions": "A user describes the data they have. Pick the chart type that best shows it.\n\n" + text[:2000],
            "criteria": {p["id"]: p["description"] for p in PRESETS},
        }},
    })
    a = data.get("answers", {}).get("answer", {})
    probs = a.get("probabilities") or {}
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])
    return {"choice": a.get("choice"), "confidence": a.get("confidence"), "ranked": ranked[:3],
            "ms": round((time.time() - t0) * 1000), "cost": data.get("usage", {}).get("cost"), "cached": cached}


ROLE_HELP = {
    "cat": "the category column, the names of the items being compared",
    "series": "the sub-group column, which splits each item or time step into groups",
    "t": "the time column, the steps along the x axis",
    "v": "the main numeric value column",
    "v2": "a second numeric column, plotted against the first",
}


def roles(text, kind, need, columns, optional=()):
    """One Jev call, one choice question per role. columns: [{name, type, distinct}]."""
    t0 = time.time()
    crit = {}
    for c in columns[:40]:
        name = str(c.get("name", ""))[:80]
        if name:
            crit[name] = f"{c.get('type', '?')} column, {c.get('distinct', '?')} distinct values"
    if not crit:
        raise ValueError("no columns")
    ctx = f"Chart type: {kind}.\n" + (f"The user says: {text[:1000]}\n" if text else "")
    qs = {}
    for r in need:
        if r in ROLE_HELP:
            c = dict(crit, **({"(none)": "no column fits this role, leave it out"} if r in optional else {}))
            qs[r] = {"type": "choice", "criteria": c,
                     "instructions": ctx + f"Which column should be {ROLE_HELP[r]}?"}
    data, cached = openrouter("/api/alpha/decisions", {"model": JEV_MODEL, "state": "", "questions": qs})
    ans = data.get("answers", {})
    out = {r: {"choice": ans.get(r, {}).get("choice"),
               "ranked": sorted((ans.get(r, {}).get("probabilities") or {}).items(), key=lambda kv: -kv[1])[:4]}
           for r in qs}
    return {"roles": out, "ms": round((time.time() - t0) * 1000), "cached": cached}


FILL_PROMPT = """The user describes data they have. Invent plausible names for a sample chart of type "{kind}".
Reply with JSON only, no prose, in this shape:
{{"title": short chart title, "x": x-axis or category label, "y": value label, "unit": unit symbol or "",
"categories": 4 to 8 short names for the main items (countries, products, months...),
"series": 2 to 4 short names for sub-groups or stages,
"range": [typical min value, typical max value]}}"""


def fill(text, kind):
    t0 = time.time()
    data, cached = openrouter("/api/v1/chat/completions", {
        "models": FILL_MODELS, "max_tokens": 300, "temperature": 0.3,
        "reasoning": {"enabled": False},
        "messages": [{"role": "system", "content": FILL_PROMPT.format(kind=kind)},
                     {"role": "user", "content": text[:2000]}],
    })
    raw = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", raw, re.S)
    out = json.loads(m.group(0)) if m else {}
    out["model"] = data.get("model")
    out["ms"] = round((time.time() - t0) * 1000)
    out["cached"] = cached
    return out


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def log_message(self, fmt, *args):
        pass

    def client_ip(self):
        xff = self.headers.get("X-Forwarded-For", "")
        return xff.split(",")[0].strip() or self.client_address[0]

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 200_000:
                return self.send(413, {"error": "request too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            text = (body.get("text") or "").strip()
            bucket = {"/api/pick": "jev", "/api/roles": "jev", "/api/fill": "fill"}.get(self.path)
            if not bucket:
                return self.send(404, {"error": "not found"})
            if self.path != "/api/roles" and not text:
                return self.send(400, {"error": "empty"})
            ok, wait = allow(self.client_ip(), bucket)
            if not ok:
                return self.send(429, {"error": f"Too many requests. Please wait {wait} s and try again.",
                                       "retry_after": wait})
            if self.path == "/api/pick":
                return self.send(200, pick(text))
            if self.path == "/api/roles":
                return self.send(200, roles(text, body.get("kind", ""), body.get("need") or [], body.get("columns") or [],
                                                 body.get("optional") or []))
            return self.send(200, fill(text, body.get("kind", "bar")))
        except urllib.error.HTTPError as e:
            self.send(502, {"error": f"OpenRouter {e.code}: {e.read().decode()[:300]}"})
        except Exception as e:
            self.send(500, {"error": f"{type(e).__name__}: {e}"})

    def send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


if __name__ == "__main__":
    print(f"QuickViz on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
