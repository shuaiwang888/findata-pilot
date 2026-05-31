import logging
import os
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.files import router as files_router
from app.api.history import router as history_router
from app.api.health import router as health_router
from app.storage.mysql import close_pool
from app.storage.repository import ensure_summary_columns
from app.utils.env import load_env

load_env()

app = FastAPI(title="FinDataPilot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8011", "http://127.0.0.1:8011"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RATE_WINDOW = 60
RATE_MAX_CHAT = 30
_rate_store: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ("/chat", "/chat/stream"):
        now = time.time()
        ip = request.client.host if request.client else "unknown"
        window = _rate_store[ip]
        window[:] = [t for t in window if now - t < RATE_WINDOW]
        if len(window) >= RATE_MAX_CHAT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please wait before sending another query."},
            )
        window.append(now)
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    try:
        ensure_summary_columns()
    except Exception:
        logging.warning("Schema migration at startup failed; persistence may be degraded.")


@app.on_event("shutdown")
def on_shutdown():
    try:
        close_pool()
    except Exception:
        pass


app.include_router(history_router)
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(files_router)

WEB_DIST_DIR = Path(__file__).resolve().parent / "web_dist"
LEGACY_WEB_PATH = Path(__file__).resolve().parent / "web" / "index.html"

if WEB_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST_DIR / "assets"), name="web-assets")


@app.get("/", response_class=HTMLResponse)
def root():
    react_index = WEB_DIST_DIR / "index.html"
    if react_index.exists():
        return react_index.read_text(encoding="utf-8")
    return LEGACY_WEB_PATH.read_text(encoding="utf-8")


@app.get("/debug/keys")
def debug_keys():
    from app.utils.env import load_env
    if os.environ.get("DATA_AGENT_DEBUG_KEYS") != "1":
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    load_env()
    return {
        "IWENCAI_API_KEY": bool(os.environ.get("IWENCAI_API_KEY")),
        "MINIMAX_API_KEY": bool(os.environ.get("MINIMAX_API_KEY")),
        "cwd": os.getcwd(),
    }
