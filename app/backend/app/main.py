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
import re

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
from fastapi.routing import APIRoute
from . import db
from .auth import is_endpoint_public, public
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

# Build public route matchers from routes decorated with @public
PUBLIC_ROUTE_MATCHERS = []  # list of tuples: (compiled_regex, set_of_methods)
try:
    for r in app.routes:
        if isinstance(r, APIRoute) and is_endpoint_public(getattr(r, "endpoint", None)):
            try:
                regex = r.path_regex
            except Exception:
                path_str = getattr(r, "path", getattr(r, "path_format", "")) or ""
                pattern = "^" + re.escape(path_str) + "$"
                regex = re.compile(pattern)
            methods = set(m.upper() for m in (r.methods or {"GET"}))
            PUBLIC_ROUTE_MATCHERS.append((regex, methods))
except Exception:
    logger.exception("Failed building public route matchers")

# Redirect root to expenses if needed (handled in pages router too)
@app.get("/health")
@public
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
    # Allow disabling auth ONLY under pytest (to keep E2E tests working)
    auth_enabled_env = os.environ.get("AUTH_ENABLED", "1")
    auth_enabled = auth_enabled_env == "1"
    running_pytest = os.environ.get("PYTEST_CURRENT_TEST") is not None
    logger.info(
        f"AUTH middleware: AUTH_ENABLED={auth_enabled_env}, running_pytest={running_pytest}, "
        f"path={request.url.path}, method={request.method}"
    )
    if not auth_enabled and running_pytest:
        logger.info("AUTH middleware: disabled under pytest -> allowing request")
        return await call_next(request)

    path = request.url.path
    method = request.method.upper()

    # Allow unauthenticated access to static and service worker by path
    if path.startswith("/static/") or path == "/sw.js":
        logger.info(f"AUTH middleware: allow public path {path}")
        return await call_next(request)

    # Check if matches any @public endpoint (best-effort; do not block on errors)
    try:
        for (regex, methods) in PUBLIC_ROUTE_MATCHERS:
            if regex.match(path) and (not methods or method in methods):
                logger.info(f"AUTH middleware: allow @public for {path} {method}")
                return await call_next(request)
    except Exception:
        logger.exception("AUTH middleware: error checking public matchers")

    # Require session user for everything else
    try:
        user_in_session = bool(request.session.get("user"))
    except AssertionError:
        # SessionMiddleware not yet installed in the stack for this scope
        # Treat as no session (unauthenticated)
        user_in_session = False
    if user_in_session:
        try:
            logger.info(f"AUTH middleware: session user detected: {request.session.get('user')}")
        except Exception:
            pass
        return await call_next(request)

    # Not authenticated -> redirect to login (preserve next for GET only)
    from fastapi.responses import RedirectResponse as _RR
    if request.method == "GET":
        # Special-case: if someone tries to GET /logout without a session, do not set next=/logout
        if path == "/logout":
            logger.info("AUTH middleware: unauthenticated GET /logout -> redirect to /login without next")
            return _RR(url="/login", status_code=302)
        query = ("?" + str(request.url.query)) if request.url.query else ""
        nxt = quote_plus(path + query)
        logger.info(f"AUTH middleware: no session. redirecting to /login?next={nxt}")
        return _RR(url=f"/login?next={nxt}", status_code=302)

    logger.info("AUTH middleware: no session on non-GET. redirecting to /login")
    return _RR(url="/login", status_code=302)
