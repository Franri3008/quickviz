import asyncio
import base64
import json
import logging
import mimetypes
import os
import shutil
import tempfile
import time
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app import auth, guard
from app.config import WEB_DIR
from app.llm import Visitor, visitor
from app.mock import RateLimit
from app.models import DEFAULT_STYLE, STYLES

log = logging.getLogger("quickviz.render")

ORIGIN = "http://qv.render"
SHELL = "/__render.html"
EXPORT_W = 760
MIN_W, MAX_W = 320, 1600
MAX_SCALE = float(os.environ.get("RENDER_MAX_SCALE", 2))
MAX_PIXELS = 16_777_216
MAX_SPEC = 400_000
TIMEOUT_S = float(os.environ.get("RENDER_TIMEOUT_S", 25))
IDLE_S = float(os.environ.get("RENDER_IDLE_S", 300))
RECYCLE = int(os.environ.get("RENDER_RECYCLE", 40))
SERVED = ("vendor/", "export/", "geo/regions/", "fonts/", "flags/flags.json")
SCRIPTS = ["vendor/d3.min.js", "vendor/d3-sankey.min.js", "vendor/topojson-client.min.js",
           "ceps-theme.js", "aiw-theme.js", "franri-theme.js", "charts.js"]
FLAGS = ["--no-zygote", "--disable-gpu", "--disable-dev-shm-usage", "--disable-extensions", "--disable-background-networking",
         "--disable-component-update", "--disable-default-apps", "--disable-sync", "--disable-breakpad", "--mute-audio",
         "--no-first-run", "--metrics-recording-only", "--renderer-process-limit=1", "--enable-low-end-device-mode",
         "--disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication",
         "--js-flags=--max-old-space-size=64", "--disk-cache-size=1", "--media-cache-size=1", "--aggressive-cache-discard", "--disable-cache"]
SINGLE = os.environ.get("RENDER_SINGLE_PROCESS", "1") != "0"
LIMIT = RateLimit({"render": int(os.environ.get("RATE_RENDER", 20))})

SHELL_HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="{ORIGIN}/fonts/carlito.css">
<style>html,body{{margin:0;padding:0;background:transparent}}body{{font-family:Carlito,Calibri,"Segoe UI",sans-serif;color:#1a1a1a}}
#host{{display:inline-block}}#chart{{display:block}}</style>
</head><body><div id="host"><svg id="chart" role="img" aria-label="Chart"></svg></div>
<script>window.QV_BASE = "{ORIGIN}/"; window.QV_FLAGS = {{}};</script>
{"".join(f'<script src="{ORIGIN}/{s}"></script>' for s in SCRIPTS)}
</body></html>"""

DRAW_JS = """async ({spec, width, flags}) => {
  Object.assign(window.QV_FLAGS, flags);
  await QV.ready;
  const svg = document.getElementById("chart");
  document.getElementById("host").style.width = width + "px";
  QV.render(svg, spec, {width, still: true, noResize: true, noControls: true});
  const busy = () => [...svg.querySelectorAll("text")].some(t => /^Loading map/.test(t.textContent));
  for (let i = 0; i < 200 && busy(); i++) await new Promise(r => setTimeout(r, 50));
  if (busy()) throw new Error("The map outlines did not load");
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const st = svg.__qv || {};
  const th = (window.QV_THEMES || {})[spec.style] || {};
  document.body.style.background = spec.background === "transparent" ? "transparent" : (th.paper || "#fff");
  const html = await QV.exportHTML(spec, svg, {flagData: flags});
  const W = +svg.getAttribute("width") || width, H = +svg.getAttribute("height") || svg.getBoundingClientRect().height;
  const box = svg.getBoundingClientRect();
  return {html, W, H, x: box.left + scrollX, y: box.top + scrollY, w: box.width, h: box.height, geoUsed: st.geoUsed || null, transparent: spec.background === "transparent"};
}"""


class RenderError(Exception):
    pass


class RenderTimeout(RenderError):
    pass


@lru_cache
def flag_data() -> dict:
    path = WEB_DIR / "flags" / "flags.json"
    return json.loads(path.read_text()) if path.exists() else {}


def asset(path: str) -> bytes | None:
    rel = path.lstrip("/")
    if ".." in rel or not any(rel == p or rel.startswith(p) for p in SCRIPTS + list(SERVED)):
        return None
    file = (WEB_DIR / rel).resolve()
    if not file.is_relative_to(WEB_DIR.resolve()) or not file.is_file():
        return None
    return file.read_bytes()


def chrome_path() -> str:
    env = os.environ.get("CHROME_PATH")
    if env:
        return env
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), str(Path.home() / ".cache/ms-playwright"),
             str(Path.home() / "Library/Caches/ms-playwright")]
    for root in filter(None, roots):
        hits = sorted(Path(root).glob("chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell"), reverse=True)
        if hits:
            return str(hits[0])
    for name in ("chrome-headless-shell", "chromium-headless-shell", "chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise RenderError("No Chromium found. Run: python -m playwright install chromium-headless-shell")


@lru_cache(maxsize=64)
def asset_b64(path: str) -> str | None:
    body = asset(path)
    return None if body is None else base64.b64encode(body).decode("ascii")


class Browser:
    def __init__(self):
        self.proc = None
        self.profile = None
        self.writer = None
        self.reader_task = None
        self.seq = 0
        self.waits: dict[int, asyncio.Future] = {}
        self.events: dict[str, asyncio.Queue] = {}

    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None and self.reader_task is not None and not self.reader_task.done()

    async def launch(self):
        loop = asyncio.get_running_loop()
        to_chrome_r, to_chrome_w = os.pipe()
        from_chrome_r, from_chrome_w = os.pipe()
        self.profile = tempfile.mkdtemp(prefix="qv-chrome-")
        args = [chrome_path(), "--headless", "--remote-debugging-pipe", "--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb",
                f"--user-data-dir={self.profile}", *FLAGS, *(["--single-process"] if SINGLE else []), "about:blank"]
        cmd = 'exec "$@" 3<&' + str(to_chrome_r) + " 4>&" + str(from_chrome_w)
        self.proc = await asyncio.create_subprocess_exec("/bin/sh", "-c", cmd, "sh", *args, pass_fds=(to_chrome_r, from_chrome_w),
                                                         stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                                                         stderr=asyncio.subprocess.DEVNULL)
        os.close(to_chrome_r)
        os.close(from_chrome_w)
        reader = asyncio.StreamReader(limit=64 * 2**20)
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(from_chrome_r, "rb", 0))
        transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, os.fdopen(to_chrome_w, "wb", 0))
        self.writer = asyncio.StreamWriter(transport, protocol, None, loop)
        self.reader_task = asyncio.create_task(self._read(reader))
        await self.send("Browser.getVersion")

    async def _read(self, reader):
        try:
            while True:
                raw = await reader.readuntil(b"\0")
                msg = json.loads(raw[:-1])
                if "id" in msg:
                    fut = self.waits.pop(msg["id"], None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(RenderError(str(msg["error"].get("message", "CDP error"))[:300]))
                        else:
                            fut.set_result(msg.get("result", {}))
                else:
                    q = self.events.get(msg.get("sessionId", ""))
                    if q:
                        q.put_nowait(msg)
        except (asyncio.IncompleteReadError, ConnectionError, ValueError):
            pass
        finally:
            for fut in self.waits.values():
                if not fut.done():
                    fut.set_exception(RenderError("The browser stopped"))
            self.waits.clear()

    async def send(self, method: str, params: dict | None = None, session: str | None = None) -> dict:
        if not self.alive():
            raise RenderError("The browser stopped")
        self.seq += 1
        msg = {"id": self.seq, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        fut = asyncio.get_running_loop().create_future()
        self.waits[self.seq] = fut
        self.writer.write(json.dumps(msg).encode() + b"\0")
        await self.writer.drain()
        return await fut

    async def close(self):
        if self.reader_task:
            self.reader_task.cancel()
        if self.writer:
            self.writer.close()
        if self.proc and self.proc.returncode is None:
            self.proc.kill()
            await self.proc.wait()
        if self.profile:
            shutil.rmtree(self.profile, ignore_errors=True)
        self.proc = self.writer = self.reader_task = self.profile = None


class Page:
    def __init__(self, browser: Browser):
        self.b = browser
        self.target = self.session = None
        self.queue = asyncio.Queue()
        self.pump = None
        self.loaded = asyncio.Event()

    async def open(self):
        self.target = (await self.b.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
        self.session = (await self.b.send("Target.attachToTarget", {"targetId": self.target, "flatten": True}))["sessionId"]
        self.b.events[self.session] = self.queue
        self.pump = asyncio.create_task(self._pump())
        await self.send("Page.enable")
        await self.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
        await self.send("Emulation.setDeviceMetricsOverride", {"width": MAX_W + 40, "height": 800, "deviceScaleFactor": 1, "mobile": False})

    def send(self, method: str, params: dict | None = None):
        return self.b.send(method, params, self.session)

    async def _pump(self):
        while True:
            msg = await self.queue.get()
            method, params = msg.get("method"), msg.get("params", {})
            if method == "Fetch.requestPaused":
                asyncio.create_task(self._serve(params))
            elif method == "Page.loadEventFired":
                self.loaded.set()

    async def _serve(self, p: dict):
        url, rid = p["request"]["url"], p["requestId"]
        try:
            if url == ORIGIN + SHELL:
                body, kind = base64.b64encode(SHELL_HTML.encode()).decode("ascii"), "text/html"
            elif url.startswith(ORIGIN + "/"):
                path = url[len(ORIGIN):].split("?", 1)[0]
                body, kind = asset_b64(path), mimetypes.guess_type(path)[0] or "application/octet-stream"
            else:
                body = kind = None
            if body is None:
                await self.send("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"})
            else:
                await self.send("Fetch.fulfillRequest", {"requestId": rid, "responseCode": 200, "body": body,
                                                         "responseHeaders": [{"name": "Content-Type", "value": kind}]})
        except RenderError:
            pass

    async def goto(self, url: str):
        self.loaded.clear()
        await self.send("Page.navigate", {"url": url})
        await self.loaded.wait()

    async def call(self, fn: str, arg) -> object:
        r = await self.send("Runtime.evaluate", {"expression": f"({fn})({json.dumps(arg)})", "awaitPromise": True, "returnByValue": True})
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RenderError(str((d.get("exception") or {}).get("description") or d.get("text") or "Script error").splitlines()[0][:300])
        return r["result"].get("value")

    async def close(self):
        if self.pump:
            self.pump.cancel()
        self.b.events.pop(self.session, None)
        if self.target:
            try:
                await self.b.send("Target.closeTarget", {"targetId": self.target})
            except RenderError:
                pass


class Renderer:
    def __init__(self):
        self.browser = None
        self.lock = asyncio.Lock()
        self.idle = None
        self.renders = 0

    async def start(self) -> Browser:
        if self.browser and self.browser.alive():
            return self.browser
        await self.stop()
        self.browser = Browser()
        await self.browser.launch()
        return self.browser

    async def stop(self):
        browser, self.browser = self.browser, None
        if browser:
            try:
                await browser.close()
            except Exception:
                log.warning("Could not close the renderer cleanly", exc_info=True)

    def _arm_idle(self):
        if self.idle:
            self.idle.cancel()
        if IDLE_S > 0:
            loop = asyncio.get_running_loop()
            self.idle = loop.call_later(IDLE_S, lambda: asyncio.ensure_future(self._idle_stop()))

    async def _idle_stop(self):
        if not self.lock.locked():
            async with self.lock:
                await self.stop()

    async def draw(self, page: Page, spec: dict, width: int, scale: float) -> dict:
        t0 = time.time()
        keys = await page.call("spec => QV.flagKeys(spec)", spec) or []
        all_flags = flag_data()
        flags = {k: all_flags[k] for k in keys if isinstance(all_flags.get(k), str)}
        if flags:
            flags["_notice"] = all_flags.get("_notice", "")
        out = await page.call(DRAW_JS, {"spec": spec, "width": width, "flags": flags})
        if out["w"] * out["h"] * scale * scale > MAX_PIXELS:
            raise RenderError("The picture is too large")
        if out["transparent"]:
            await page.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        shot = await page.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True, "fromSurface": True,
                                                         "clip": {"x": out["x"], "y": out["y"], "width": out["w"], "height": out["h"], "scale": scale}})
        return {"png": base64.b64decode(shot["data"]), "html": out["html"], "width": round(out["W"]), "height": round(out["H"]), "geo": out["geoUsed"],
                "ms": round((time.time() - t0) * 1000)}

    async def _in_page(self, work):
        page = Page(await self.start())
        try:
            await page.open()
            await page.goto(ORIGIN + SHELL)
            return await work(page)
        finally:
            await page.close()

    async def render(self, spec: dict, width: int, scale: float) -> dict:
        return await self.run(lambda page: self.draw(page, spec, width, scale))

    async def run(self, work):
        async with self.lock:
            try:
                return await asyncio.wait_for(self._in_page(work), TIMEOUT_S)
            except asyncio.TimeoutError:
                await self.stop()
                raise RenderTimeout(f"Drawing took longer than {TIMEOUT_S:g} s")
            except RenderError:
                if not (self.browser and self.browser.alive()):
                    await self.stop()
                raise
            except Exception as e:
                await self.stop()
                log.exception("Server render failed")
                raise RenderError(str(e).splitlines()[0][:300] if str(e) else "The chart could not be drawn")
            finally:
                self.renders += 1
                if RECYCLE and self.renders % RECYCLE == 0:
                    await self.stop()
                self._arm_idle()


RENDERER = Renderer()


def clean_spec(spec, style: str | None) -> dict:
    if not isinstance(spec, dict) or not spec:
        raise RenderError("The spec must be a JSON object")
    if len(json.dumps(spec)) > MAX_SPEC:
        raise RenderError("The spec is too large")
    if not isinstance(spec.get("kind"), str):
        raise RenderError("The spec needs a kind")
    if not isinstance(spec.get("rows"), list) or not spec["rows"]:
        raise RenderError("The spec needs rows")
    out = {k: v for k, v in spec.items() if k not in ("patches", "ctlInit")}
    out["style"] = style or spec.get("style") or DEFAULT_STYLE
    if out["style"] not in STYLES:
        raise RenderError(f"Unknown style {out['style']}")
    return out


async def render_chart(spec: dict, style: str | None = None, width: int = EXPORT_W, scale: float = 2) -> dict:
    width = max(MIN_W, min(MAX_W, int(width)))
    scale = max(1.0, min(float(MAX_SCALE), float(scale)))
    clean = clean_spec(spec, style)
    out = await RENDERER.render(clean, width, scale)
    return {**out, "style": clean["style"]}


def render_chart_sync(spec: dict, style: str | None = None, width: int = EXPORT_W, scale: float = 2) -> dict:
    return asyncio.run(render_chart(spec, style, width, scale))


router = APIRouter(prefix="/api")


class RenderIn(BaseModel):
    spec: dict
    style: str | None = Field(None, max_length=20)
    width: int = Field(EXPORT_W, ge=MIN_W, le=MAX_W)
    scale: float = Field(2, ge=1, le=MAX_SCALE)


def pick_style(user: Visitor, style: str | None) -> str | None:
    return auth.check_style(user.user, style)


@router.post("/render")
async def api_render(request: Request, body: RenderIn, user: Visitor = Depends(visitor)):
    if user.user is None:
        raise HTTPException(401, detail="Sign in to draw charts on the server.")
    ok, wait = LIMIT.allow(guard.who(user.ip, user.user), "render")
    if not ok:
        raise HTTPException(429, detail={"reason": "rate", "message": f"Too many requests. Please wait {wait} s and try again.", "retry_after": wait})
    style = pick_style(user, body.style)
    try:
        out = await render_chart(body.spec, style, body.width, body.scale)
    except RenderError as e:
        raise HTTPException(422, detail=str(e))
    return {"png": base64.b64encode(out["png"]).decode("ascii"), "html": out["html"], "style": out["style"],
            "width": out["width"], "height": out["height"], "scale": body.scale, "ms": out["ms"]}
