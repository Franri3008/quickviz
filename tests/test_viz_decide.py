import json

import httpx

from app import llm
from app.viz import file_context

COLS = [{"name": "country", "type": "category", "distinct": 31, "samples": ["Austria"]},
        {"name": "rd_spending_pct_gdp", "type": "number", "distinct": 31, "samples": [3.59]},
        {"name": "ai_patents_per_million", "type": "number", "distinct": 31, "samples": [242.4]}]


def fake_jev(monkeypatch):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"answers": {"kind": {"choice": "scatter", "confidence": 0.8, "probabilities": {"scatter": 0.8, "bar": 0.2}}},
                                         "usage": {"cost": 1e-05}, "id": "gen-dec"})

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    return sent


def test_file_context_is_a_hint():
    out = file_context("MOCK_rd_spending_vs_ai_patents.csv", "")
    assert out.startswith("The file is called MOCK_rd_spending_vs_ai_patents.csv. ")
    assert "hint" in out and "sheet" not in out


def test_file_context_with_sheet_and_cleaning():
    out = file_context('flows"\n.xlsx', "Net balance")
    assert "The sheet is called Net balance." in out
    assert '"' not in out.split("\n")[0]


def test_file_context_empty():
    assert file_context("", "") == ""


def test_decide_sends_file_and_sheet(client, monkeypatch):
    c = client
    sent = fake_jev(monkeypatch)
    r = c.post("/api/viz/decide", json={"text": "", "columns": COLS, "file": "MOCK_rd_spending_vs_ai_patents.csv", "sheet": "Data"})
    assert r.status_code == 200, r.text
    assert r.json()["choice"] == "scatter"
    qs = sent[0]["questions"]
    assert "The file is called MOCK_rd_spending_vs_ai_patents.csv. The sheet is called Data." in qs["kind"]["instructions"]
    assert "The file is called" in qs["col0"]["instructions"]


def test_decide_without_file_has_no_name_line(client, monkeypatch):
    c = client
    sent = fake_jev(monkeypatch)
    assert c.post("/api/viz/decide", json={"text": "", "columns": COLS}).status_code == 200
    assert "The file is called" not in sent[0]["questions"]["kind"]["instructions"]
