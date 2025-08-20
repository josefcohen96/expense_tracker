# --- imports ---
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path as FSPath
import os

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
from .api import backup

@app.on_event("startup")
def on_startup() -> None:
    db.initialise_database()
    try:
        inserted = recurrence.apply_recurring()
        if inserted:
            print(f"Applied {inserted} recurring transactions on startup.")
    except Exception as exc:
        print(f"Failed to apply recurring transactions: {exc}")
    if os.getenv("COUPLEBUDGET_BACKUP_ON_START", "0") in {"1","true","True","yes"}:
        try:
            path = backup.create_backup()
            print(f"Startup backup created: {path.name}")
        except Exception as exc:
            print(f"Failed to create startup backup: {exc}")

@app.on_event("shutdown")
def on_shutdown() -> None:
    if os.getenv("COUPLEBUDGET_BACKUP_ON_SHUTDOWN", "1") in {"1","true","True","yes"}:
        try:
            path = backup.create_backup()
            print(f"Shutdown backup created: {path.name}")
        except Exception as exc:
            print(f"Failed to create startup backup: {exc}")
