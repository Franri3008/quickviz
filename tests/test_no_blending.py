import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.viz_parse import ParseError, parse_file

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
CORPUS = ROOT / "tests" / "parse_corpus"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")

FILES = ([("samples", p.name) for p in sorted(SAMPLES.iterdir()) if p.suffix in (".csv", ".xlsx", ".tsv", ".json", ".txt")]
         + [("corpus", p.name[: -len(".expected.json")]) for p in sorted(CORPUS.glob("*.expected.json"))])

CHECK = r"""
const d = state.data, problems = [], seen = [];
const close = (a, b) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
for (const kind of KIND_ORDER) {
  let r;
  try { r = fitsKind(kind, {filters: []}); } catch (e) { problems.push(`${kind}: ${e.message}`); continue; }
  if (!r) continue;
  seen.push(kind);
  const s = buildSpec(r), map = r.roles;
  let src = renameRows(dropAggregates(kind, filterRows(d.rows, r.filters), map, r.filters), r.rename);
  if (map.wide) {
    const nm = wideNames(map.wide);
    src = src.flatMap(x => map.wide.map(w => ({...x, "(columns)": nm[w], "(value)": x[w]})));
  }
  const vcol = map.v;
  const num = x => typeof x === "number" && Number.isFinite(x);
  const matches = row => src.filter(x => ["cat", "series", "t"].every(f => !map[f] || row[f] == null || String(x[map[f]] ?? "") === String(row[f])));
  if (kind === "histogram") {
    const vals = new Set(src.map(x => x[vcol]).filter(num));
    const bad = s.rows.filter(row => !vals.has(row.v));
    if (bad.length) problems.push(`${kind}: ${bad.length} values not in the source`);
    continue;
  }
  if (kind === "scatter") {
    const bad = s.rows.filter(row => !matches(row).some(x => x[map.v] === row.v && x[map.v2] === row.v2));
    if (bad.length) problems.push(`${kind}: ${bad.length} points not in the source`);
    if (map.cat) {
      const n = d3.rollup(s.rows, g => g.length, row => JSON.stringify([row.cat, row.series ?? null]));
      const dup = [...n].filter(e => e[1] > 1);
      if (dup.length) problems.push(`${kind}: ${dup.length} items drawn more than once, e.g. ${dup[0][0]}`);
    }
    continue;
  }
  for (const row of s.rows) {
    const m = matches(row);
    if (vcol === "(count)") {
      if (row.v !== m.length && kind !== "bump") { problems.push(`${kind}: count ${row.v} for ${JSON.stringify(row)} but ${m.length} rows`); break; }
      continue;
    }
    const vals = [...new Set(m.map(x => x[vcol]).filter(num))];
    if (kind === "bump") {
      if (vals.length !== 1) { problems.push(`${kind}: ${JSON.stringify([row.t, row.cat])} ranks ${vals.length} source values ${JSON.stringify(vals.slice(0, 4))}`); break; }
      continue;
    }
    if (vals.length !== 1 || !close(vals[0], row.v)) {
      problems.push(`${kind}: ${JSON.stringify({cat: row.cat, series: row.series, t: row.t})} drew ${row.v} from ${vals.length} source values ${JSON.stringify(vals.slice(0, 4))}`);
      break;
    }
  }
}
({seen, problems})
"""


def load(where, name):
    path = (SAMPLES if where == "samples" else CORPUS) / name
    try:
        out = parse_file(path.read_bytes(), name, None)
    except ParseError:
        return None
    names = [c["name"] for c in out["columns"]]
    rows = [{n: ("" if v is None else v) for n, v in zip(names, r)} for r in out["rows"]]
    return {**out, "rows": rows, "cols": out["columns"], "name": name}


def run(data, code):
    setup = f"state.data = {json.dumps(data)}; state.decide = null; state.names = null;\nglobalThis.__countries = {{}};\n"
    r = subprocess.run(["node", str(ROOT / "tests" / "app_harness.js")], input=setup + code, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("where,name", FILES, ids=[f"{w}/{n}" for w, n in FILES])
def test_every_drawn_value_is_one_source_value(where, name):
    data = load(where, name)
    if data is None or not data["rows"]:
        pytest.skip("no table")
    out = run(data, CHECK)
    assert not out["problems"], f"{name} kinds {out['seen']}:\n" + "\n".join(out["problems"][:12])


STRESS = "STRESS_eurostat_style_ai_use_by_size.xlsx"
SIZE = "Size classes in number of persons employed"


def stress():
    return load("samples", STRESS)


def test_stress_bar_keeps_one_size_class_and_year():
    out = run(stress(), f"""
      const r = withAutoControls(fitsKind("bar", {{filters: []}}));
      const s = buildSpec(r);
      const dk = s.rows.find(x => x.cat === "Denmark");
      const ctl = s.controls.map(c => [c.label, c.options, c.initial]);
      const v250 = s.variants[[1, ctl[1][2]].join("-")].rows.find(x => x.cat === "Denmark");
      const v2023 = s.variants[[ctl[0][2], 1].join("-")];
      ({{dk: dk.v, note: s.autoNote, ctl, v250: v250.v, note250: s.variants[[1, ctl[1][2]].join("-")].autoNote, note2023: v2023.autoNote,
        dk2023: v2023.rows.find(x => x.cat === "Denmark").v, filters: r.filters}})
    """)
    assert out["dk"] == 34.01
    assert out["note"] == "Showing: 10 persons employed or more, 2025."
    assert out["ctl"][0][1] == ["From 10 to 249 persons employed", "250 persons employed or more", "10 persons employed or more"]
    assert out["ctl"][0][2] == 2
    assert out["ctl"][1][1] == ["2021", "2023", "2024", "2025"] and out["ctl"][1][2] == 3
    assert out["v250"] == 78
    assert out["note250"] == "Showing: 250 persons employed or more, 2025."
    assert out["note2023"] == "Showing: 10 persons employed or more, 2023."
    assert out["dk2023"] == 14.25
    assert all(f["auto"] for f in out["filters"])


def test_explicit_mean_is_the_true_mean():
    out = run(stress(), f"""
      const r = applyChange(fitsKind("bar", {{filters: []}}), {{ops: [{{op: "aggregate", how: "mean"}}]}});
      const s = buildSpec(r);
      ({{dk: s.rows.find(x => x.cat === "Denmark").v, filters: r.filters.map(f => f.column)}})
    """)
    assert out["filters"] == ["Year"]
    assert abs(out["dk"] - (31.11 + 78) / 2) < 1e-9


def test_percent_share_math():
    out = run(stress(), """
      const r = applyChange(fitsKind("bar", {filters: []}), {ops: [{op: "percent_share", within: "total"}]});
      const plain = buildSpec({...r, percent: null}).rows, s = buildSpec(r).rows;
      const tot = plain.reduce((a, x) => a + Math.abs(x.v), 0);
      s.every(x => Math.abs(x.v - plain.find(p => p.cat === x.cat).v / tot * 100) < 1e-9) && Math.abs(s.reduce((a, x) => a + x.v, 0) - 100) < 1e-9
    """)
    assert out is True


def test_line_by_size_class_and_one_area():
    out = run(stress(), """
      const r = withAutoControls(fitsKind("line", {roles: {series: "Size classes in number of persons employed"}, filters: []}));
      const s = buildSpec(r);
      ({series: [...new Set(s.rows.map(x => x.series))].length, f: r.filters.map(f => [f.column, f.keep[0]]), note: s.autoNote})
    """)
    assert out["series"] == 3
    assert out["f"] == [["GEO", "European Union - 27 countries (from 2020)"]]
    assert out["note"] == "Showing: European Union - 27 countries (from 2020)."


def test_stacked_bar_leaves_out_the_total_size_class():
    out = run(stress(), """
      const s = buildSpec(fitsKind("stacked_bar", {filters: []}));
      [...new Set(s.rows.map(x => x.series))].sort()
    """)
    assert out == ["250 persons employed or more", "From 10 to 249 persons employed"]


def test_kind_switch_keeps_the_picked_value():
    out = run(stress(), f"""
      let r = withAutoControls(fitsKind("bar", {{filters: []}}));
      r = applyChange(r, {{ops: [{{op: "filter", column: "{SIZE}", keep: ["250 persons employed or more"]}}]}});
      const t = applyChange(r, {{set: {{kind: "donut"}}}});
      const l = applyChange(r, {{set: {{kind: "line"}}, ops: [{{op: "roles", series: "{SIZE}"}}]}});
      ({{t: t.filters.map(f => [f.column, f.keep[0]]), l: l.filters.map(f => [f.column, f.keep && f.keep[0]])}})
    """)
    assert ["Size classes in number of persons employed", "250 persons employed or more"] in out["t"]
    assert all(c != "Year" for c, _ in out["l"])


def test_blending_change_is_refused():
    data = load("samples", "MOCK_firm_size_distribution_2000_firms.csv")
    out = run(data, """
      let msg = "";
      try { applyChange(fitsKind("bar", {filters: []}), {ops: [{op: "roles", cat: "sector"}]}); } catch (e) { msg = e.message; }
      const ok = applyChange(fitsKind("bar", {filters: []}), {ops: [{op: "roles", cat: "sector"}, {op: "aggregate", how: "sum"}]});
      ({msg, ok: buildSpec(ok).rows.length})
    """)
    assert "add up or average" in out["msg"]
    assert out["ok"] == 10


def test_totals_found_by_name_and_range():
    out = run(stress(), """
      [defaultPick(["Men", "Women", "Total"]), defaultPick(["Female", "Both sexes", "Male"]), defaultPick(["A", "B"]),
       totalByRange(["10_249", "GE250", "GE10"]), totalByRange(["From 10 to 249 persons employed", "250 persons employed or more", "10 persons employed or more"]),
       totalByRange(["0-14", "15-64", "65 or more"]), defaultPick(["All other sectors", "Manufacturing"])]
    """)
    assert out == ["Total", "Both sexes", "A", "GE10", "10 persons employed or more", None, "All other sectors"]


def test_title_years_follow_the_drawn_rows():
    out = run(stress(), """
      const k = new Set([2021, 2023, 2024, 2025]);
      [trueYears("AI use by enterprise size, 2021 to 2024", {drawn: [2025], known: k}),
       trueYears("AI use by enterprises, 2025", {drawn: [2021, 2023, 2024, 2025], known: k}),
       trueYears("Target for 2030", {drawn: [2025], known: k}),
       trueYears("AI use since 2021", {drawn: [2023, 2025], known: k})]
    """)
    assert out == ["AI use by enterprise size, 2025", "AI use by enterprises, 2021 to 2025", "Target for 2030", "AI use since 2023"]


def test_title_and_note_follow_the_year_control():
    out = run(stress(), """
      state.names = {title: "AI use by enterprises, 2021 to 2024", columns: {}};
      const s = buildSpec(withAutoControls(fitsKind("bar", {filters: []})));
      [s.title, s.variants["2-0"].title, s.variants["2-0"].autoNote]
    """)
    assert out == ["AI use by enterprises, 2025", "AI use by enterprises, 2021", "Showing: 10 persons employed or more, 2021."]


def test_names_gets_filters_and_fixes_years(client, monkeypatch):
    import httpx

    from app import llm

    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        content = json.dumps({"roles": {}, "title": "AI use by enterprise size, 2021 to 2024", "unit": "%", "columns": {}})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {"cost": 1e-05}, "model": "m", "id": "gen-n"})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    c = client
    r = c.post("/api/viz/names", json={"text": "", "kind": "bar", "roles": {"cat": "GEO", "v": "Value"},
                                       "columns": [{"name": "GEO", "type": "category"}, {"name": "Value", "type": "number"}],
                                       "filters": [{"column": SIZE, "value": "10 persons employed or more", "reader": True},
                                                   {"column": "Year", "value": "2025"}],
                                       "years": [2025], "data_years": [2021, 2023, 2024, 2025]})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "AI use by enterprise size, 2025"
    msg = sent[0]["messages"][1]["content"]
    assert "Only these rows are drawn: Size classes in number of persons employed = 10 persons employed or more (the reader can change it); Year = 2025" in msg
    assert "Years drawn: 2025" in msg


def test_names_retries_when_the_title_names_a_switchable_pick(client, monkeypatch):
    import httpx

    from app import llm

    sent = []
    titles = ["Share of firms using AI now, by sector", "Uses AI now by sector", "Firms and AI use, by sector"]

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        content = json.dumps({"roles": {}, "title": titles[1 if len(sent) == 1 else 2], "unit": "%", "columns": {}})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {"cost": 1e-05}, "model": "m", "id": "gen-n"})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    c = client
    r = c.post("/api/viz/names", json={"text": "", "kind": "bar", "roles": {"cat": "sector", "v": "share_of_firms"},
                                       "columns": [{"name": "sector", "type": "category"}, {"name": "share_of_firms", "type": "number"}],
                                       "filters": [{"column": "answer", "value": "Uses AI now", "reader": True,
                                                    "options": ["Uses AI now", "Plans to use AI", "No plans"]}]})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Firms and AI use, by sector"
    assert len(sent) == 2
    assert "answer = Uses AI now (the reader can switch it to Plans to use AI, No plans)" in sent[0]["messages"][1]["content"]
    assert "which the reader can switch away from" in sent[1]["messages"][-1]["content"]
