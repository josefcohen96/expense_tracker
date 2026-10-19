from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    IdeaCreate,
    IdeaUpdate,
)

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Ideas ────────────────────────────────────────────────────────────────────

@router.get("/ideas")
async def list_ideas(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM wedding_ideas ORDER BY CASE status WHEN 'approved' THEN 1 WHEN 'new' THEN 2 WHEN 'considering' THEN 3 ELSE 4 END, created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/ideas", status_code=201)
async def create_idea(body: IdeaCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    cur = db_conn.execute(
        "INSERT INTO wedding_ideas (title, description, category, status, color) VALUES (?,?,?,?,?)",
        (body.title, body.description, body.category, body.status, body.color),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_ideas WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/ideas/{idea_id}")
async def update_idea(idea_id: int, body: IdeaUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_ideas WHERE id=?", (idea_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Idea not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return dict(existing)
    set_clause = ", ".join(f"{k}=?" for k in fields) + ", updated_at=CURRENT_TIMESTAMP"
    db_conn.execute(
        f"UPDATE wedding_ideas SET {set_clause} WHERE id=?",
        (*fields.values(), idea_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_ideas WHERE id=?", (idea_id,)).fetchone())


@router.delete("/ideas/{idea_id}", status_code=204)
async def delete_idea(idea_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_ideas WHERE id=?", (idea_id,))
    db_conn.commit()
