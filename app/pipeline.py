import logging
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from app import auth, guard, viz, viz_reading
from app.capabilities import say_unused
from app.config import WEB_DIR
from app.llm import Visitor
from app.render import EXPORT_W, RENDERER, RenderError, render_chart
from app.viz_chat import KINDS
from app.viz_parse import ParseError

log = logging.getLogger("quickviz.pipeline")

PIPE_JS = Path(__file__).with_name("pipeline.js")
DATA_KEYS = ("name", "sheet", "sheets", "columns", "rows", "source_hint", "notes", "aggregates", "orientation_hint", "source_url")
MAX_TEXT = 2000
VERSION = 1
NO_CHANGE = "The chart did not change, so nothing was applied."
UNCHANGED = "The chart did not change."
SAID = ("did not change", "nothing changed", "nothing was applied", "no change")
BOOT_JS = """async ({app, pipe}) => { await QV.ready; (0, eval)(pipe); QVPipe.boot(app); return true; }"""


class ChartError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


@lru_cache
def sources() -> dict:
    return {"app": (WEB_DIR / "app.js").read_text(encoding="utf-8"), "pipe": PIPE_JS.read_text(encoding="utf-8")}


async def stage(name: str, payload: dict):
    async def work(page):
        await page.call(BOOT_JS, sources())
        return await page.call(f"input => QVPipe.{name}(input)", payload)

    try:
        return await RENDERER.run(work)
    except RenderError as e:
        if type(e) is RenderError:
            raise ChartError("data", f"The chart could not be built from this data. {e}")
        raise


def slim(parsed: dict) -> dict:
    return {k: parsed[k] for k in DATA_KEYS if k in parsed}


def models() -> list[str]:
    return viz._models(*viz.settings().label_models.split(",", 1))


async def read_csv(user: Visitor, text: str) -> dict:
    raw = (text or "").encode("utf-8")
    if not raw.strip():
        raise ChartError("data", "The data is empty. Send CSV text with a header row.")
    limit = viz.settings().max_upload_bytes
    if len(raw) > limit:
        raise ChartError("data", f"The data is over {limit // (1024 * 1024)} MB.")
    try:
        parsed = await viz_reading.read(user, raw, "data.csv", None, models())
    except ParseError as e:
        raise ChartError("data", f"The data could not be read. {e}")
    if not parsed.get("rows") or not parsed.get("columns"):
        raise ChartError("data", "No rows could be read from the data.")
    return slim(parsed)


async def named(user: Visitor, body: dict) -> dict | None:
    try:
        return await viz.names(viz.NamesIn(**body), user)
    except HTTPException as e:
        log.info("Names skipped: %s", e.detail)
        return None


async def picture(user: Visitor, done: dict, data: dict, style: str) -> dict:
    out = await render_chart(done["spec"], style, EXPORT_W, 2)
    chart = {**done["spec"], "style": out["style"],
             "quickviz": {"v": VERSION, "recipe": done["recipe"], "names": done["names"], "data": data}}
    limit = guard.limit_for(user.user)
    return {"png": out["png"], "html": out["html"], "spec": chart, "style": out["style"], "kind": done["kind"],
            "title": done["spec"].get("title") or "", "width": out["width"], "height": out["height"],
            "credits_left": guard.left(user.who, limit)}


async def make_chart(user: Visitor, csv: str, description: str | None = None, style: str | None = None, chart_type: str | None = None) -> dict:
    style = auth.check_style(user.user, style)
    text = (description or "").strip()[:MAX_TEXT]
    kind = (chart_type or "").strip().lower().replace(" ", "_") or None
    if kind and kind not in KINDS:
        raise ChartError("chart_type", f"Unknown chart type {chart_type!r}. Use one of: " + ", ".join(KINDS) + ".")
    data = await read_csv(user, csv)
    if kind:
        p = {"choice": kind, "ranked": [], "guess": True}
    else:
        body = await stage("columns", {"data": data, "style": style, "text": text})
        p = await viz.decide(viz.DecideIn(**body), user)
    plan = await stage("plan", {"data": data, "style": style, "decide": p, "text": text})
    if not plan["recipe"]:
        if kind:
            raise ChartError("chart_type", f"A {kind.replace('_', ' ')} chart does not fit this data. Leave chart_type out to let QuickViz pick.")
        raise ChartError("data", "No chart fits this data on its own. Say what to show in the description.")
    names = await named(user, plan["names"])
    done = await stage("finish", {"data": data, "style": style, "recipe": plan["recipe"], "names": names, "first": True})
    out = await picture(user, done, data, style)
    out["kinds"] = plan["kinds"]
    out["reply"] = ""
    return out


def unpack(chart) -> tuple[dict, dict, dict | None]:
    qv = chart.get("quickviz") if isinstance(chart, dict) else None
    if not isinstance(qv, dict) or not isinstance(qv.get("recipe"), dict) or not isinstance(qv.get("data"), dict):
        raise ChartError("spec", "This spec has no QuickViz data in it. Pass the spec that make_chart or edit_chart returned, unchanged.")
    data = qv["data"]
    if not isinstance(data.get("columns"), list) or not isinstance(data.get("rows"), list) or not data["rows"]:
        raise ChartError("spec", "The data inside this spec is damaged. Make the chart again with make_chart.")
    names = qv.get("names") if isinstance(qv.get("names"), dict) else None
    return qv["recipe"], slim(data), names


def honest(applied: dict) -> str:
    reply = (applied.get("reply") or "").strip()
    if not applied["changed"]:
        return reply if any(s in reply.lower() for s in SAID) else f"{UNCHANGED} {reply}".strip()
    if applied.get("missed"):
        return say_unused(applied["missed"], applied.get("recipe", {}).get("kind"), bool(applied.get("rest")))
    return reply


async def edit_chart(user: Visitor, chart: dict, instruction: str, style: str | None = None) -> dict:
    recipe, data, names = unpack(chart)
    style = auth.check_style(user.user, style or (chart.get("style") if isinstance(chart.get("style"), str) else None))
    message = (instruction or "").strip()[:600]
    if not message:
        raise ChartError("instruction", "Say what to change.")
    state = {"data": data, "style": style, "names": names, "recipe": recipe}
    body = await stage("chat", {**state, "message": message})
    res = await viz.chat(viz.ChatIn(**body), user)
    applied = await stage("apply", {**state, "res": res})
    if applied.get("noop"):
        res = await viz.chat(viz.ChatIn(**body, no_effect=applied["noop"]), user)
        applied = await stage("apply", {**state, "res": res})
        if applied.get("noop") or not applied["changed"]:
            applied = {"recipe": recipe, "reply": NO_CHANGE, "changed": False}
    applied["reply"] = honest(applied)
    if applied.get("names"):
        got = await named(user, applied["names"])
        if got and got.get("title"):
            names = {**(names or {}), "title": got["title"]}
    done = await stage("finish", {**state, "recipe": applied["recipe"], "names": names, "first": False})
    out = await picture(user, done, data, style)
    out["reply"] = applied["reply"]
    out["changed"] = applied["changed"]
    return out
