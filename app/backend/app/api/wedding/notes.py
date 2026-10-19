from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    NoteCreate,
    NoteUpdate,
)

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Notes ────────────────────────────────────────────────────────────────────

@router.get("/notes")
async def list_notes(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM wedding_notes ORDER BY pinned DESC, updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/notes", status_code=201)
async def create_note(body: NoteCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    cur = db_conn.execute(
        "INSERT INTO wedding_notes (title, content, color, pinned) VALUES (?,?,?,?)",
        (body.title, body.content, body.color, body.pinned),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_notes WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/notes/{note_id}")
async def update_note(note_id: int, body: NoteUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_notes WHERE id=?", (note_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return dict(existing)
    set_clause = ", ".join(f"{k}=?" for k in fields) + ", updated_at=CURRENT_TIMESTAMP"
    db_conn.execute(
        f"UPDATE wedding_notes SET {set_clause} WHERE id=?",
        (*fields.values(), note_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_notes WHERE id=?", (note_id,)).fetchone())


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_notes WHERE id=?", (note_id,))
    db_conn.commit()
