# --- imports ---
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path as FSPath
import os
import logging
import importlib

# --- create app ---
app = FastAPI(title="CoupleBudget Local", version="0.1.0")

# --- templates & static (מצביעים ל-frontend) ---
ROOT_DIR = FSPath(__file__).resolve().parents[2]   # .../expense_tracker/app
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

from fastapi.responses import JSONResponse
@app.middleware("http")
async def catch_exceptions_middleware(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled exception while processing request %s %s", request.method, request.url)
        return JSONResponse({"error": "Internal server error"}, status_code=500)

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

# --- startup/shutdown (אופציונלי) ---
from . import db, recurrence

@app.on_event("startup")
def on_startup() -> None:
    db.initialise_database()
    try:
        inserted = recurrence.apply_recurring()
        if inserted:
            print(f"Applied {inserted} recurring transactions on startup.")
    except Exception as exc:
        print(f"Failed to apply recurring transactions: {exc}")

    # dynamically import backup to avoid circular import issues and catch errors
    if os.getenv("COUPLEBUDGET_BACKUP_ON_START", "0") in {"1","true","True","yes"}:
        try:
            backup = importlib.import_module(".api.backup", package=__package__)
            path = backup.create_backup()
            print(f"Startup backup created: {path.name}")
        except Exception as exc:
            # keep printing to console for immediate visibility and also log full traceback
            print(f"Failed to create startup backup: {exc}")
            logger.exception("Startup backup failed")

@app.on_event("shutdown")
def on_shutdown() -> None:
    if os.getenv("COUPLEBUDGET_BACKUP_ON_SHUTDOWN", "1") in {"1","true","True","yes"}:
        try:
            backup = importlib.import_module(".api.backup", package=__package__)
            path = backup.create_backup()
            print(f"Shutdown backup created: {path.name}")
        except Exception as exc:
            print(f"Failed to create startup backup: {exc}")
            logger.exception("Shutdown backup failed")
