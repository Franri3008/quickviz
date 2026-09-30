"""Check Jev picks the intended kind for each demo in demo/demos.json. Standard library only.
Sends the same text app.js sends once the CSV is loaded (description + column summary),
and also the bare description (what Jev sees while the user types). Usage: python3 tests/demo_check.py [runs]"""
import csv, json, re, sys
from pathlib import Path
sys.argv, runs = sys.argv[:1], int(sys.argv[1]) if len(sys.argv) > 1 else 3
sys.path.insert(0, str(Path(__file__).parent))
from eval import pick, ROOT  # noqa: E402

WANT = {"youth_unemployment.csv": "line", "eu_gas_imports.csv": "sankey", "rd_vs_patents.csv": "scatter"}
TIME_NAME = re.compile(r"^(year|yr|date|month|time|quarter|qtr|week|day|period|season|fy|timestamp|datetime|hour)s?$|(_|\b)(year|date|month|quarter|week|day|period|season|time)$", re.I)


def is_num(s):
    try:
        float(s.replace(",", "").replace("%", "")); return True
    except ValueError:
        return False


def summary(path):
    rows = list(csv.DictReader(open(path)))
    parts = []
    for name in rows[0]:
        vals = [r[name] for r in rows if r[name] != ""]
        typ = "time" if TIME_NAME.search(name) else "number" if all(is_num(v) for v in vals) else "category"
        samples = list(dict.fromkeys(vals))[:3]
        parts.append(f"{name} ({typ}, {len(set(vals))} distinct, e.g. {', '.join(s[:20] for s in samples)})")
    return f"{len(rows)} rows. Columns: " + "; ".join(parts) + "."


demos = json.loads((ROOT / "demo/demos.json").read_text())
for dm in demos:
    want = WANT[dm["csv"]]
    for label, text in [("with data", dm["description"] + "\n\nThe data: " + summary(ROOT / "demo" / dm["csv"])),
                        ("text only", dm["description"])]:
        got = [pick(text) for _ in range(runs)]
        hits = sum(g["choice"] == want for g in got)
        print(f"{dm['name']:<42} {label:<9} want {want:<8} {hits}/{runs}  picks {[g['choice'] for g in got]}"
              f"  top {[(k, round(v, 2)) for k, v in got[0]['top']]}")
