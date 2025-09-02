# --- imports ---
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path as FSPath
import os
import logging
import importlib
from datetime import datetime, date
import sqlite3

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
file_handler.setLevel(logging.INFO)  # Back to INFO since cache service uses INFO
file_handler.setFormatter(formatter)

# stream handler (console)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)  # Back to INFO since cache service uses INFO
stream_handler.setFormatter(formatter)

# root logger: ensure level and handlers (avoid duplicates)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)  # Back to INFO since cache service uses INFO
# add file handler if not present
if not any(getattr(h, "baseFilename", None) == str(LOG_PATH) for h in root_logger.handlers if isinstance(h, logging.FileHandler)):
    root_logger.addHandler(file_handler)
# add stream handler if not present
if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
    root_logger.addHandler(stream_handler)

# also attach file handler to uvicorn loggers so their output goes to the log file
for uv_logger_name in ("uvicorn.error", "uvicorn.access", "uvicorn"):
    lg = logging.getLogger(uv_logger_name)
    lg.setLevel(logging.INFO)  # Back to INFO since cache service uses INFO
    if not any(getattr(h, "baseFilename", None) == str(LOG_PATH) for h in lg.handlers if isinstance(h, logging.FileHandler)):
        lg.addHandler(file_handler)

logger = logging.getLogger(__name__)

from fastapi.responses import JSONResponse

# Global variable to track daily progress update
_daily_progress_updated = False

@app.middleware("http")
async def catch_exceptions_middleware(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled exception while processing request %s %s", request.method, request.url)
        return JSONResponse({"error": "Internal server error"}, status_code=500)

@app.middleware("http")
async def challenge_progress_middleware(request, call_next):
    """Check and update daily challenge progress if needed."""
    global _daily_progress_updated
    
    # Only run once per server session
    if not _daily_progress_updated:
        try:
            _check_and_run_daily_progress_update()
            _daily_progress_updated = True
        except Exception as exc:
            logger.exception("Daily challenge progress update failed")
    
    return await call_next(request)

def _check_and_run_daily_progress_update():
    """Check if daily progress update is needed and run it if so."""
    today = date.today()
    
    # Get database path
    db_path = db.get_db_path()
    
    with sqlite3.connect(db_path) as db_conn:
        db_conn.row_factory = sqlite3.Row
        
        # Check if we've already done daily update today
        last_daily_update = db_conn.execute("""
            SELECT value FROM system_settings WHERE key = 'last_daily_progress_update'
        """).fetchone()
        
        if last_daily_update:
            last_date = datetime.strptime(last_daily_update["value"], "%Y-%m-%d").date()
            # If we already updated today, skip
            if last_date == today:
                return
        
        # Run daily progress update
        print("Running daily challenge progress update...")
        cron_service = CronService(db_path)
        
        # Run the update synchronously
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If event loop is already running, skip the update
                print("Event loop is already running, skipping daily progress update")
                return
            loop.run_until_complete(cron_service.update_active_challenge_progress())
        except RuntimeError:
            # If no event loop exists, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(cron_service.update_active_challenge_progress())
        
        # Update last daily update date
        db_conn.execute("""
            INSERT OR REPLACE INTO system_settings (key, value) 
            VALUES ('last_daily_progress_update', ?)
        """, (today.isoformat(),))
        db_conn.commit()
        
        print("Daily challenge progress update completed")

# --- include routers (אחרי app = FastAPI) ---
from .routes.pages import router as pages_router
from .routes.partials import router as partials_router
from .api.transactions import router as transactions_api
from .api.recurrences import router as recurrences_api, system_router as system_api
from .api.backup import router as backup_api
from .api.statistics import router as statistics_api
from .api.challenges import router as challenges_api
from .api.whatsapp import router as whatsapp_router

app.include_router(pages_router)
app.include_router(partials_router)
app.include_router(transactions_api)
app.include_router(recurrences_api)
app.include_router(system_api)
app.include_router(backup_api)
app.include_router(statistics_api)
app.include_router(challenges_api)
app.include_router(whatsapp_router)

# --- startup/shutdown (אופציונלי) ---
from . import db, recurrence
from .services.cron_service import CronService
from datetime import datetime, date
import sqlite3

# Global variable to track if monthly evaluation has been done
_monthly_evaluation_done = False

@app.on_event("startup")
def on_startup() -> None:
    db.initialise_database()
    try:
        inserted = recurrence.apply_recurring()
        if inserted:
            print(f"Applied {inserted} recurring transactions on startup.")
    except Exception as exc:
        print(f"Failed to apply recurring transactions: {exc}")

    # Check if monthly challenge evaluation is needed
    global _monthly_evaluation_done
    if not _monthly_evaluation_done:
        try:
            _check_and_run_monthly_evaluation()
            _monthly_evaluation_done = True
        except Exception as exc:
            print(f"Failed to run monthly challenge evaluation: {exc}")
            logger.exception("Monthly challenge evaluation failed")

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

def _check_and_run_monthly_evaluation():
    """Check if monthly evaluation is needed and run it if so."""
    today = date.today()
    
    # Get database path
    db_path = db.get_db_path()
    
    with sqlite3.connect(db_path) as db_conn:
        db_conn.row_factory = sqlite3.Row
        
        # Check if we've already done evaluation for this month
        last_evaluation = db_conn.execute("""
            SELECT value FROM system_settings WHERE key = 'last_monthly_evaluation'
        """).fetchone()
        
        if last_evaluation:
            last_date = datetime.strptime(last_evaluation["value"], "%Y-%m-%d").date()
            # If we already evaluated this month, skip
            if last_date.year == today.year and last_date.month == today.month:
                print("Monthly challenge evaluation already done this month")
                return
        
        # Run monthly evaluation
        print("Running monthly challenge evaluation...")
        cron_service = CronService(db_path)
        
        # Run the evaluation synchronously
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If event loop is already running, skip the evaluation
                print("Event loop is already running, skipping monthly evaluation")
                return
            loop.run_until_complete(cron_service.evaluate_all_challenges())
        except RuntimeError:
            # If no event loop exists, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(cron_service.evaluate_all_challenges())
        
        # Update last evaluation date
        db_conn.execute("""
            INSERT OR REPLACE INTO system_settings (key, value) 
            VALUES ('last_monthly_evaluation', ?)
        """, (today.isoformat(),))
        db_conn.commit()
        
        print("Monthly challenge evaluation completed")

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
