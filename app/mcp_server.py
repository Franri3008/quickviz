import base64
import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, EmbeddedResource, ImageContent, TextContent, TextResourceContents, ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import auth, guard, pipeline
from app.config import get_settings
from app.llm import Visitor
from app.models import STYLES
from app.pipeline import ChartError
from app.render import LIMIT, RenderError, RenderTimeout
from app.viz_chat import KINDS

log = logging.getLogger("quickviz.mcp")

PATH = "/mcp"
STYLE_NAMES = {"franri": "QuickViz", "aiw": "AI World", "ceps": "CEPS"}
INSTRUCTIONS = ("QuickViz turns a table into a finished chart. Call make_chart with CSV text. You get a PNG, the chart spec as JSON "
                "and a self-contained HTML file. To change a chart, pass the spec back to edit_chart with an instruction in plain words. "
                "Each call uses credits from the QuickViz account the key belongs to. Call list_styles to see which chart styles it may use.")
NO_KEY = "A QuickViz API key is needed. Make one in the QuickViz account menu and send it as: Authorization: Bearer <key>"

server = FastMCP("QuickViz", instructions=INSTRUCTIONS, stateless_http=True, json_response=True,
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


def failure(reason: str, message: str, status: int | None = None) -> CallToolResult:
    head = {"credits": "No credits left.", "site": "QuickViz is out of AI budget for today.", "style": "Style not allowed (403, reason: style).",
            "rate": "Too many requests.", "data": "Bad data.", "timeout": "Render timeout.", "render": "The chart could not be drawn.",
            "bad_change": "The change could not be made.", "ai": "The AI service failed.", "auth": "Not signed in.",
            "spec": "Bad spec.", "chart_type": "Bad chart type.", "instruction": "Bad instruction."}.get(reason, "Error.")
    return CallToolResult(content=[TextContent(type="text", text=f"{head} {message}".strip())], isError=True,
                          structuredContent={"error": {"reason": reason, "status": status, "message": message}})


def from_http(e: HTTPException, user: Visitor | None) -> CallToolResult:
    d = e.detail
    reason = d.get("reason") if isinstance(d, dict) else None
    message = d.get("message", "") if isinstance(d, dict) else str(d)
    if reason == "style":
        message += " You can use: " + ", ".join(auth.allowed_styles(user.user if user else None)) + "."
    elif reason in ("credits", "site") and isinstance(d, dict) and d.get("resets_at"):
        message = message.split(" Your chart,")[0] + f" Resets at {d['resets_at']}."
    elif e.status_code in (502, 503, 504):
        reason = "ai"
    return failure(reason or ("data" if e.status_code == 422 else "error"), message, e.status_code)


async def guarded(ctx: Context, work) -> CallToolResult:
    user = None
    try:
        user = caller(ctx)
        ok, wait = LIMIT.allow(user.who, "render")
        if not ok:
            return failure("rate", f"Please wait {wait} s and try again.", 429)
        return await work(user)
    except ChartError as e:
        return failure(e.reason, e.message)
    except HTTPException as e:
        return from_http(e, user)
    except RenderTimeout as e:
        return failure("timeout", str(e))
    except RenderError as e:
        return failure("render", str(e))


def result(out: dict, html: bool) -> CallToolResult:
    name = (out["title"] or out["kind"] or "chart").lower()
    slug = "".join(ch if ch.isalnum() else "-" for ch in name).strip("-")[:60] or "chart"
    lines = [f"{out['kind']} chart" + (f": {out['title']}" if out["title"] else "") + f". Style {out['style']}. {out['width']} x {out['height']} px at 2x."]
    if out.get("reply"):
        lines.append(out["reply"])
    if out.get("kinds"):
        lines.append("Other chart types that fit: " + ", ".join(k for k in out["kinds"] if k != out["spec"].get("kind")) + ".")
    lines.append(f"Credits left today: {out['credits_left']}.")
    lines.append("To change it, call edit_chart with the spec below, unchanged, and an instruction.")
    if not html:
        lines.append(f"The self-contained HTML file is {len(out['html']) // 1024} KB. Call again with html=true to get it.")
    content = [
        ImageContent(type="image", data=base64.b64encode(out["png"]).decode("ascii"), mimeType="image/png"),
        TextContent(type="text", text="\n".join(lines)),
        TextContent(type="text", text=json.dumps(out["spec"], ensure_ascii=False, separators=(",", ":"))),
    ]
    if html:
        content.append(EmbeddedResource(type="resource", resource=TextResourceContents(uri=f"quickviz://chart/{slug}.html", mimeType="text/html",
                                                                                     text=out["html"])))
    return CallToolResult(content=content)


@server.tool(description="List the chart styles this key's account may use, the default style, and the credits left today.",
             annotations=ToolAnnotations(title="List chart styles", readOnlyHint=True, openWorldHint=False))
async def list_styles(ctx: Context) -> CallToolResult:
    try:
        user = caller(ctx)
    except ChartError as e:
        return failure(e.reason, e.message)
    allowed = auth.allowed_styles(user.user)
    default = auth.default_style(user.user)
    left = guard.left(user.who, guard.limit_for(user.user))
    data = {"styles": [{"id": s, "name": STYLE_NAMES[s], "default": s == default} for s in STYLES if s in allowed], "default": default,
            "credits_left": left}
    text = "Styles: " + ", ".join(f"{s} ({STYLE_NAMES[s]}{', default' if s == default else ''})" for s in allowed) + f". Credits left today: {left}."
    return CallToolResult(content=[TextContent(type="text", text=text)], structuredContent=data)


HTML_HELP = "Optional. Also return the self-contained interactive HTML file. It is large, often 400 KB or more, so ask only when you will save it."
MAKE = ("Make a finished chart from a table. QuickViz reads the data, picks the chart type and the column roles, names the chart and draws it. "
        "Returns a PNG, a short summary and the chart spec as JSON, plus the self-contained HTML file when html is true. Uses credits.")
EDIT = ("Change a chart made by make_chart or edit_chart. Pass its spec JSON unchanged and say what to change in plain words, "
        "for example 'show the top 10', 'make it a line chart' or 'title: AI use in 2025'. Returns the same outputs as make_chart. Uses credits.")


@server.tool(description=MAKE, annotations=ToolAnnotations(title="Make a chart", readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def make_chart(ctx: Context,
                     data: Annotated[str, Field(description="The table as CSV text with a header row. Comma, semicolon or tab separated.")],
                     description: Annotated[str | None, Field(description="Optional. What the data is and what the chart should show.")] = None,
                     style: Annotated[str | None, Field(description="Optional. One of the styles from list_styles. Leave out for the default.")] = None,
                     chart_type: Annotated[str | None, Field(description="Optional. Force a chart type: " + ", ".join(KINDS) + ".")] = None,
                     html: Annotated[bool, Field(description=HTML_HELP)] = False) -> CallToolResult:
    return await guarded(ctx, lambda user: _make(user, data, description, style, chart_type, html))


async def _make(user, data, description, style, chart_type, html):
    return result(await pipeline.make_chart(user, data, description, style, chart_type), html)


@server.tool(description=EDIT, annotations=ToolAnnotations(title="Edit a chart", readOnlyHint=False, destructiveHint=False, openWorldHint=False))
async def edit_chart(ctx: Context,
                     spec: Annotated[dict | str, Field(description="The spec JSON returned by make_chart or edit_chart, unchanged.")],
                     instruction: Annotated[str, Field(description="What to change, in plain words.")],
                     style: Annotated[str | None, Field(description="Optional. Redraw in another style from list_styles.")] = None,
                     html: Annotated[bool, Field(description=HTML_HELP)] = False) -> CallToolResult:
    return await guarded(ctx, lambda user: _edit(user, spec, instruction, style, html))


async def _edit(user, spec, instruction, style, html):
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except ValueError:
            raise ChartError("spec", "The spec is not valid JSON.")
    return result(await pipeline.edit_chart(user, spec, instruction, style), html)
