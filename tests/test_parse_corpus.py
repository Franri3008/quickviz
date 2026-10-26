import json
import math
from pathlib import Path

import pytest

from app.viz_parse import parse_file

CORPUS = Path(__file__).resolve().parent / "parse_corpus"
CASES = sorted(p.name[: -len(".expected.json")] for p in CORPUS.glob("*.expected.json"))


def same(got, want):
    if want is None:
        return got is None or got == ""
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        if not isinstance(got, (int, float)) or isinstance(got, bool):
            return False
        return math.isclose(got, want, rel_tol=1e-6, abs_tol=1e-9)
    return got is not None and str(got) == str(want)


def check(name):
    exp = json.loads((CORPUS / f"{name}.expected.json").read_text(encoding="utf-8"))
    out = parse_file((CORPUS / name).read_bytes(), name)
    problems = []
    if exp.get("needs_ai"):
        conf = out.get("reading", {}).get("confidence", 1)
        if conf >= 0.7:
            problems.append(f"needs_ai but confidence {conf}")
        return problems
    if exp.get("sheet") and out.get("sheet") != exp["sheet"]:
        problems.append(f"sheet {out.get('sheet')!r} != {exp['sheet']!r}")
    got_cols = [[c["name"], c["type"]] for c in out["columns"]]
    if got_cols != exp["columns"]:
        problems.append(f"columns {got_cols} != {exp['columns']}")
    if out["n_rows"] != exp["n_rows"]:
        problems.append(f"n_rows {out['n_rows']} != {exp['n_rows']}")
    names = [c["name"] for c in out["columns"]]
    rows = [dict(zip(names, r)) for r in out["rows"]]
    for spot in exp["rows"]:
        if not any(all(k in r and same(r[k], v) for k, v in spot.items()) for r in rows):
            problems.append(f"row not found {spot}")
    aggs = set(out.get("aggregates", []))
    for a in exp.get("aggregates", []):
        if a not in aggs:
            problems.append(f"aggregate missing {a!r}")
    for a in exp.get("not_aggregates", []):
        if a in aggs:
            problems.append(f"wrong aggregate {a!r}")
    return problems


@pytest.mark.parametrize("name", CASES)
def test_corpus(name):
    problems = check(name)
    assert not problems, "\n".join(problems[:12])


if __name__ == "__main__":
    ok = 0
    for n in CASES:
        try:
            p = check(n)
        except Exception as e:
            p = [f"error {type(e).__name__}: {e}"]
        ok += not p
        print(("PASS " if not p else "FAIL ") + n + ("" if not p else "\n    " + "\n    ".join(x[:300] for x in p[:6])))
    print(f"{ok}/{len(CASES)} pass")


def test_empty_echo_of_earlier_keys_is_not_a_continuation():
    from app.viz_parse import parse_file
    out = parse_file((Path(__file__).resolve().parents[1] / "samples" / "MOCK_energy_imports_wide.xlsx").read_bytes(), "MOCK_energy_imports_wide.xlsx")
    years = [r[0] for r in out["rows"]]
    assert len(years) == 25 and len(set(years)) == 25
