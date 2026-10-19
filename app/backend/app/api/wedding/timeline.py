from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    TimelineEventCreate,
    TimelineEventUpdate,
)

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Timeline Events ──────────────────────────────────────────────────────────

@router.get("/timeline-events")
async def list_timeline_events(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM wedding_timeline_events ORDER BY day, start_time"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/timeline-events", status_code=201)
async def create_timeline_event(body: TimelineEventCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    cur = db_conn.execute(
        "INSERT INTO wedding_timeline_events (day, title, description, start_time, end_time, category) VALUES (?,?,?,?,?,?)",
        (body.day, body.title, body.description, body.start_time, body.end_time, body.category),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_timeline_events WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/timeline-events/{event_id}")
async def update_timeline_event(event_id: int, body: TimelineEventUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_timeline_events WHERE id=?", (event_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return dict(existing)
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db_conn.execute(
        f"UPDATE wedding_timeline_events SET {set_clause} WHERE id=?",
        (*fields.values(), event_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_timeline_events WHERE id=?", (event_id,)).fetchone())


@router.delete("/timeline-events/{event_id}", status_code=204)
async def delete_timeline_event(event_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_timeline_events WHERE id=?", (event_id,))
    db_conn.commit()
