"""
Home renovation module pages.

The module has its own look and its own navigation — it is deliberately not
part of the finances/wedding layout, so it stays simple for someone who only
ever uses this one section.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path as FSPath
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..db import get_db_conn
from ..services.access import can_edit_renovation, normalise_username

ROOT_DIR = FSPath(__file__).resolve().parents[3]
TEMPLATES_DIR = ROOT_DIR / "frontend" / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(prefix="/renovation", tags=["renovation"])

TASK_STATUS_LABELS = {
    "todo": "לביצוע",
    "in_progress": "בתהליך",
    "done": "הושלם",
}

SUPPLY_STATUS_LABELS = {
    "needed": "חסר",
    "bought": "יש",
}

IDEA_STATUS_LABELS = {
    "new": "חדש",
    "considering": "שוקלים",
    "approved": "אושר",
    "rejected": "לא מתאים",
}

# Hebrew display names for the header greeting.
USER_DISPLAY_NAMES = {
    "YOSEF": "יוסף",
    "TSAHALA": "צהלה",
    "KARINA": "קארינה",
}


def _current_user(request: Request) -> Any:
    user = getattr(request.state, "user", None)
    if user:
        return user
    try:
        return request.session.get("user")
    except Exception:
        return None


def _base_context(request: Request, db_conn: sqlite3.Connection) -> dict:
    user = _current_user(request)
    rooms = [dict(r) for r in db_conn.execute(
        "SELECT * FROM renovation_rooms ORDER BY sort_order ASC, id ASC"
    ).fetchall()]
    username = normalise_username(user)
    return {
        "request": request,
        "rooms": rooms,
        "username": username,
        "user_display_name": USER_DISPLAY_NAMES.get(username, username.title()),
        "can_edit": can_edit_renovation(user),
        "today": date.today().isoformat(),
        "task_status_labels": TASK_STATUS_LABELS,
        "idea_status_labels": IDEA_STATUS_LABELS,
        "supply_status_labels": SUPPLY_STATUS_LABELS,
    }


def _task_rows(db_conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in db_conn.execute("""
        SELECT t.*, r.name AS room_name, r.icon AS room_icon
        FROM renovation_tasks t
        LEFT JOIN renovation_rooms r ON r.id = t.room_id
        ORDER BY
            CASE t.status WHEN 'in_progress' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END,
            CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            COALESCE(t.due_date, '9999-12-31') ASC,
            t.id DESC
    """).fetchall()]


def _idea_rows(db_conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in db_conn.execute("""
        SELECT i.*, r.name AS room_name, r.icon AS room_icon
        FROM renovation_ideas i
        LEFT JOIN renovation_rooms r ON r.id = i.room_id
        ORDER BY i.updated_at DESC, i.id DESC
    """).fetchall()]


def _supply_rows(db_conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in db_conn.execute("""
        SELECT s.*, r.name AS room_name, r.icon AS room_icon, t.title AS task_title
        FROM renovation_supplies s
        LEFT JOIN renovation_rooms r ON r.id = s.room_id
        LEFT JOIN renovation_tasks t ON t.id = s.task_id
        ORDER BY
            CASE s.status WHEN 'needed' THEN 1 ELSE 2 END,
            r.sort_order IS NULL, r.sort_order ASC,
            s.id DESC
    """).fetchall()]


def _attach_supplies(rows: list[dict], supplies: list[dict], key: str) -> None:
    """Hang each row's supplies (and its missing count) off the row itself."""
    by_parent: dict = {}
    for supply in supplies:
        by_parent.setdefault(supply[key], []).append(supply)
    for row in rows:
        items = by_parent.get(row["id"], [])
        row["supplies"] = items
        row["supplies_missing"] = len([s for s in items if s["status"] == "needed"])


def _int_or_none(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def renovation_dashboard(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    ctx = _base_context(request, db_conn)
    tasks = _task_rows(db_conn)
    ideas = _idea_rows(db_conn)
    supplies = _supply_rows(db_conn)
    today = ctx["today"]
    missing_supplies = [s for s in supplies if s["status"] == "needed"]

    done = [t for t in tasks if t["status"] == "done"]
    open_tasks = [t for t in tasks if t["status"] != "done"]
    overdue = [t for t in open_tasks if t.get("due_date") and t["due_date"] < today]
    progress = round(len(done) * 100 / len(tasks)) if tasks else 0

    # Per-room progress, ordered by the room list so the dashboard matches the
    # rooms page.
    room_progress = []
    for room in ctx["rooms"]:
        room_tasks = [t for t in tasks if t["room_id"] == room["id"]]
        room_done = [t for t in room_tasks if t["status"] == "done"]
        room_progress.append({
            **room,
            "total": len(room_tasks),
            "done": len(room_done),
            "percent": round(len(room_done) * 100 / len(room_tasks)) if room_tasks else 0,
        })

    ctx.update({
        "total_tasks": len(tasks),
        "done_tasks": len(done),
        "open_tasks": len(open_tasks),
        "in_progress_tasks": len([t for t in tasks if t["status"] == "in_progress"]),
        "overdue_tasks": overdue,
        "progress": progress,
        "upcoming": [t for t in open_tasks if t.get("due_date")][:5],
        "recent_ideas": ideas[:6],
        "total_ideas": len(ideas),
        "approved_ideas": len([i for i in ideas if i["status"] == "approved"]),
        "room_progress": room_progress,
        "total_supplies": len(supplies),
        "missing_supplies_count": len(missing_supplies),
        "missing_supplies": missing_supplies[:6],
    })
    return templates.TemplateResponse("renovation/index.html", ctx)


@router.get("/tasks", response_class=HTMLResponse)
async def renovation_tasks(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    ctx = _base_context(request, db_conn)
    status_filter = request.query_params.get("status") or ""
    room_filter = _int_or_none(request.query_params.get("room"))

    tasks = _task_rows(db_conn)
    _attach_supplies(tasks, _supply_rows(db_conn), "task_id")
    if status_filter in TASK_STATUS_LABELS:
        tasks = [t for t in tasks if t["status"] == status_filter]
    elif status_filter == "open":
        tasks = [t for t in tasks if t["status"] != "done"]
    if room_filter is not None:
        tasks = [t for t in tasks if t["room_id"] == room_filter]

    ctx.update({
        "tasks": tasks,
        "status_filter": status_filter,
        "room_filter": room_filter,
    })
    return templates.TemplateResponse("renovation/tasks.html", ctx)


@router.get("/ideas", response_class=HTMLResponse)
async def renovation_ideas(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    ctx = _base_context(request, db_conn)
    status_filter = request.query_params.get("status") or ""
    room_filter = _int_or_none(request.query_params.get("room"))

    ideas = _idea_rows(db_conn)
    if status_filter in IDEA_STATUS_LABELS:
        ideas = [i for i in ideas if i["status"] == status_filter]
    if room_filter is not None:
        ideas = [i for i in ideas if i["room_id"] == room_filter]

    ctx.update({
        "ideas": ideas,
        "status_filter": status_filter,
        "room_filter": room_filter,
    })
    return templates.TemplateResponse("renovation/ideas.html", ctx)


@router.get("/rooms", response_class=HTMLResponse)
async def renovation_rooms(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    ctx = _base_context(request, db_conn)
    tasks = _task_rows(db_conn)
    ideas = _idea_rows(db_conn)
    supplies = _supply_rows(db_conn)

    cards = []
    for room in ctx["rooms"]:
        room_tasks = [t for t in tasks if t["room_id"] == room["id"]]
        room_done = [t for t in room_tasks if t["status"] == "done"]
        room_supplies = [s for s in supplies if s["room_id"] == room["id"]]
        cards.append({
            **room,
            "total": len(room_tasks),
            "done": len(room_done),
            "open": len(room_tasks) - len(room_done),
            "percent": round(len(room_done) * 100 / len(room_tasks)) if room_tasks else 0,
            "ideas": len([i for i in ideas if i["room_id"] == room["id"]]),
            "supplies": len(room_supplies),
            "supplies_missing": len([s for s in room_supplies if s["status"] == "needed"]),
        })

    ctx.update({
        "room_cards": cards,
        "unassigned_tasks": len([t for t in tasks if t["room_id"] is None]),
    })
    return templates.TemplateResponse("renovation/rooms.html", ctx)


@router.get("/supplies", response_class=HTMLResponse)
async def renovation_supplies(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    ctx = _base_context(request, db_conn)
    status_filter = request.query_params.get("status")
    # The shopping list is what people open this page for, so "what's missing"
    # is the default view rather than everything ever added.
    if status_filter is None:
        status_filter = "needed"
    room_filter = _int_or_none(request.query_params.get("room"))
    task_filter = _int_or_none(request.query_params.get("task"))

    supplies = _supply_rows(db_conn)
    missing_total = len([s for s in supplies if s["status"] == "needed"])

    if status_filter in SUPPLY_STATUS_LABELS:
        supplies = [s for s in supplies if s["status"] == status_filter]
    if room_filter is not None:
        supplies = [s for s in supplies if s["room_id"] == room_filter]
    if task_filter is not None:
        supplies = [s for s in supplies if s["task_id"] == task_filter]

    # Group by room so the list reads like an aisle-by-aisle shopping list.
    groups: list[dict] = []
    for room in ctx["rooms"]:
        items = [s for s in supplies if s["room_id"] == room["id"]]
        if items:
            groups.append({"room": room, "items": items})
    loose = [s for s in supplies if s["room_id"] is None]
    if loose:
        groups.append({"room": None, "items": loose})

    ctx.update({
        "groups": groups,
        "supplies_count": len(supplies),
        "missing_total": missing_total,
        "status_filter": status_filter,
        "room_filter": room_filter,
        "task_filter": task_filter,
        "tasks": _task_rows(db_conn),
    })
    return templates.TemplateResponse("renovation/supplies.html", ctx)
