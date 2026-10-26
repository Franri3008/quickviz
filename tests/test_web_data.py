import json
import unittest

from app.web_data import web_chart


def response(rows, searches=1, annotations=None, timeline=None):
    return {
        "choices": [{"message": {
            "content": json.dumps({"title": "Population", "xLabel": "Country", "yLabel": "People",
                                   "unit": "", "rows": rows, "timeline": timeline or {"mode": "none", "rows": []}}),
            "annotations": annotations if annotations is not None else [
                {"type": "url_citation", "url_citation": {"url": "https://example.org/data", "title": "Data"}}],
        }}],
        "usage": {"server_tool_use_details": {"web_search_requests": searches}},
        "model": "google/gemini-test",
    }


class WebDataTests(unittest.TestCase):
    def test_accepts_cited_numeric_rows_and_uses_search_tool(self):
        request = {}

        def call(path, body, timeout):
            request.update(path=path, body=body, timeout=timeout)
            return response([{"cat": "A", "v": 10}, {"cat": "B", "v": 12}])

        result = web_chart("population", "bar", call, "google/gemini-test")
        self.assertEqual(request["path"], "/api/v1/chat/completions")
        self.assertEqual(request["body"]["tools"][0]["type"], "openrouter:web_search")
        self.assertEqual(request["body"]["tool_choice"], "required")
        self.assertEqual(request["body"]["reasoning"]["effort"], "minimal")
        self.assertEqual(request["body"]["tools"][0]["parameters"]["max_results"], 3)
        self.assertFalse(result["spec"]["mock"])
        self.assertEqual(result["spec"]["rows"][0], {"cat": "A", "v": 10})
        self.assertEqual(result["sources"][0]["url"], "https://example.org/data")

    def test_event_timeline_adds_consistent_cumulative_line(self):
        data = response([{"cat": "Brazil", "v": 2}, {"cat": "Germany", "v": 1}], timeline={
            "mode": "events", "rows": [
                {"t": "1950", "series": "Brazil", "v": 1},
                {"t": "1954", "series": "Germany", "v": 1},
                {"t": "1958", "series": "Brazil", "v": 1},
            ]})
        result = web_chart("world cups", "bar", lambda *args, **kwargs: data, "google/gemini-test")
        line = result["alternatives"]["line"]
        self.assertFalse(line["mock"])
        self.assertEqual(line["rows"][-2:], [
            {"t": "1958", "series": "Brazil", "v": 2},
            {"t": "1958", "series": "Germany", "v": 1},
        ])

    def test_rejects_unsourced_or_empty_results(self):
        cases = [
            response([{"cat": "A", "v": 10}, {"cat": "B", "v": 12}], searches=0),
            response([{"cat": "A", "v": 10}, {"cat": "B", "v": 12}], annotations=[]),
            response([{"cat": "A", "v": 10}]),
            response([{"cat": "A", "v": "10"}, {"cat": "B", "v": 12}]),
        ]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                web_chart("population", "bar", lambda *args, **kwargs: data, "google/gemini-test")



import httpx  # noqa: E402
import pytest  # noqa: E402

from app import guard, llm, mock  # noqa: E402

JEV = {"answers": {"answer": {"choice": "line", "confidence": 0.8, "probabilities": {"line": 0.8, "bar": 0.15, "pie": 0.05}},
                   "chartable": {"noul": 0.97}, "web_data": {"noul": 0.82}}, "usage": {"cost": 0.002}}
FILL = {"choices": [{"message": {"content": 'Sure {"title": "Coffee prices", "x": "Month", "y": "Price", "unit": "$", '
                                            '"categories": ["Arabica", "Robusta"], "range": [1, 4], "number": "decimal"}'}}],
        "model": "google/gemini-3.8-flash", "usage": {"cost": 0.001}}


@pytest.fixture
def model(monkeypatch):
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append((request.url.path, body))
        if request.url.path == mock.DECISIONS:
            return httpx.Response(200, json=JEV)
        if "tools" in body:
            return httpx.Response(200, json={**response([{"cat": "Brazil", "v": 5}, {"cat": "Germany", "v": 4}]), "usage": {
                "cost": 0.004, "server_tool_use_details": {"web_search_requests": 1}}})
        return httpx.Response(200, json=FILL)

    monkeypatch.setattr(llm, "transport", httpx.MockTransport(handler))
    monkeypatch.setattr(mock, "LIMIT", mock.RateLimit({"pick": 2, "fill": 5, "web": 5}))
    monkeypatch.setattr(mock, "WEB_CACHE", mock.WebCache())
    return sent


def test_pick_route_asks_jev_three_questions_and_drops_kinds_it_cannot_draw(client, model):
    r = client.post("/api/pick", json={"text": "coffee prices since 2015"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["choice"] == "line" and j["ranked"][0] == ["line", 0.8] and all(k != "pie" for k, _ in j["ranked"])
    assert j["chartable"] == 0.97 and j["web_data"] == 0.82
    assert set(model[0][1]["questions"]) == {"answer", "chartable", "web_data"}


def test_fill_route_returns_clean_labels(client, model):
    r = client.post("/api/fill", json={"text": "coffee prices since 2015", "kind": "line"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["title"] == "Coffee prices" and j["range"] == [1, 4] and j["categories"] == ["Arabica", "Robusta"]
    assert model[0][1]["models"] == mock.FILL_MODELS


def test_web_data_route_is_sourced_and_cached(client, model):
    one = client.post("/api/web-data", json={"text": "world cup wins by country", "kind": "bar"}).json()
    two = client.post("/api/web-data", json={"text": "World cup wins by country ", "kind": "bar"}).json()
    assert one["spec"]["mock"] is False and one["sources"][0]["url"] == "https://example.org/data"
    assert one["cached"] is False and two["cached"] is True and len(model) == 1


def test_mock_routes_refuse_short_text_bad_kinds_and_floods(client, model):
    assert client.post("/api/pick", json={"text": "ab"}).status_code == 400
    assert client.post("/api/web-data", json={"text": "coffee", "kind": "pie"}).status_code == 422
    codes = [client.post("/api/pick", json={"text": "coffee"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post("/api/pick", json={"text": "coffee"})
    assert r.json()["detail"]["reason"] == "rate" and r.json()["detail"]["retry_after"] > 0
    assert len(model) == 2


def test_mock_routes_count_in_the_site_spend(client, model):
    client.post("/api/pick", json={"text": "coffee prices"})
    client.post("/api/fill", json={"text": "coffee prices", "kind": "line"})
    client.post("/api/web-data", json={"text": "world cup wins", "kind": "bar"})
    assert guard.summary()["spent_usd"] == 0.007
