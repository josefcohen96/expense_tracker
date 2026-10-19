from __future__ import annotations

import os
import sqlite3
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from ...db import get_db_conn
from ...schemas.wedding import (
    GuestCreate,
    GuestUpdate,
)

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Guests ─────────────────────────────────────────────────────────────────

@router.get("/guests")
async def list_guests(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute("SELECT * FROM wedding_guests ORDER BY group_name, name").fetchall()
    return [dict(r) for r in rows]


@router.post("/guests", status_code=201)
async def create_guest(body: GuestCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    cur = db_conn.execute(
        """INSERT INTO wedding_guests
           (name, phone, group_name, status, plus_one, plus_one_name, children_count, needs_transport, staying_overnight, table_number, notes, meal_type, food_notes, plus_one_meal_type)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (body.name, body.phone, body.group_name, body.status,
         body.plus_one, body.plus_one_name, body.children_count,
         body.needs_transport, body.staying_overnight, body.table_number, body.notes,
         body.meal_type, body.food_notes, body.plus_one_meal_type),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_guests WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/guests/{guest_id}")
async def update_guest(guest_id: int, body: GuestUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_guests WHERE id=?", (guest_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Guest not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return dict(existing)
    # If marking guest declined, clean up seating/room assignments to keep state consistent
    new_status = fields.get("status")
    if new_status == "declined":
        db_conn.execute("DELETE FROM wedding_seating_assignments WHERE guest_id=?", (guest_id,))
        db_conn.execute("DELETE FROM wedding_room_assignments WHERE guest_id=?", (guest_id,))
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db_conn.execute(
        f"UPDATE wedding_guests SET {set_clause} WHERE id=?",
        (*fields.values(), guest_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_guests WHERE id=?", (guest_id,)).fetchone())


@router.delete("/guests/{guest_id}", status_code=204)
async def delete_guest(guest_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    # Explicitly clean dependent rows since FK CASCADEs may not be enforced
    # (SQLite requires PRAGMA foreign_keys=ON which we cannot rely on per-connection).
    db_conn.execute("DELETE FROM wedding_seating_assignments WHERE guest_id=?", (guest_id,))
    db_conn.execute("DELETE FROM wedding_room_assignments WHERE guest_id=?", (guest_id,))
    db_conn.execute("DELETE FROM wedding_guests WHERE id=?", (guest_id,))
    db_conn.commit()


# ─── Invite Tokens ───────────────────────────────────────────────────────────

# Default base URL used when no request context is available. Can be overridden by
# the PUBLIC_BASE_URL environment variable for staging/custom domains.
DEFAULT_BASE_URL = "https://expensetracker-production-2084.up.railway.app"


def _resolve_base_url(request: Request | None) -> str:
    """Prefer env override, then request scheme+host, then production fallback."""
    env_url = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    if request is not None:
        try:
            base = str(request.base_url).rstrip("/")
            if base:
                return base
        except Exception:
            pass
    return DEFAULT_BASE_URL


@router.post("/guests/{guest_id}/generate-invite")
async def generate_invite(guest_id: int, request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    guest = db_conn.execute("SELECT * FROM wedding_guests WHERE id=?", (guest_id,)).fetchone()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    token = uuid.uuid4().hex
    db_conn.execute("UPDATE wedding_guests SET invite_token=? WHERE id=?", (token, guest_id))
    db_conn.commit()
    link = f"{_resolve_base_url(request)}/invite/{token}"
    return {"token": token, "link": link, "guest_id": guest_id, "guest_name": guest["name"]}


@router.get("/guests/{guest_id}/invite-link")
async def get_invite_link(guest_id: int, request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    guest = db_conn.execute("SELECT id, name, invite_token FROM wedding_guests WHERE id=?", (guest_id,)).fetchone()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    token = guest["invite_token"]
    if not token:
        return {"link": None, "guest_id": guest_id}
    link = f"{_resolve_base_url(request)}/invite/{token}"
    return {"token": token, "link": link, "guest_id": guest_id, "guest_name": guest["name"]}
