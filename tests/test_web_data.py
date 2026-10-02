import unittest

from web_data import web_chart


def response(rows, searches=1, annotations=None, timeline=None):
    import json
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
            return response([{"cat": "A", "v": 10}, {"cat": "B", "v": 12}]), False

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
        result = web_chart("world cups", "bar", lambda *args, **kwargs: (data, False), "google/gemini-test")
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
                web_chart("population", "bar", lambda *args, **kwargs: (data, False), "google/gemini-test")


if __name__ == "__main__":
    unittest.main()
