from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    TaskCreate,
    TaskUpdate,
)
from ...services.people import valid_owner

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Tasks ──────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM wedding_tasks ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def _task_owner(db_conn: sqlite3.Connection, owner: str | None) -> str | None:
    try:
        return valid_owner(db_conn, owner)
    except ValueError:
        raise HTTPException(status_code=422, detail="אחראי לא מוכר")


@router.post("/tasks", status_code=201)
async def create_task(body: TaskCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="יש להזין כותרת")
    cur = db_conn.execute(
        "INSERT INTO wedding_tasks (title, category, due_date, priority, notes, owner) VALUES (?,?,?,?,?,?)",
        (title, body.category, body.due_date or None, body.priority, body.notes,
         _task_owner(db_conn, body.owner)),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_tasks WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_tasks WHERE id=?", (task_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return dict(existing)
    if "owner" in updates:
        updates["owner"] = _task_owner(db_conn, updates["owner"])
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db_conn.execute(
        f"UPDATE wedding_tasks SET {set_clause} WHERE id=?",
        (*updates.values(), task_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_tasks WHERE id=?", (task_id,)).fetchone())


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_tasks WHERE id=?", (task_id,))
    db_conn.commit()
