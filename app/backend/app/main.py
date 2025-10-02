# --- imports ---
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path as FSPath
import os
import logging
from urllib.parse import quote_plus
from starlette.middleware.trustedhost import TrustedHostMiddleware

# --- create app ---
app = FastAPI(title="Expense Tracker", version="0.1.0")

# --- static (מצביעים ל-frontend) ---
ROOT_DIR = FSPath(__file__).resolve().parents[2]   # .../expense_tracker/app
FRONTEND_DIR = ROOT_DIR / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --- sessions ---
# Use a stronger default secret key for production
DEFAULT_SECRET_KEY = "expense_tracker_session_secret_key_2024_production_secure_random_string_12345"
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", DEFAULT_SECRET_KEY)

# Auto-detect HTTPS in production (Railway uses HTTPS)
is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None or os.environ.get("ENVIRONMENT") == "production"

# For Railway deployment, use more permissive cookie settings
if is_production:
    COOKIE_SAMESITE = "lax"  # Railway requires lax for cross-site requests
    HTTPS_ONLY = False  # Railway proxy handles HTTPS termination
    SESSION_COOKIE_DOMAIN = None  # Let browser handle domain
else:
    COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax")
    if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
        COOKIE_SAMESITE = "lax"
    
    _secure_env = os.environ.get("COOKIE_SECURE")
    if _secure_env is not None:
        HTTPS_ONLY = str(_secure_env).strip().lower() in {"1", "true", "yes", "on"}
    else:
        HTTPS_ONLY = False  # Default to False for local development
    
    SESSION_COOKIE_DOMAIN = os.environ.get("SESSION_COOKIE_DOMAIN")

# Ensure correct scheme/host behind Railway proxy
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["expensetracker-production-2084.up.railway.app", "127.0.0.1", "localhost", "*"],
)

session_kwargs = {
    "secret_key": SESSION_SECRET_KEY,
    "same_site": COOKIE_SAMESITE,
    "https_only": HTTPS_ONLY,
    "max_age": 86400,  # 24 hours
    "session_cookie": "session",
}
if SESSION_COOKIE_DOMAIN:
    session_kwargs["domain"] = SESSION_COOKIE_DOMAIN

# Log session configuration for debugging
print(f"Session configuration: https_only={HTTPS_ONLY}, same_site={COOKIE_SAMESITE}, domain={SESSION_COOKIE_DOMAIN}, is_production={is_production}")
print(f"Session kwargs: {session_kwargs}")

app.add_middleware(SessionMiddleware, **session_kwargs)

from .services.logging_service import configure_logging, redirect_prints_to_logs
from .services.production_logging import setup_production_logging, log_environment_info

# --- logging (writes tracebacks to logs/server.log) ---
LOG_DIR = ROOT_DIR / "logs"

# Check if we're in production (Railway deployment)
is_production = os.environ.get("RAILWAY_ENVIRONMENT") is not None or os.environ.get("ENVIRONMENT") == "production"

if is_production:
    setup_production_logging(LOG_DIR)
    log_environment_info()
else:
    configure_logging(LOG_DIR)

logger = logging.getLogger(__name__)

# Redirect print statements to logs for production debugging
print_handler = redirect_prints_to_logs()
print_handler.__enter__()

from fastapi.responses import JSONResponse, RedirectResponse
from . import db
from .auth import public, build_public_route_matchers
from .services.cron_service import CronService
from .services.auth_middleware import AuthMiddleware

# --- include routers (אחרי app = FastAPI) ---
from .routes.pages import router as pages_router
from .routes.partials import router as partials_router
from .routes.debug_logs import router as debug_logs_router
from .api.transactions import router as transactions_api
from .api.recurrences import router as recurrences_api, system_router as system_api
from .api.backup import router as backup_api
from .api.statistics import router as statistics_api

app.include_router(pages_router)
app.include_router(partials_router)
app.include_router(debug_logs_router)
app.include_router(transactions_api)
app.include_router(recurrences_api)
app.include_router(system_api)
app.include_router(backup_api)
app.include_router(statistics_api)

# Build public route matchers from routes decorated with @public
PUBLIC_ROUTE_MATCHERS = build_public_route_matchers(app)

# --- auth middleware (must be added AFTER session middleware) ---
auth_enabled_env = os.environ.get("AUTH_ENABLED", "1")
running_pytest = os.environ.get("PYTEST_CURRENT_TEST") is not None
# Allow disabling auth only under pytest
auth_enabled = not (auth_enabled_env != "1" and running_pytest)

# Add AuthMiddleware - this must be after SessionMiddleware
app.add_middleware(AuthMiddleware, public_route_matchers=PUBLIC_ROUTE_MATCHERS, auth_enabled=auth_enabled)

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


# (Old function-based auth middleware removed in favor of class-based one above)
