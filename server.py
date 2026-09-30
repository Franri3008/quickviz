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
    return {"choice": a.get("choice"), "confidence": a.get("confidence"), "ranked": ranked,
            "ms": round((time.time() - t0) * 1000), "cost": data.get("usage", {}).get("cost"), "cached": cached}


# What each column can be. Jev answers one choice question per column, in the same call as the kind.
COLUMN_ROLES = {
    "name": "names or labels of the items being compared, such as country, product or company",
    "value": "the numbers to plot, such as amount, rate, count or price",
    "time": "dates, years, months, quarters or other time steps",
    "group": "a sub-group that splits the data, such as region, type, gender or scenario",
    "ignore": "not useful for the chart, such as IDs, codes, notes or free text",
}
MAX_COLUMNS = 30


def ranked_probs(a):
    return sorted((a.get("probabilities") or {}).items(), key=lambda kv: -kv[1])


def decide(text, columns):
    """One Jev call: the chart kind plus the role of every column. columns: [{name, type, distinct, samples}]."""
    t0 = time.time()
    cols = [c for c in columns if str(c.get("name", "")).strip()][:MAX_COLUMNS]
    summary = "; ".join(
        f"{c['name']} ({c.get('type', '?')}, {c.get('distinct', '?')} distinct, e.g. "
        + ", ".join(str(x)[:20] for x in (c.get("samples") or [])[:3]) + ")" for c in cols)
    ctx = (f"The user says: {text[:1500]}\n" if text else "") + f"The data has these columns: {summary}.\n"
    qs = {"kind": {
        "type": "choice",
        "instructions": "A user describes the data they have. Pick the chart type that best shows it.\n\n" + ctx,
        "criteria": {p["id"]: p["description"] for p in PRESETS},
    }}
    for i, c in enumerate(cols):
        qs[f"col{i}"] = {
            "type": "choice", "criteria": COLUMN_ROLES,
            "instructions": ctx + f"What role does the column \"{str(c['name'])[:80]}\" play in a chart of this data?",
        }
    data, cached = openrouter("/api/alpha/decisions", {"model": JEV_MODEL, "state": "", "questions": qs})
    ans = data.get("answers", {})
    k = ans.get("kind", {})
    out_cols = {}
    for i, c in enumerate(cols):
        a = ans.get(f"col{i}", {})
        out_cols[c["name"]] = {"role": a.get("choice"), "confidence": a.get("confidence"), "ranked": ranked_probs(a)}
    return {"choice": k.get("choice"), "confidence": k.get("confidence"), "ranked": ranked_probs(k),
            "columns": out_cols, "ms": round((time.time() - t0) * 1000),
            "cost": data.get("usage", {}).get("cost"), "cached": cached}


FILL_PROMPT = """The user describes data they have. Invent plausible names for a sample chart of it.
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
        "messages": [{"role": "system", "content": FILL_PROMPT},
                     {"role": "user", "content": text[:2000]}],
    })
    raw = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", raw, re.S)
    out = json.loads(m.group(0)) if m else {}
    out["model"] = data.get("model")
    out["ms"] = round((time.time() - t0) * 1000)
    out["cached"] = cached
    return out


NAME_PROMPT = """You name the parts of a chart. The user describes their data, and you get its columns with sample values.
Reply with JSON only, no prose, in this shape:
{"title": a short chart title, at most 8 words, no final period,
"unit": the unit symbol of the main numeric value, such as "%", "$", "€" or "bcm", or "",
"columns": {"<each exact column name>": a short readable label, at most 4 words, with the unit in brackets only if it has one, never the column type}}"""


def chat_json(system, user):
    t0 = time.time()
    data, cached = openrouter("/api/v1/chat/completions", {
        "models": FILL_MODELS, "max_tokens": 400, "temperature": 0.2,
        "reasoning": {"enabled": False},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user[:4000]}],
    })
    raw = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", raw, re.S)
    out = json.loads(m.group(0)) if m else {}
    out.update(model=data.get("model"), ms=round((time.time() - t0) * 1000), cached=cached)
    return out


def names(text, columns):
    """Titles and readable axis names for real data. Qwen does the wording Jev cannot."""
    cols = [c for c in columns if str(c.get("name", "")).strip()][:MAX_COLUMNS]
    lines = "\n".join(f"- {c['name']} ({c.get('type', '?')}), e.g. " + ", ".join(str(x)[:30] for x in (c.get("samples") or [])[:3])
                      for c in cols)
    out = chat_json(NAME_PROMPT, (f"The user says: {text}\n" if text else "") + "Columns:\n" + lines)
    known = {c["name"] for c in cols}
    out["columns"] = {k: str(v)[:40] for k, v in (out.get("columns") or {}).items() if k in known}
    out["title"] = str(out.get("title") or "")[:90]
    out["unit"] = str(out.get("unit") or "")[:8]
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
            bucket = {"/api/pick": "jev", "/api/decide": "jev", "/api/fill": "fill", "/api/names": "fill"}.get(self.path)
            if not bucket:
                return self.send(404, {"error": "not found"})
            if self.path not in ("/api/decide", "/api/names") and not text:
                return self.send(400, {"error": "empty"})
            ok, wait = allow(self.client_ip(), bucket)
            if not ok:
                return self.send(429, {"error": f"Too many requests. Please wait {wait} s and try again.",
                                       "retry_after": wait})
            if self.path == "/api/pick":
                return self.send(200, pick(text))
            if self.path == "/api/names":
                return self.send(200, names(text, body.get("columns") or []))
            if self.path == "/api/decide":
                if not body.get("columns"):
                    return self.send(400, {"error": "no columns"})
                return self.send(200, decide(text, body["columns"]))
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
