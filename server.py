"""QuickViz: tiny local server. Serves index.html and proxies Jev + a label-filler model on OpenRouter."""
import json, os, re, threading, time, urllib.request, urllib.error
from collections import defaultdict, deque
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).parent
PORT = int(os.environ.get("PORT", 8799))
HOST = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
JEV_MODEL = "typesafe/jev-1.13"
FILL_MODELS = os.environ.get("FILL_MODELS", "google/gemini-3.8-flash,google/gemini-2.5-flash-lite").split(",")
REASONING = {"effort": "minimal"}


def load_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for p in [ROOT / ".env", Path.home() / "Documents/github/observatory-site/.env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("No OPENROUTER_API_KEY found")


KEY = load_key()
# One place for the version: VERSION. The server writes it into index.html, so the asset URLs change on every release.
VERSION = (ROOT / "VERSION").read_text().strip() if (ROOT / "VERSION").exists() else "dev"
PRESETS = json.loads((ROOT / "presets.json").read_text())


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


LIMITS = {"jev": int(os.environ.get("RATE_JEV", 60)), "fill": int(os.environ.get("RATE_FILL", 60))}
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
        if len(_hits) > 5000:
            for k in [k for k, v in _hits.items() if not v or v[-1] < now - 60]:
                del _hits[k]
        return True, 0


def pick(text):
    t0 = time.time()
    data, cached = openrouter("/api/alpha/decisions", {
        "model": JEV_MODEL, "state": "",
        "questions": {
            "answer": {
                "type": "choice",
                "instructions": "A user describes the data they have. Pick the chart type that best shows it.\n\n" + text[:2000],
                "criteria": {p["id"]: p["description"] for p in PRESETS},
            },
            "chartable": {
                "type": "noul",
                "instructions": "Could someone want a chart about this text? Any real-world topic, place, product, "
                                "organisation, market or quantity counts, even a single word such as bitcoin or coffee. "
                                "Only gibberish, greetings, thanks, filler words or small talk do not.\n\nText: " + text[:2000],
            },
        },
    })
    a = data.get("answers", {}).get("answer", {})
    chartable = data.get("answers", {}).get("chartable", {}).get("noul")
    probs = a.get("probabilities") or {}
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])
    return {"choice": a.get("choice"), "confidence": a.get("confidence"), "ranked": ranked, "chartable": chartable,
            "ms": round((time.time() - t0) * 1000), "cost": data.get("usage", {}).get("cost"), "cached": cached}


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


FILL_PROMPT = """The user describes data they have. It will be drawn as a {kind} chart. Invent plausible names for a sample chart of it.
Reply with JSON only, no prose, in this shape:
{{"title": short chart title, "x": x-axis or category label, "y": value label, "unit": unit symbol or "",
"categories": short names for the main items (countries, products...), as many as the user asks for, else 6, at most 12,
"series": short names for sub-groups, as many as the user asks for, else 3, at most 8. If several items are tracked over time, they are the series,
"times": 6 to 12 consecutive time labels at the grain the user describes (e.g. "Jan 2025" for monthly, "2019" for yearly, "2024-Q1" for quarterly),
"range": [typical min value, typical max value],
"sources": for a sankey only, the names things flow from,
"targets": for a sankey only, the names things flow to}}
Use real, plausible names, never placeholders like "Country A". For a map, categories are real country names, or the real region names of one country, and then also
"country": that country's ISO 3166 alpha-3 code, such as "CHL" or "USA"."""


def fill(text, kind):
    """Sample-chart words, written for the kind Jev picked."""
    return chat_json(FILL_PROMPT.replace("{{", "{").replace("}}", "}").replace("{kind}", kind or "chart"), text[:2000])


NAME_PROMPT = """You check a chart before it is shown. The user describes their data. You get the chart type,
which column fills each role, and every column with sample values.
Roles: cat = the items compared or the source of a flow, series = the sub-groups or the target of a flow,
t = time on the x axis, v = the main number, v2 = the second number of a scatter.
Fix the role mapping if it is wrong, e.g. a flow drawn backwards or the wrong number chosen. Leave it out if it is right.
Reply with JSON only, no prose, in this shape:
{"roles": only the roles you would change, as {"<role>": "<exact column name>"}, or {},
"title": a short chart title, at most 8 words, no final period,
"unit": the unit symbol of the main numeric value, such as "%", "$", "€" or "bcm", or "",
"columns": {"<each exact column name>": a short readable label, at most 4 words, with the unit in brackets only if it has one, never the column type}}"""


def chat_json(system, user):
    t0 = time.time()
    data, cached = openrouter("/api/v1/chat/completions", {
        "models": FILL_MODELS, "max_tokens": 800, "temperature": 0.2,
        "reasoning": REASONING, "provider": {"sort": "latency"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user[:4000]}],
    })
    raw = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", raw, re.S)
    out = json.loads(m.group(0)) if m else {}
    out.update(model=data.get("model"), ms=round((time.time() - t0) * 1000), cached=cached)
    return out


def names(text, columns, kind="", roles=None):
    """Checks the drawn chart: fixes roles, writes the title and readable axis names. Gemini does what Jev cannot."""
    cols = [c for c in columns if str(c.get("name", "")).strip()][:MAX_COLUMNS]
    lines = "\n".join(f"- {c['name']} ({c.get('type', '?')}), e.g. " + ", ".join(str(x)[:30] for x in (c.get("samples") or [])[:3])
                      for c in cols)
    drawn = ", ".join(f"{r}={c}" for r, c in (roles or {}).items())
    out = chat_json(NAME_PROMPT, (f"The user says: {text}\n" if text else "") + f"Chart type: {kind}\nRoles now: {drawn}\n"
                    + "Columns:\n" + lines)
    known = {c["name"] for c in cols}
    out["roles"] = {r: c for r, c in (out.get("roles") or {}).items() if r in ("cat", "series", "t", "v", "v2") and c in known}
    out["columns"] = {k: str(v)[:40] for k, v in (out.get("columns") or {}).items() if k in known}
    out["title"] = str(out.get("title") or "")[:90]
    out["unit"] = str(out.get("unit") or "")[:8]
    return out


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def end_headers(self):
        # browsers must check back before reusing the page or its code, so a deploy is never half seen
        if self.command in ("GET", "HEAD") and not self.path.startswith("/geo/"):
            self.send_header("Cache-Control", "no-cache")
        if self.path.startswith("/geo/"):  # downloaded HTML charts fetch their outlines from here
            self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            b = (ROOT / "index.html").read_text().replace("__VERSION__", VERSION).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        if self.path == "/api/version":
            return self.send(200, {"version": VERSION})
        return super().do_GET()

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
                return self.send(200, names(text, body.get("columns") or [], body.get("kind", ""), body.get("roles") or {}))
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
