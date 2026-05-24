from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.files import router as files_router
from app.api.history import router as history_router
from app.api.health import router as health_router
from app.utils.env import load_env


load_env()

app = FastAPI(title="FinDataPilot", version="0.1.0")
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
