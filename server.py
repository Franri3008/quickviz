"""QuickViz: tiny local server. Serves index.html and proxies Jev + a label-filler model on OpenRouter."""
import json, os, re, time, urllib.request, urllib.error
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


def openrouter(path, body, timeout=20):
    req = urllib.request.Request(
        "https://openrouter.ai" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def pick(text):
    t0 = time.time()
    data = openrouter("/api/alpha/decisions", {
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
            "ms": round((time.time() - t0) * 1000), "cost": data.get("usage", {}).get("cost")}


FILL_PROMPT = """The user describes data they have. Invent plausible names for a sample chart of type "{kind}".
Reply with JSON only, no prose, in this shape:
{{"title": short chart title, "x": x-axis or category label, "y": value label, "unit": unit symbol or "",
"categories": 4 to 8 short names for the main items (countries, products, months...),
"series": 2 to 4 short names for sub-groups or stages,
"range": [typical min value, typical max value]}}"""


def fill(text, kind):
    t0 = time.time()
    data = openrouter("/api/v1/chat/completions", {
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
    return out


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            text = (body.get("text") or "").strip()
            if not text:
                return self.send(400, {"error": "empty"})
            if self.path == "/api/pick":
                return self.send(200, pick(text))
            if self.path == "/api/fill":
                return self.send(200, fill(text, body.get("kind", "bar")))
            self.send(404, {"error": "not found"})
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
