import base64
import json
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import Field
from sqlalchemy import delete
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from app import auth, guard, leak, pipeline
from app.config import get_settings
from app.db import session
from app.llm import Visitor
from app.models import STYLES, ChartFile
from app.pipeline import ChartError
from app.render import LIMIT, RenderError, RenderTimeout, render_chart
from app.viz_chat import KINDS

log = logging.getLogger("quickviz.mcp")

PATH = "/mcp"
FILES = PATH + "/files/{name}"
FILE_DAYS = 7
FILE_ID = re.compile(r"^[A-Za-z0-9_-]{40,64}$")
STYLE_NAMES = {"franri": "QuickViz", "aiw": "AI World", "ceps": "CEPS"}
INSTRUCTIONS = ("QuickViz turns a table into a finished chart. Call make_chart with CSV text. You get a picture of the chart, a chart id "
                "and a link to download the interactive chart. To change a chart, call edit_chart with its chart id and say what to change "
                "in plain words. Each call uses credits from the QuickViz account the key belongs to. Call list_styles to see which "
                "chart styles it may use.")
NO_KEY = "A QuickViz API key is needed. Make one in the QuickViz account menu and send it as: Authorization: Bearer <key>"
EXPIRED = "That chart has expired, make it again with make_chart."
OLD_SPEC = "edit_chart now takes the chart id from make_chart, not a spec. Make the chart again with make_chart, then pass its chart id."
HEADS = {"credits": "No credits left.", "site": "QuickViz is out of AI budget for today.", "style": "Style not allowed.",
         "rate": "Too many requests.", "data": "Bad data.", "timeout": "Render timeout.", "render": "The chart could not be drawn.",
         "bad_change": "The change could not be made.", "ai": "The AI service failed.", "auth": "Not signed in.", "expired": "Chart expired.",
         "spec": "Old request.", "chart_type": "Bad chart type.", "instruction": "Bad instruction.", "error": "Error."}
SAYS = {"credits": "Try again tomorrow.", "site": "Try again tomorrow.", "rate": "Wait a moment and try again.",
        "data": "The data could not be read or charted. Send CSV text with a header row, or say in the description what to show.",
        "timeout": "Drawing the chart took too long. Try again.", "render": "Try again, or make the chart again.",
        "bad_change": "Try saying it another way.", "ai": "Try again in a moment.", "auth": NO_KEY, "expired": EXPIRED, "spec": OLD_SPEC,
        "instruction": "Say what to change in plain words.", "error": leak.REFUSED}
KEEP = ("chart_type", "instruction")


class Server(FastMCP):
    async def call_tool(self, name, arguments):
        if name == "edit_chart" and isinstance(arguments, dict) and "spec" in arguments:
            return failure("spec")
        try:
            return await super().call_tool(name, arguments)
        except Exception:
            log.exception("Tool %s failed", name)
            return failure("error")


server = Server("QuickViz", instructions=INSTRUCTIONS, stateless_http=True, json_response=True,
                transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
manager: StreamableHTTPSessionManager | None = None


@asynccontextmanager
async def lifespan():
    global manager
    manager = StreamableHTTPSessionManager(app=server._mcp_server, json_response=True, stateless=True,
                                           security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
                                           max_request_body_size=get_settings().max_body_bytes)
    async with manager.run():
        yield
    manager = None


class Endpoint:
    async def __call__(self, scope, receive, send):
        request = Request(scope, receive)
        user = auth.token_user(request)
        if user is None:
            reply = JSONResponse({"error": "unauthorized", "message": NO_KEY}, 401,
                                 headers={"WWW-Authenticate": 'Bearer realm="QuickViz"', "Cache-Control": "no-store"})
            return await reply(scope, receive, send)
        if manager is None:
            return await JSONResponse({"error": "starting", "message": "QuickViz is starting. Try again in a moment."}, 503)(scope, receive, send)
        scope.setdefault("state", {})["qv_user"] = user
        await manager.handle_request(scope, receive, send)


endpoint = Endpoint()


def caller(ctx: Context) -> Visitor:
    request = ctx.request_context.request
    user = request.state.qv_user if request is not None and hasattr(request.state, "qv_user") else None
    if user is None and request is not None:
        user = auth.token_user(request)
    if user is None:
        raise ChartError("auth", NO_KEY)
    return Visitor(guard.client_ip(request), user)


def failure(reason: str, message: str | None = None, status: int | None = None) -> CallToolResult:
    reason = reason if reason in HEADS else "error"
    text = message if message is not None else SAYS.get(reason, leak.REFUSED)
    return CallToolResult(content=[TextContent(type="text", text=f"{HEADS[reason]} {text}".strip())], isError=True,
                          structuredContent={"error": {"reason": reason, "status": status, "message": text}})


def from_http(e: HTTPException, user: Visitor | None) -> CallToolResult:
    d = e.detail
    log.info("Tool call refused: %s %r", e.status_code, d)
    reason = d.get("reason") if isinstance(d, dict) else None
    if reason == "style":
        return failure("style", "You can use: " + ", ".join(auth.allowed_styles(user.user if user else None)) + ".", e.status_code)
    if reason in ("credits", "site"):
        when = d.get("resets_at") if isinstance(d, dict) else None
        return failure(reason, f"Resets at {when}." if when else None, e.status_code)
    if reason == "rate" and isinstance(d, dict) and d.get("retry_after"):
        return failure("rate", f"Please wait {d['retry_after']} s and try again.", e.status_code)
    if e.status_code in (502, 503, 504):
        return failure("ai", status=e.status_code)
    return failure(reason if reason in HEADS else ("data" if e.status_code == 422 else "error"), status=e.status_code)


async def guarded(ctx: Context, work) -> CallToolResult:
    user = None
    try:
        user = caller(ctx)
        ok, wait = LIMIT.allow(user.who, "render")
        if not ok:
            return failure("rate", f"Please wait {wait} s and try again.", 429)
        return await work(user)
    except ChartError as e:
        log.info("Tool call failed: %s %s", e.reason, e.message)
        return failure(e.reason, e.message if e.reason in KEEP else None)
    except HTTPException as e:
        return from_http(e, user)
    except RenderTimeout:
        log.warning("Tool render timed out", exc_info=True)
        return failure("timeout")
    except RenderError:
        log.warning("Tool render failed", exc_info=True)
        return failure("render")


def file_age() -> float:
    return FILE_DAYS * 86400


def prune(db=None) -> int:
    cut = time.time() - file_age()
    if db is not None:
        return db.execute(delete(ChartFile).where(ChartFile.created < cut)).rowcount or 0
    with session() as db, db.begin():
        return db.execute(delete(ChartFile).where(ChartFile.created < cut)).rowcount or 0


def keep_file(owner: str, spec: dict) -> str:
    fid = secrets.token_urlsafe(32)
    with session() as db, db.begin():
        prune(db)
        db.add(ChartFile(id=fid, user_id=owner, spec=json.dumps(spec, ensure_ascii=False, separators=(",", ":")), created=time.time()))
    return fid


def load_file(owner: str, fid: str) -> dict | None:
    if not isinstance(fid, str) or not FILE_ID.match(fid):
        return None
    with session() as db, db.begin():
        row = db.get(ChartFile, fid)
        if row is None:
            return None
        if row.created < time.time() - file_age():
            db.delete(row)
            return None
        return json.loads(row.spec) if row.user_id == owner else None


def drawn(spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k != "quickviz"}


def base_url(request: Request | None) -> str:
    if request is None:
        return get_settings().public_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def slug_of(title: str, kind: str | None) -> str:
    name = (title or kind or "chart").lower()
    return "".join(ch if ch.isalnum() else "-" for ch in name).strip("-")[:60] or "chart"


def result(ctx: Context, user: Visitor, out: dict) -> CallToolResult:
    fid = keep_file(user.user.id, out["spec"])
    url = base_url(ctx.request_context.request) + PATH + "/files/" + fid + ".html"
    allowed = out.get("allowed", "")
    title = leak.clean(out["title"], "", allowed, "title")
    reply = leak.clean(out.get("reply") or "", leak.DONE if out.get("changed", True) else leak.REFUSED, allowed)
    lines = [f"{out['kind']} chart" + (f": {title}" if title else "") + f". Style {out['style']}. {out['width']} x {out['height']} px at 2x."]
    if reply:
        lines.append(reply)
    if out.get("kinds"):
        lines.append("Other chart types that fit: " + ", ".join(k for k in out["kinds"] if k != out["kind"]) + ".")
    lines.append(f"Credits left today: {out['credits_left']}.")
    lines.append(f"Chart id: {fid}. To change the chart, call edit_chart with this chart id and say what to change.")
    lines.append(f"The interactive chart is a self-contained HTML file at {url}. It needs the same key and the link lasts {FILE_DAYS} days. "
                 f'Save it with: curl -s -H "Authorization: Bearer $KEY" -o {slug_of(title, out["kind"])}.html {url}')
    return CallToolResult(content=[ImageContent(type="image", data=base64.b64encode(out["png"]).decode("ascii"), mimeType="image/png"),
                                   TextContent(type="text", text="\n".join(lines))],
                          structuredContent={"chart_id": fid, "html_url": url})


@server.tool(description="List the chart styles this key's account may use, the default style, and the credits left today.",
             annotations=ToolAnnotations(title="List chart styles", readOnlyHint=True, openWorldHint=False))
async def list_styles(ctx: Context) -> CallToolResult:
    try:
        user = caller(ctx)
    except ChartError as e:
        return failure(e.reason)
    allowed = auth.allowed_styles(user.user)
    default = auth.default_style(user.user)
    left = guard.left(user.who, guard.limit_for(user.user))
    data = {"styles": [{"id": s, "name": STYLE_NAMES[s], "default": s == default} for s in STYLES if s in allowed], "default": default,
            "credits_left": left}
    text = "Styles: " + ", ".join(f"{s} ({STYLE_NAMES[s]}{', default' if s == default else ''})" for s in allowed) + f". Credits left today: {left}."
    return CallToolResult(content=[TextContent(type="text", text=text)], structuredContent=data)


MAKE = ("Make a finished chart from a table. QuickViz picks the chart type, names the chart and draws it. "
        "Returns a picture of the chart, a chart id and a link to download the interactive chart. Uses credits.")
EDIT = ("Change a chart made earlier. Pass its chart id and say what to change in plain words, for example 'show the top 10', "
        "'make it a line chart' or 'title: AI use in 2025'. Returns a new chart id, the picture and a download link. Uses credits. "
        "When the change could not be made, the reply says so and the chart stays as it was.")


@server.tool(description=MAKE, annotations=ToolAnnotations(title="Make a chart", readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def make_chart(ctx: Context,
                     data: Annotated[str, Field(description="The table as CSV text with a header row. Comma, semicolon or tab separated.")],
                     description: Annotated[str | None, Field(description="Optional. What the data is and what the chart should show.")] = None,
                     style: Annotated[str | None, Field(description="Optional. One of the styles from list_styles. Leave out for the default.")] = None,
                     chart_type: Annotated[str | None, Field(description="Optional. Force a chart type: " + ", ".join(KINDS) + ".")] = None) -> CallToolResult:
    return await guarded(ctx, lambda user: _make(ctx, user, data, description, style, chart_type))


async def _make(ctx, user, data, description, style, chart_type):
    return result(ctx, user, await pipeline.make_chart(user, data, description, style, chart_type))


@server.tool(description=EDIT, annotations=ToolAnnotations(title="Edit a chart", readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def edit_chart(ctx: Context,
                     chart_id: Annotated[str, Field(description="The chart id from make_chart or edit_chart.")],
                     instruction: Annotated[str, Field(description="What to change, in plain words.")],
                     style: Annotated[str | None, Field(description="Optional. Redraw in another style from list_styles.")] = None) -> CallToolResult:
    return await guarded(ctx, lambda user: _edit(ctx, user, chart_id, instruction, style))


async def _edit(ctx, user, chart_id, instruction, style):
    spec = load_file(user.user.id, (chart_id or "").strip())
    if spec is None:
        raise ChartError("expired", EXPIRED)
    return result(ctx, user, await pipeline.edit_chart(user, spec, instruction, style))


def gone() -> JSONResponse:
    return JSONResponse({"error": "not_found", "message": f"No such chart file. Links last {FILE_DAYS} days. Make the chart again to get a new one."},
                        404, headers={"Cache-Control": "no-store"})


async def download(request: Request):
    user = auth.token_user(request)
    if user is None:
        return JSONResponse({"error": "unauthorized", "message": NO_KEY}, 401,
                            headers={"WWW-Authenticate": 'Bearer realm="QuickViz"', "Cache-Control": "no-store"})
    spec = load_file(user.id, request.path_params["name"].removesuffix(".html"))
    if spec is None:
        return gone()
    ok, wait = LIMIT.allow(Visitor(guard.client_ip(request), user).who, "render")
    if not ok:
        return JSONResponse({"error": "rate", "message": f"Too many requests. Please wait {wait} s and try again."}, 429,
                            headers={"Retry-After": str(wait), "Cache-Control": "no-store"})
    try:
        out = await render_chart(drawn(spec), spec.get("style"))
    except RenderTimeout:
        log.warning("Download render timed out", exc_info=True)
        return JSONResponse({"error": "timeout", "message": "Drawing the chart took too long. Try again."}, 503, headers={"Cache-Control": "no-store"})
    except RenderError:
        log.warning("Download render failed", exc_info=True)
        return JSONResponse({"error": "render", "message": "The chart could not be drawn."}, 500, headers={"Cache-Control": "no-store"})
    name = slug_of(spec.get("title") or "", spec.get("kind"))
    return HTMLResponse(out["html"], headers={"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="{name}.html"'})
