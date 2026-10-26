import json
import re
import time
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import guard, viz_reading
from app.llm import DEFAULT_REASONING, Visitor, openrouter, visitor
from app.viz_chat import STYLE_PROMPT, ChangeError, _norm, KINDS, build_messages, dropped_error, extract_json, honest_reply, validate_change
from app.viz_parse import ParseError

ROOT = Path(__file__).resolve().parents[1]
STYLE = "franri"
REDRAW_CALLS = 3
NO_LOGO = "These charts have no logo, so nothing changed."
NO_LOGO_RULE = "logo: these charts have no logo. Never set logo. When asked to add, remove or move a logo, change nothing and reply that these charts have no logo."
PRESETS = json.loads((ROOT / "web" / "presets.json").read_text())
MAX_COLUMNS = 30

router = APIRouter(prefix="/api/viz")


class VizSettings(BaseSettings):
    chat_model: str = "anthropic/claude-haiku-5.5"
    label_models: str = "anthropic/claude-haiku-5.5,google/gemini-3.8-flash"
    jev_model: str = "typesafe/jev-1.13"
    redraw_model: str = "anthropic/claude-haiku-5.5"
    max_upload_bytes: int = 5 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def settings() -> VizSettings:
    return VizSettings()


def _models(primary: str, fallbacks: str = "") -> list[str]:
    out = []
    for m in [primary] + fallbacks.split(","):
        m = m.strip()
        if m and m not in out:
            out.append(m)
    return out


def _cost(data: dict):
    c = (data.get("usage") or {}).get("cost") if isinstance(data, dict) else None
    return c if isinstance(c, (int, float)) else None


def _content(data: dict) -> str:
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content


class Column(BaseModel):
    name: str = Field(max_length=200)
    type: str = Field("category", max_length=20)
    distinct: int = 0
    samples: list = Field(default_factory=list, max_length=10)
    values: list | None = Field(None, max_length=80)
    min: float | None = None
    max: float | None = None


class DecideIn(BaseModel):
    text: str = Field("", max_length=2000)
    columns: list[Column] = Field(max_length=200)
    file: str = Field("", max_length=200)
    sheet: str = Field("", max_length=200)


class NameFilter(BaseModel):
    column: str = Field(max_length=200)
    value: str = Field(max_length=200)
    reader: bool = False
    options: list[str] = Field(default_factory=list, max_length=24)


class NamesIn(BaseModel):
    text: str = Field("", max_length=2000)
    columns: list[Column] = Field(max_length=200)
    kind: str = Field("", max_length=30)
    roles: dict[str, str] = Field(default_factory=dict)
    file: str = Field("", max_length=200)
    filters: list[NameFilter] = Field(default_factory=list, max_length=12)
    years: list[int] = Field(default_factory=list, max_length=400)
    data_years: list[int] = Field(default_factory=list, max_length=400)


class ChatTurn(BaseModel):
    role: str = Field(max_length=20)
    text: str = Field("", max_length=2000)


class PatchError(BaseModel):
    code: str = Field(max_length=5000)
    error: str = Field("", max_length=600)


class NoEffect(BaseModel):
    change: dict = Field(default_factory=dict)
    detail: str = Field("", max_length=1600)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=600)
    recipe: dict
    columns: list[Column] = Field(max_length=200)
    sample: list[list] = Field(default_factory=list, max_length=10)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    chart_rows: list[dict] = Field(default_factory=list, max_length=20)
    chart_names: list[str] = Field(default_factory=list, max_length=200)
    outline: str = Field("", max_length=12000)
    patch_error: PatchError | None = None
    no_effect: NoEffect | None = None


@router.post("/parse")
async def parse(request: Request, name: str = "data.csv", sheet: str | None = None, user: Visitor = Depends(visitor)):
    raw = await request.body()
    if len(raw) > settings().max_upload_bytes:
        raise HTTPException(413, detail=f"The file is over {settings().max_upload_bytes // (1024 * 1024)} MB")
    if not raw:
        raise HTTPException(422, detail="The file is empty")
    s = settings()
    try:
        out = await viz_reading.read(user, raw, name[:200], sheet, _models(*s.label_models.split(",", 1)))
    except ParseError as e:
        raise HTTPException(422, detail=str(e))
    return out


@router.post("/redraw")
async def redraw(request: Request, name: str = "chart.png", user: Visitor = Depends(visitor)):
    raw = await request.body()
    if len(raw) > settings().max_upload_bytes:
        raise HTTPException(413, detail=f"The picture is over {settings().max_upload_bytes // (1024 * 1024)} MB")
    if not raw:
        raise HTTPException(422, detail="The picture is empty")
    if viz_reading.picture_type(raw) is None:
        raise HTTPException(422, detail="That picture is not a PNG or JPG.")
    user.prepaid = user.reserve("/api/viz/redraw", REDRAW_CALLS)
    try:
        return await viz_reading.redraw(user, raw, name[:200], settings().redraw_model.strip())
    finally:
        guard.release(user.prepaid)


class RereadIn(BaseModel):
    file_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")
    sheet: str | None = Field(None, max_length=200)
    recipe: dict | None = None
    header_row: int | None = Field(None, ge=0, le=200_000)


@router.post("/reread")
async def reread(body: RereadIn, user: Visitor = Depends(visitor)):
    if (body.recipe is None) == (body.header_row is None):
        raise HTTPException(400, detail="Send a recipe or a header row")
    if body.recipe is not None and len(json.dumps(body.recipe)) > 40_000:
        raise HTTPException(413, detail="That reading is too large")
    try:
        return await viz_reading.reread(user, body.file_id, body.sheet, body.recipe, body.header_row)
    except ParseError as e:
        raise HTTPException(422, detail=str(e))


COLUMN_ROLES = {
    "name": "names or labels of the items being compared, such as country, product or company",
    "value": "the numbers to plot, such as amount, rate, count or price",
    "time": "dates, years, months, quarters or other time steps",
    "group": "a sub-group that splits the data, such as region, type, gender or scenario",
    "ignore": "not useful for the chart, such as IDs, codes, notes or free text",
}


def _ranked(a: dict):
    return sorted((a.get("probabilities") or {}).items(), key=lambda kv: -kv[1])


def _clean_name(s: str) -> str:
    return re.sub(r"[\x00-\x1f\"]", " ", s or "").strip()[:120]


def file_context(file: str, sheet: str = "") -> str:
    file, sheet = _clean_name(file), _clean_name(sheet)
    out = (f"The file is called {file}. " if file else "") + (f"The sheet is called {sheet}. " if sheet else "")
    return out + "The name may hint at what the data shows, but the columns matter most.\n" if out else ""


@router.post("/decide")
async def decide(body: DecideIn, user: Visitor = Depends(visitor)):
    t0 = time.time()
    cols = [c for c in body.columns if c.name.strip()][:MAX_COLUMNS]
    if not cols:
        raise HTTPException(400, detail="No columns")
    summary = "; ".join(
        f"{c.name} ({c.type}, {c.distinct} distinct, e.g. " + ", ".join(str(x)[:20] for x in c.samples[:3]) + ")" for c in cols)
    ctx = (f"The user says: {body.text[:1500]}\n" if body.text.strip() else "") + file_context(body.file, body.sheet) + f"The data has these columns: {summary}.\n"
    qs = {"kind": {
        "type": "choice",
        "instructions": "A user describes the data they have. Pick the chart type that best shows it.\n\n" + ctx,
        "criteria": {p["id"]: p["description"] for p in PRESETS},
    }}
    for i, c in enumerate(cols):
        qs[f"col{i}"] = {"type": "choice", "criteria": COLUMN_ROLES,
                         "instructions": ctx + f"What role does the column \"{c.name[:80]}\" play in a chart of this data?"}
    data = await openrouter(user, "/api/alpha/decisions", {"model": settings().jev_model, "state": "", "questions": qs}, timeout=30)
    ans = data.get("answers", {}) if isinstance(data, dict) else {}
    k = ans.get("kind", {})
    out_cols = {}
    for i, c in enumerate(cols):
        a = ans.get(f"col{i}", {})
        out_cols[c.name] = {"role": a.get("choice"), "confidence": a.get("confidence"), "ranked": _ranked(a)}
    choice = k.get("choice") if k.get("choice") in KINDS else "bar"
    return {"choice": choice, "confidence": k.get("confidence"), "ranked": [r for r in _ranked(k) if r[0] in KINDS],
            "columns": out_cols, "ms": round((time.time() - t0) * 1000), "cost": _cost(data)}


NAME_PROMPT = """You check a chart before it is shown. The user describes their data. You get the chart type,
which column fills each role, and every column with sample values.
Roles: cat = the items compared or the source of a flow, series = the sub-groups or the target of a flow,
t = time on the x axis, v = the main number, v2 = the second number of a scatter.
Fix the role mapping if it is wrong, e.g. a flow drawn backwards or the wrong number chosen. Leave it out if it is right.
Reply with JSON only, no prose, in this shape:
{"roles": only the roles you would change, as {"<role>": "<exact column name>"}, or {},
"title": a short chart title in sentence case, at most 8 words, no final period. Name the measure. It must be true for exactly the rows drawn.
  Name only the years drawn: one year as ", 2025", several as ", 2021 to 2025". Never name a year that is not drawn.
  A filter the reader can change is switched by a dropdown on the chart, and a note under the chart names the pick.
  So the title must stay true for every option of that dropdown. Never name the pick or any other option, and never describe them in other words.
  For example with answer = "Uses AI now" switchable to "Plans to use AI", write "Firms and AI use, by sector", not "Firms using AI now, by sector",
"unit": the unit symbol of the main numeric value, such as "%", "$", "€" or "bcm", or "",
"columns": {"<each exact column name>": a short readable label in sentence case, at most 4 words, with the unit in brackets only if it has one, never the column type}}
Never use the characters ≥ ≤ → or a middle dot."""


def span_text(years: list[int]) -> str:
    return "" if not years else str(years[0]) if years[0] == years[-1] else f"{years[0]} to {years[-1]}"


YEAR_RANGE = re.compile(r"\b((?:18|19|20|21)\d{2})(\s*(?:to|until|through|-|–|—)\s*)((?:18|19|20|21)\d{2})\b")
YEAR_ONE = re.compile(r"(\b(?:since|from|after)\s+)?\b((?:18|19|20|21)\d{2})\b(?!\s*(?:to|until|through|-|–|—)\s*\d)", re.I)


def true_years(title: str, years: list[int], data_years: list[int] | None = None) -> str:
    years = sorted(set(years or []))
    if not title or not years:
        return title
    lo, hi, span = years[0], years[-1], span_text(years)
    known = set(data_years or []) or None

    def ok(y: int) -> bool:
        return known is None or y in known

    def rng(m):
        a, b = int(m.group(1)), int(m.group(3))
        return span if (ok(a) or ok(b)) and (a != lo or b != hi) else m.group(0)

    out = YEAR_RANGE.sub(rng, title)

    def one(m):
        y, pre = int(m.group(2)), m.group(1)
        if not ok(y) or re.search(r"(?:to|until|through|-|–|—)\s*$", m.string[:m.start(2)]):
            return m.group(0)
        if pre:
            return m.group(0) if y == lo else pre + str(lo)
        return m.group(0) if len(years) == 1 and y == lo else span

    return YEAR_ONE.sub(one, out)


@router.post("/names")
async def names(body: NamesIn, user: Visitor = Depends(visitor)):
    t0 = time.time()
    cols = [c for c in body.columns if c.name.strip()][:MAX_COLUMNS]
    lines = "\n".join(f"- {c.name} ({c.type}), e.g. " + ", ".join(str(x)[:30] for x in c.samples[:3]) for c in cols)
    drawn = ", ".join(f"{r}={c}" for r, c in body.roles.items())
    picked = "; ".join(f"{_clean_name(f.column)} = {_clean_name(f.value)}"
                       + (" (the reader can switch it to " + ", ".join(_clean_name(o)[:60] for o in f.options[:12] if o != f.value) + ")" if f.reader and f.options
                          else " (the reader can change it)" if f.reader else "") for f in body.filters)
    years = sorted(set(body.years))
    user_msg = ((f"The user says: {body.text}\n" if body.text.strip() else "") + (f"File name: {body.file}\n" if body.file else "")
                + f"Chart type: {body.kind}\nRoles now: {drawn}\n"
                + (f"Only these rows are drawn: {picked}\n" if picked else "")
                + (f"Years drawn: {span_text(years)}\n" if years else "")
                + "Columns:\n" + lines)
    s = settings()
    msgs = [{"role": "system", "content": NAME_PROMPT}, {"role": "user", "content": user_msg[:4000]}]
    switchable = [v for f in body.filters if f.reader for v in [f.value, *f.options] if len(_norm(v)) > 2]
    cost = 0.0
    for attempt in range(2):
        data = await openrouter(user, "/api/v1/chat/completions", {
            "models": _models(*s.label_models.split(",", 1)), "max_tokens": 700, "temperature": 0.2,
            "reasoning": DEFAULT_REASONING, "provider": {"sort": "latency"}, "messages": msgs,
        }, timeout=20)
        cost += _cost(data) or 0.0
        raw = _content(data)
        try:
            out = extract_json(raw)
        except ChangeError:
            out = {}
        named = [v for v in switchable if _norm(v) in _norm(out.get("title") or "")]
        if not named or attempt:
            break
        msgs = msgs + [{"role": "assistant", "content": raw[:1500]},
                       {"role": "user", "content": f"The title names \"{named[0][:60]}\", which the reader can switch away from. "
                                                   "Reply again with the same JSON and a title that stays true for every option."}]
    known = {c.name for c in cols}
    roles = out.get("roles") if isinstance(out.get("roles"), dict) else {}
    cols_out = out.get("columns") if isinstance(out.get("columns"), dict) else {}
    return {
        "roles": {r: c for r, c in roles.items() if r in ("cat", "series", "t", "v", "v2") and c in known},
        "columns": {k: re.sub(r"[≥≤→·]", "", str(v))[:40] for k, v in cols_out.items() if k in known},
        "title": true_years(re.sub(r"[≥≤→·]", "", str(out.get("title") or ""))[:90].rstrip("."), years, body.data_years),
        "unit": str(out.get("unit") or "")[:8],
        "model": data.get("model"), "ms": round((time.time() - t0) * 1000), "cost": round(cost, 6),
    }


def system_messages(msgs: list[dict]) -> list[dict]:
    text = msgs[0]["content"].replace(STYLE_PROMPT[STYLE]["@@LOGO@@"], NO_LOGO_RULE).replace("for a CEPS researcher", "for a user")
    head = {**msgs[0], "content": text}
    return [head] + msgs[1:]


def no_logo(change: dict, message: str) -> dict:
    asked = change["set"].pop("logo", None) is not None or re.search(r"\blogos?\b", message, re.I)
    if asked and not (change["set"] or change["ops"] or change.get("patch")):
        change["reply"] = NO_LOGO
    return change


@router.post("/chat")
async def chat(body: ChatIn, user: Visitor = Depends(visitor)):
    t0 = time.time()
    s = settings()
    columns = [c.model_dump() for c in body.columns]
    layout = body.recipe.get("layout") if isinstance(body.recipe.get("layout"), dict) else {}
    msgs = system_messages(build_messages(body.message, body.recipe, columns, body.sample, [h.model_dump() for h in body.history],
                                          body.chart_rows, body.chart_names, body.outline, body.patch_error.model_dump() if body.patch_error else None,
                                          body.no_effect.model_dump() if body.no_effect else None, style=STYLE))
    req = {"model": s.chat_model.strip(), "max_tokens": 2400, "temperature": 0.1,
           "reasoning": DEFAULT_REASONING, "response_format": {"type": "json_object"}, "messages": msgs}
    cost, tries, last_err, model = 0.0, 0, "", None
    for attempt in range(2):
        tries += 1
        data = await openrouter(user, "/api/v1/chat/completions", req, timeout=30)
        cost += _cost(data) or 0.0
        model = data.get("model") or model
        raw = _content(data)
        try:
            kind = body.recipe.get("kind")
            change = validate_change(extract_json(raw), columns, body.chart_names, kind=kind, caps=True, style=STYLE, logo=layout.get("logo"))
            dropped = change.pop("dropped", [])
            target = change["set"].get("kind") or kind
            if dropped and attempt == 0:
                raise ChangeError(dropped_error(dropped, target))
            if dropped:
                change["reply"] = honest_reply(change, dropped, target)
            change = no_logo(change, body.message)
            return {**change, "style": STYLE, "model": model, "ms": round((time.time() - t0) * 1000), "cost": round(cost, 6), "tries": tries,
                    "retry_reason": last_err[:300]}
        except ChangeError as e:
            last_err = str(e)
            req = {**req, "messages": msgs + [
                {"role": "assistant", "content": raw[:1500] or "(empty)"},
                {"role": "user", "content": f"That reply could not be used: {last_err}\nReply again with one valid JSON object only."},
            ]}
    raise HTTPException(422, detail={"reason": "bad_change", "message": "The assistant's answer did not fit, so nothing changed. Try saying it another way.",
                                      "error": last_err[:300], "cost": round(cost, 6)})
