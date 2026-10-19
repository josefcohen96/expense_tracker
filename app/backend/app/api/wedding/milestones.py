from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    MilestoneCreate,
    MilestoneUpdate,
)
from ...services import wedding_plan

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Milestones ──────────────────────────────────────────────────────────────

def _milestone_view(db_conn: sqlite3.Connection, milestone_id: int) -> dict:
    view = wedding_plan.list_milestones(db_conn)
    return next(m for m in view["milestones"] if m["id"] == milestone_id)


@router.get("/milestones")
async def list_milestones(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    """Milestones with dates computed from the wedding date (custom_date wins)."""
    return wedding_plan.list_milestones(db_conn)


@router.post("/milestones", status_code=201)
async def create_milestone(body: MilestoneCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="יש להזין שם")
    kind = body.kind if body.kind in wedding_plan.MILESTONE_KINDS else "general"
    next_order = db_conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM wedding_milestones").fetchone()[0]
    cur = db_conn.execute(
        "INSERT INTO wedding_milestones (title, offset_days, kind, sort_order) VALUES (?,?,?,?)",
        (title, body.offset_days, kind, next_order),
    )
    db_conn.commit()
    return _milestone_view(db_conn, cur.lastrowid)


@router.put("/milestones/{milestone_id}")
async def update_milestone(milestone_id: int, body: MilestoneUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    if not db_conn.execute("SELECT 1 FROM wedding_milestones WHERE id=?", (milestone_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Milestone not found")
    updates = body.model_dump(exclude_unset=True)
    if "title" in updates:
        updates["title"] = (updates["title"] or "").strip()
        if not updates["title"]:
            raise HTTPException(status_code=422, detail="יש להזין שם")
    if "completed" in updates:
        updates["completed"] = 1 if updates["completed"] else 0
    if updates.get("custom_date"):
        try:
            date.fromisoformat(updates["custom_date"])
        except ValueError:
            raise HTTPException(status_code=422, detail="תאריך לא תקין")
    elif "custom_date" in updates:
        updates["custom_date"] = None
    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        db_conn.execute(
            f"UPDATE wedding_milestones SET {set_clause} WHERE id=?",
            (*updates.values(), milestone_id),
        )
        db_conn.commit()
    return _milestone_view(db_conn, milestone_id)


@router.delete("/milestones/{milestone_id}", status_code=204)
async def delete_milestone(milestone_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_milestones WHERE id=?", (milestone_id,))
    db_conn.commit()
