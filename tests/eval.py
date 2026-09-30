"""Run tests/cases.json against Jev with the current presets.json. Standard library only.
Usage: python3 tests/eval.py [runs] [--set tune|heldout|all] [--file path.json]"""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "typesafe/jev-1.13"


def key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OPENROUTER_API_KEY missing in .env")


KEY = key()
PRESETS = json.loads((ROOT / "presets.json").read_text())


def pick(text):
    body = {"model": MODEL, "state": "", "questions": {"answer": {
        "type": "choice",
        "instructions": "A user describes the data they have. Pick the chart type that best shows it.\n\n" + text[:2000],
        "criteria": {p["id"]: p["description"] for p in PRESETS}}}}
    req = urllib.request.Request("https://openrouter.ai/api/alpha/decisions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    t0 = time.time()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
            break
        except Exception as e:
            if attempt == 2:
                return {"choice": f"ERR {e}", "ms": 0, "cost": 0, "top": [], "probs": {}}
            time.sleep(1.5)
    a = d.get("answers", {}).get("answer", {})
    allp = a.get("probabilities") or {}
    probs = sorted(allp.items(), key=lambda kv: -kv[1])[:3]
    return {"choice": a.get("choice"), "ms": (time.time() - t0) * 1000, "probs": allp,
            "cost": (d.get("usage") or {}).get("cost") or 0, "top": probs}


def main():
    args = sys.argv[1:]
    runs = int(args[0]) if args and args[0].isdigit() else 1
    which = args[args.index("--set") + 1] if "--set" in args else "all"
    path = Path(args[args.index("--file") + 1]) if "--file" in args else ROOT / "tests/cases.json"
    data = json.loads(path.read_text())
    sets = [s for s in data if which in ("all", s)]
    total_cost = 0.0
    for run in range(1, runs + 1):
        for s in sets:
            cases = data[s]
            with ThreadPoolExecutor(8) as ex:
                res = list(ex.map(lambda c: pick(c["text"]), cases))
            hits = [r["choice"] in c["ok"] for c, r in zip(cases, res)]
            ms = [r["ms"] for r in res if r["ms"]]
            total_cost += sum(r["cost"] for r in res)
            p_ok = [sum(r["probs"].get(k, 0) for k in c["ok"]) for c, r in zip(cases, res)]
            print(f"run {run} [{s}] accuracy {sum(hits)}/{len(cases)} = {sum(hits)/len(cases):.0%}"
                  f"  mean p_ok {sum(p_ok)/len(p_ok):.2f}  mean latency {sum(ms)/max(len(ms),1):.0f} ms")
            for c, r, h in zip(cases, res, hits):
                if not h:
                    top = ", ".join(f"{k} {v:.2f}" for k, v in r["top"])
                    print(f"   MISS {c['text']!r}: got {r['choice']}, want {'/'.join(c['ok'])}  [{top}]")
    print(f"total cost ${total_cost:.4f}")


if __name__ == "__main__":
    main()
