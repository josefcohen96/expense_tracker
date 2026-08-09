"""
Home renovation module API endpoints.
CRUD for rooms, tasks, and ideas.

Every write goes through `_require_editor`, so a user who may only look at the
module (see services/access.py) cannot change data by calling the API directly.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from ..db import get_db_conn
from ..services.access import can_edit_renovation, normalise_username

router = APIRouter(prefix="/api/renovation", tags=["renovation"])

TASK_STATUSES = ("todo", "in_progress", "done")
TASK_PRIORITIES = ("low", "medium", "high")
IDEA_STATUSES = ("new", "considering", "approved", "rejected")
IDEA_COLORS = ("white", "amber", "orange", "green", "teal", "blue", "purple", "pink")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _current_user(request: Request) -> Any:
    user = getattr(request.state, "user", None)
    if user:
        return user
    try:
        return request.session.get("user")
    except Exception:
        return None


def _require_editor(request: Request) -> str:
    """Abort with 403 unless the caller may modify renovation data."""
    user = _current_user(request)
    if not can_edit_renovation(user):
        raise HTTPException(status_code=403, detail="אין לך הרשאה לערוך את נתוני השיפוץ")
    return normalise_username(user)


def _clean(value: Optional[str]) -> Optional[str]:
    """Trim a free-text field, turning blanks into NULL."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _one_of(field: str, allowed: tuple[str, ...]):
    """Reusable pydantic validator that keeps enum-ish columns clean."""
    def _check(cls, v):  # noqa: N805 - pydantic validator signature
        if v is None:
            return v
        if v not in allowed:
            raise ValueError(f"{field} must be one of {allowed}")
        return v
    return _check


def _room_exists(db_conn: sqlite3.Connection, room_id: Optional[int]) -> None:
    if room_id is None:
        return
    row = db_conn.execute("SELECT 1 FROM renovation_rooms WHERE id=?", (room_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="החדר שנבחר לא קיים")


def _apply_updates(
    db_conn: sqlite3.Connection,
    table: str,
    row_id: int,
    updates: dict,
    not_found: str,
) -> dict:
    existing = db_conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail=not_found)
    if not updates:
        return dict(existing)
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db_conn.execute(
        f"UPDATE {table} SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (*updates.values(), row_id),
    )
    db_conn.commit()
    return dict(db_conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone())


# ─── Schemas ─────────────────────────────────────────────────────────────────

class RoomCreate(BaseModel):
    name: str
    icon: str = "🏠"
    notes: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name is required")
        return v.strip()


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    notes: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: Optional[int] = None


class TaskCreate(BaseModel):
    title: str
    room_id: Optional[int] = None
    status: str = "todo"
    priority: str = "medium"
    due_date: Optional[str] = None
    notes: Optional[str] = None
    link_url: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title is required")
        return v.strip()

    _status_ok = field_validator("status")(_one_of("status", TASK_STATUSES))
    _priority_ok = field_validator("priority")(_one_of("priority", TASK_PRIORITIES))


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    room_id: Optional[int] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    link_url: Optional[str] = None

    _status_ok = field_validator("status")(_one_of("status", TASK_STATUSES))
    _priority_ok = field_validator("priority")(_one_of("priority", TASK_PRIORITIES))


class IdeaCreate(BaseModel):
    title: str
    description: Optional[str] = None
    room_id: Optional[int] = None
    status: str = "new"
    color: str = "white"
    image_url: Optional[str] = None
    link_url: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title is required")
        return v.strip()

    _status_ok = field_validator("status")(_one_of("status", IDEA_STATUSES))
    _color_ok = field_validator("color")(_one_of("color", IDEA_COLORS))


class IdeaUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    room_id: Optional[int] = None
    status: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = None
    link_url: Optional[str] = None

    _status_ok = field_validator("status")(_one_of("status", IDEA_STATUSES))
    _color_ok = field_validator("color")(_one_of("color", IDEA_COLORS))


# ─── Rooms ───────────────────────────────────────────────────────────────────

@router.get("/rooms")
async def list_rooms(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM renovation_rooms ORDER BY sort_order ASC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/rooms", status_code=201)
async def create_room(
    body: RoomCreate,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    _require_editor(request)
    cur = db_conn.execute(
        "INSERT INTO renovation_rooms (name, icon, notes, image_url, sort_order) VALUES (?,?,?,?,?)",
        (body.name, body.icon or "🏠", _clean(body.notes), _clean(body.image_url), body.sort_order),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM renovation_rooms WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/rooms/{room_id}")
async def update_room(
    room_id: int,
    body: RoomUpdate,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    _require_editor(request)
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates:
        name = (updates["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="שם החדר לא יכול להיות ריק")
        updates["name"] = name
    for field in ("notes", "image_url"):
        if field in updates:
            updates[field] = _clean(updates[field])
    existing = db_conn.execute("SELECT * FROM renovation_rooms WHERE id=?", (room_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="החדר לא נמצא")
    if not updates:
        return dict(existing)
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db_conn.execute(
        f"UPDATE renovation_rooms SET {set_clause} WHERE id=?",
        (*updates.values(), room_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM renovation_rooms WHERE id=?", (room_id,)).fetchone())


@router.delete("/rooms/{room_id}", status_code=204)
async def delete_room(
    room_id: int,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    _require_editor(request)
    # Tasks and ideas survive the room; they simply become unassigned. The
    # ON DELETE SET NULL rule needs foreign_keys=ON, which get_connection sets,
    # but we clear them explicitly so an old connection can't orphan the rows.
    db_conn.execute("UPDATE renovation_tasks SET room_id=NULL WHERE room_id=?", (room_id,))
    db_conn.execute("UPDATE renovation_ideas SET room_id=NULL WHERE room_id=?", (room_id,))
    db_conn.execute("DELETE FROM renovation_rooms WHERE id=?", (room_id,))
    db_conn.commit()


# ─── Tasks ───────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute("""
        SELECT t.*, r.name AS room_name, r.icon AS room_icon
        FROM renovation_tasks t
        LEFT JOIN renovation_rooms r ON r.id = t.room_id
        ORDER BY
            CASE t.status WHEN 'in_progress' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END,
            CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            COALESCE(t.due_date, '9999-12-31') ASC,
            t.id DESC
    """).fetchall()
    return [dict(r) for r in rows]


@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskCreate,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    username = _require_editor(request)
    _room_exists(db_conn, body.room_id)
    cur = db_conn.execute(
        "INSERT INTO renovation_tasks (title, room_id, status, priority, due_date, notes, link_url, created_by) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            body.title,
            body.room_id,
            body.status,
            body.priority,
            _clean(body.due_date),
            _clean(body.notes),
            _clean(body.link_url),
            username,
        ),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM renovation_tasks WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    body: TaskUpdate,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    _require_editor(request)
    updates = body.model_dump(exclude_unset=True)
    if "title" in updates:
        title = (updates["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail="שם המשימה לא יכול להיות ריק")
        updates["title"] = title
    for field in ("due_date", "notes", "link_url"):
        if field in updates:
            updates[field] = _clean(updates[field])
    if "room_id" in updates:
        _room_exists(db_conn, updates["room_id"])
    return _apply_updates(db_conn, "renovation_tasks", task_id, updates, "המשימה לא נמצאה")


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    _require_editor(request)
    db_conn.execute("DELETE FROM renovation_tasks WHERE id=?", (task_id,))
    db_conn.commit()


# ─── Ideas ───────────────────────────────────────────────────────────────────

@router.get("/ideas")
async def list_ideas(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute("""
        SELECT i.*, r.name AS room_name, r.icon AS room_icon
        FROM renovation_ideas i
        LEFT JOIN renovation_rooms r ON r.id = i.room_id
        ORDER BY i.updated_at DESC, i.id DESC
    """).fetchall()
    return [dict(r) for r in rows]


@router.post("/ideas", status_code=201)
async def create_idea(
    body: IdeaCreate,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    username = _require_editor(request)
    _room_exists(db_conn, body.room_id)
    cur = db_conn.execute(
        "INSERT INTO renovation_ideas (title, description, room_id, status, color, image_url, link_url, created_by) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            body.title,
            _clean(body.description),
            body.room_id,
            body.status,
            body.color,
            _clean(body.image_url),
            _clean(body.link_url),
            username,
        ),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM renovation_ideas WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/ideas/{idea_id}")
async def update_idea(
    idea_id: int,
    body: IdeaUpdate,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    _require_editor(request)
    updates = body.model_dump(exclude_unset=True)
    if "title" in updates:
        title = (updates["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail="שם הרעיון לא יכול להיות ריק")
        updates["title"] = title
    for field in ("description", "image_url", "link_url"):
        if field in updates:
            updates[field] = _clean(updates[field])
    if "room_id" in updates:
        _room_exists(db_conn, updates["room_id"])
    return _apply_updates(db_conn, "renovation_ideas", idea_id, updates, "הרעיון לא נמצא")


@router.delete("/ideas/{idea_id}", status_code=204)
async def delete_idea(
    idea_id: int,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    _require_editor(request)
    db_conn.execute("DELETE FROM renovation_ideas WHERE id=?", (idea_id,))
    db_conn.commit()
