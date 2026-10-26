import logging
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import admin, auth, db, guard, health, mock
from app.config import ROOT_DIR, WEB_DIR
from app.protect import RequestProtection
from app.viz import router as viz_router

log = logging.getLogger("quickviz")


def version() -> str:
    path = ROOT_DIR / "VERSION"
    return path.read_text().strip() if path.exists() else "dev"


PAGE_CSP = "frame-src 'none'; child-src 'none'; object-src 'none'; base-uri 'self'"


def page(name: str) -> HTMLResponse:
    html = (WEB_DIR / name).read_text(encoding="utf-8").replace("__VERSION__", version())
    return HTMLResponse(html, headers={"Cache-Control": "no-cache", "Content-Security-Policy": PAGE_CSP})


@asynccontextmanager
async def lifespan(app):
    db.initialize()
    yield


app = FastAPI(title="QuickViz", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(RequestProtection)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(viz_router)
app.include_router(mock.router)


@app.middleware("http")
async def static_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/geo/"):
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif not path.startswith("/api") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/version", include_in_schema=False)
def version_info():
    return {"version": version()}


@app.get("/api/health", include_in_schema=False)
async def health_check():
    checked_at = time.time()
    try:
        ai = await health.openrouter_state()
        ok, metrics, checks, error = health.assess(ai, guard.summary(), version())
        return JSONResponse({
            "schemaVersion": "1",
            "service": health.SERVICE,
            "ok": ok,
            "checkedAt": health.utc(checked_at),
            "updatedAt": health.utc(ai["at"]),
            "metrics": metrics,
            "checks": checks,
            "error": error,
            "version": version(),
        }, status_code=200 if ok else 503)
    except Exception:
        log.exception("Could not assess service health")
        return JSONResponse({
            "schemaVersion": "1",
            "service": health.SERVICE,
            "ok": False,
            "checkedAt": health.utc(checked_at),
            "updatedAt": None,
            "metrics": {},
            "checks": {},
            "error": {"code": "ASSESSMENT_FAILED", "message": "Health assessment failed"},
            "version": version(),
        }, status_code=503)


@app.get("/admin", include_in_schema=False)
@app.get("/admin.html", include_in_schema=False)
def admin_page(request: Request):
    if not auth.is_admin(auth.session_user(request)):
        raise HTTPException(404, detail="Not Found")
    return page("admin.html")


@app.get("/privacy", include_in_schema=False)
@app.get("/privacy.html", include_in_schema=False)
def privacy_page():
    return page("privacy.html")


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def index():
    return page("index.html")


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
