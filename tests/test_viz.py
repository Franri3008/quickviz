import io

import pytest

from app.viz_chat import ChangeError, build_messages, extract_json, validate_change
from app.viz_parse import ParseError, parse_file

COLUMNS = [
    {"name": "country", "type": "category", "distinct": 3, "values": ["Spain", "EU27_2020", "Belgium"]},
    {"name": "year", "type": "time", "distinct": 4, "values": ["2021", "2022", "2023", "2024"]},
    {"name": "rate", "type": "number", "distinct": 12, "min": 1.0, "max": 40.0},
]


def test_csv_semicolon_decimal_comma():
    raw = "pays;annee;valeur\nBelgique;2020;1.234,5\nFrance;2020;987,25\n".encode("cp1252")
    out = parse_file(raw, "x.csv")
    assert [c["type"] for c in out["columns"]] == ["category", "time", "number"]
    assert out["rows"][0][2] == 1234.5


def test_xlsx_title_rows_source_and_melt():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Share of enterprises using AI"])
    ws.append([])
    ws.append(["geo", 2022, 2023, 2024])
    ws.append(["Belgium", 10.3, 13.8, 24.7])
    ws.append(["EU27", 8, ":", 13.5])
    ws.append(["Source: Eurostat"])
    buf = io.BytesIO()
    wb.save(buf)
    out = parse_file(buf.getvalue(), "ai.xlsx")
    assert out["melted"] == 3
    assert [c["name"] for c in out["columns"]] == ["geo", "Year", "Value"]
    assert out["source_hint"] == "Eurostat"
    assert ["EU27", "2023", None] not in out["rows"]
    assert len(out["rows"]) == 5


def test_empty_file():
    with pytest.raises(ParseError):
        parse_file(b"", "x.csv")


def test_change_fixes_names_and_values():
    ch = validate_change({"reply": "ok", "set": {"highlight": ["belgium"]},
                          "ops": [{"op": "filter", "column": "Country", "keep": ["eu27 2020", "Spain"]}]}, COLUMNS, ["Spain", "Belgium"])
    assert ch["ops"][0] == {"op": "filter", "column": "country", "keep": ["EU27_2020", "Spain"]}
    assert ch["set"]["highlight"] == ["Belgium"]


def test_change_year_string_bound():
    ch = validate_change({"reply": "ok", "ops": [{"op": "filter", "column": "year", "min": "2022"}]}, COLUMNS, [])
    assert ch["ops"][0]["min"] == 2022.0


@pytest.mark.parametrize("bad", [
    {"reply": "x", "ops": [{"op": "eval", "code": "1"}]},
    {"reply": "x", "set": {"colors": {"Spain": "magenta; x"}}},
    {"reply": "x", "set": {"kind": "pie3d"}},
    {"reply": "x", "ops": [{"op": "filter", "column": "nope", "keep": ["a"]}]},
    {"reply": "x", "ops": [{"op": "filter", "column": "country", "keep": ["France"]}]},
    {"reply": "x", "ops": [{"op": "roles", "v": "country"}]},
    {"reply": "x", "set": {"html": "<script>"}},
])
def test_change_rejects(bad):
    with pytest.raises(ChangeError):
        validate_change(bad, COLUMNS, ["Spain"])


def test_extract_json_from_fenced_reply():
    assert extract_json('```json\n{"reply": "hi"}\n```') == {"reply": "hi"}


def test_messages_carry_no_rows():
    msgs = build_messages("sort it", {"kind": "bar", "rows": [{"cat": "a", "v": 1}]}, COLUMNS, [["Spain", "2021", 3]], [], [], [])
    assert '"rows"' not in msgs[-1]["content"]
