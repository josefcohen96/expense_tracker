"""The app's one Jinja environment, shared by every HTML route module."""
from __future__ import annotations

import sqlite3
from pathlib import Path as FSPath

from fastapi.templating import Jinja2Templates

from . import db as _db
from .services import wedding_plan

# Frontend paths
ROOT_DIR = FSPath(__file__).resolve().parents[2]  # .../expense_tracker/app
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _wedding_header() -> dict:
    """Countdown + open-task count for the wedding section header (called from wedding/base.html)."""
    conn = _db.get_connection()
    try:
        info = wedding_plan.countdown(conn)
        info["planning_counts"] = {
            "/wedding/tasks": info["open"],
        }
        return info
    except sqlite3.Error:
        return {"days_left": None, "planning_counts": {}}
    finally:
        conn.close()


templates.env.globals["wedding_header"] = _wedding_header
