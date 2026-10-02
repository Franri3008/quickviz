import json
import math
import re
from collections import Counter
from urllib.parse import urlparse


FIELDS = {
    "bar": ("cat", "v"), "treemap": ("cat", "v"), "donut": ("cat", "v"),
    "map": ("cat", "v"), "line": ("t", "v"),
    "stacked_area": ("t", "series", "v"),
    "stacked_bar": ("cat", "series", "v"),
    "heatmap": ("cat", "series", "v"),
    "sankey": ("cat", "series", "v"),
    "dot_range": ("cat", "series", "v"),
    "scatter": ("v", "v2"), "histogram": ("v",),
    "bump": ("t", "cat", "v"),
}

PROMPT = """You must call the web search tool before answering, even if you know the topic from memory. Search the web for real numeric observations that answer the user's chart request. Use figures stated in the sources. Do not invent, interpolate, extrapolate, or estimate values. Prefer an authoritative primary source and keep units and time periods consistent. If you cannot find enough actual numbers, return an empty rows array.

Return only one JSON object with title, xLabel, yLabel, unit, rows, and timeline. The chart kind is {kind}. Each main row must use these exact keys: {fields}. Each v or v2 must be a JSON number, not formatted text. For line charts, series is optional. For scatter charts, series is optional. Return 2 to 40 main observations, or rows: [] if unavailable.

When the request covers a time span and the sources contain dated observations, include timeline as {{"mode":"values","rows":[{{"t":"2015","series":"item name","v":12.3}}]}}. If the main chart counts dated events by category, such as tournament titles by country, instead use mode "events" and list each dated event once with t=event year, series=the same category name used in the main rows, and v=1. Include the complete event list supported by the sources, not made-up years. If no reliable dated observations are available, use {{"mode":"none","rows":[]}}. The timeline must describe the same measure as the main rows. Keep labels concise. Do not include markdown."""


def _url(value):
    try:
        parsed = urlparse(value)
        return value if parsed.scheme in ("http", "https") and parsed.netloc else None
    except (TypeError, ValueError):
        return None


def _sources(annotations):
    seen = set()
    sources = []
    for annotation in annotations or []:
        if not isinstance(annotation, dict):
            continue
        citation = annotation.get("url_citation") or annotation
        if not isinstance(citation, dict):
            continue
        url = _url(citation.get("url"))
        if url and url not in seen:
            seen.add(url)
            sources.append({"url": url, "title": str(citation.get("title") or urlparse(url).netloc)[:100]})
    return sources[:5]


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Web search returned values that are not numeric")
    return value


def _line_alternative(result, spec):
    timeline = result.get("timeline") or {}
    if not isinstance(timeline, dict) or spec["kind"] == "line":
        return None
    raw_rows = timeline.get("rows")
    if not isinstance(raw_rows, list) or not 3 <= len(raw_rows) <= 80:
        return None
    mode = timeline.get("mode")
    observations = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            return None
        t = str(raw.get("t") or "").strip()[:40]
        series = str(raw.get("series") or "").strip()[:90]
        v = raw.get("v")
        if not t or not series or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        observations.append({"t": t, "series": series, "v": v})
    times = sorted({row["t"] for row in observations})
    if len(times) < 3:
        return None
    if mode == "events":
        if any(row["v"] != 1 for row in observations):
            return None
        totals = Counter(row["series"] for row in observations)
        if {row["cat"]: row["v"] for row in spec["rows"] if "cat" in row} != dict(totals):
            return None
        series = [row["cat"] for row in spec["rows"]]
        cumulative = Counter()
        line_rows = []
        for t in times:
            cumulative.update(row["series"] for row in observations if row["t"] == t)
            line_rows.extend({"t": t, "series": name, "v": cumulative[name]} for name in series)
        title = "Cumulative " + spec["title"]
    elif mode == "values":
        line_rows = observations
        title = spec["title"] + " over time"
    else:
        return None
    return {"kind": "line", "title": title[:90], "xLabel": "Year", "yLabel": spec["yLabel"],
            "unit": spec["unit"], "mock": False, "rows": line_rows}


def web_chart(text, kind, openrouter, model):
    if kind not in FIELDS:
        raise ValueError("Unsupported chart type for web data")
    required = FIELDS[kind]
    fields = ", ".join(required + (("series",) if kind in ("line", "scatter") else ()))
    data, cached = openrouter("/api/v1/chat/completions", {
        "model": model,
        "max_tokens": 2800,
        "temperature": 0,
        "reasoning": {"effort": "minimal"},
        "tool_choice": "required",
        "tools": [{"type": "openrouter:web_search", "parameters": {
            "engine": "exa", "max_results": 3, "max_total_results": 6, "max_characters": 3000,
        }}],
        "messages": [
            {"role": "system", "content": PROMPT.format(kind=kind, fields=fields)},
            {"role": "user", "content": text[:2000]},
        ],
    }, timeout=65)
    message = data["choices"][0]["message"]
    usage = data.get("usage") or {}
    searches = usage.get("server_tool_use_details") or usage.get("server_tool_use") or {}
    sources = _sources(message.get("annotations"))
    if searches.get("web_search_requests", 0) < 1 or not sources:
        raise ValueError("Web search returned no citable sources")
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise ValueError("Web search returned no chart data")
    result = json.loads(match.group(0))
    if not isinstance(result, dict) or not str(result.get("title") or "").strip():
        raise ValueError("Web search returned no chart title")
    raw_rows = result.get("rows")
    if not isinstance(raw_rows, list) or not 2 <= len(raw_rows) <= 40:
        raise ValueError("Could not find enough sourced data points for this chart")
    rows = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError("Web search returned invalid chart rows")
        row = {}
        for field in required:
            if field in ("v", "v2"):
                row[field] = _number(raw.get(field))
            else:
                value = str(raw.get(field) or "").strip()
                if not value:
                    raise ValueError("Web search returned incomplete chart rows")
                row[field] = value[:90]
        if kind in ("line", "scatter") and raw.get("series"):
            row["series"] = str(raw["series"])[:90]
        rows.append(row)
    spec = {"kind": kind, "mock": False, "rows": rows}
    for field in ("title", "xLabel", "yLabel", "unit"):
        spec[field] = str(result.get(field) or "")[:90]
    line = _line_alternative(result, spec)
    return {"spec": spec, "alternatives": {"line": line} if line else {}, "sources": sources,
            "model": data.get("model") or model, "cached": cached}
