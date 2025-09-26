# --- imports ---
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path as FSPath
import os
import logging
import importlib
from datetime import datetime, date
from typing import Optional
import sqlite3
from urllib.parse import quote_plus

# --- create app ---
app = FastAPI(title="Expense Tracker", version="0.1.0")

# --- templates & static (מצביעים ל-frontend) ---
ROOT_DIR = FSPath(__file__).resolve().parents[2]   # .../expense_tracker/app
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --- sessions ---
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "please_change_session_secret")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax",
    https_only=False,
)

# --- logging (writes tracebacks to logs/server.log) ---
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

import logging
LOG_PATH = LOG_DIR / "server.log"

# create formatter
fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
formatter = logging.Formatter(fmt)

# file handler
file_handler = logging.FileHandler(str(LOG_PATH))
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# stream handler (console)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)

# root logger: ensure level and handlers (avoid duplicates)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
# add file handler if not present
if not any(getattr(h, "baseFilename", None) == str(LOG_PATH) for h in root_logger.handlers if isinstance(h, logging.FileHandler)):
    root_logger.addHandler(file_handler)
# add stream handler if not present
if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
    root_logger.addHandler(stream_handler)

# also attach file handler to uvicorn loggers so their output goes to the log file
for uv_logger_name in ("uvicorn.error", "uvicorn.access", "uvicorn"):
    lg = logging.getLogger(uv_logger_name)
    lg.setLevel(logging.INFO)
    if not any(getattr(h, "baseFilename", None) == str(LOG_PATH) for h in lg.handlers if isinstance(h, logging.FileHandler)):
        lg.addHandler(file_handler)

logger = logging.getLogger(__name__)

from fastapi.responses import JSONResponse, RedirectResponse
from . import db
from .services.cron_service import CronService

# --- include routers (אחרי app = FastAPI) ---
from .routes.pages import router as pages_router
from .routes.partials import router as partials_router
from .api.transactions import router as transactions_api
from .api.recurrences import router as recurrences_api, system_router as system_api
from .api.backup import router as backup_api
from .api.statistics import router as statistics_api

app.include_router(pages_router)
app.include_router(partials_router)
app.include_router(transactions_api)
app.include_router(recurrences_api)
app.include_router(system_api)
app.include_router(backup_api)
app.include_router(statistics_api)

# Redirect root to expenses if needed (handled in pages router too)
@app.get("/health")
async def health():
    return {"status": "ok"}


# --- lifecycle: init DB and start/stop cron ---
@app.on_event("startup")
async def _on_startup() -> None:
    try:
        db.initialise_database()
    except Exception:
        logger.exception("Database initialization failed")
        # Keep starting the app; routes like backup may help diagnose
    try:
        cron = CronService()
        cron.start()
        app.state.cron = cron
    except Exception:
        logger.exception("CronService failed to start")


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    cron = getattr(app.state, "cron", None)
    if cron is not None:
        try:
            cron.stop()
        except Exception:
            logger.exception("CronService shutdown error")


# --- simple auth gate (redirect to /login if not authenticated) ---
@app.middleware("http")
async def _require_login(request, call_next):
    try:
        # allow disabling auth via env for tests/dev
        if os.environ.get("AUTH_ENABLED", "1") != "1":
            return await call_next(request)
        path = request.url.path
        # Allow unauthenticated access to static, health, service worker and login
        if (
            path.startswith("/static/")
            or path == "/sw.js"
            or path.startswith("/login")
            or path == "/health"
        ):
            return await call_next(request)

        # Require session user for everything else
        if request.session.get("user"):
            return await call_next(request)

        # Preserve next only for GET requests
        if request.method == "GET":
            query = ("?" + str(request.url.query)) if request.url.query else ""
            nxt = quote_plus(path + query)
            from fastapi.responses import RedirectResponse as _RR

            return _RR(url=f"/login?next={nxt}", status_code=302)

        from fastapi.responses import RedirectResponse as _RR
        return _RR(url="/login", status_code=302)
    except Exception:  # fail open to avoid blocking due to auth errors
        return await call_next(request)
