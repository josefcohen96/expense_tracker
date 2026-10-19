from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    RoomCreate,
    RoomUpdate,
)

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Rooms ───────────────────────────────────────────────────────────────────

@router.get("/rooms")
async def list_rooms(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rooms = [dict(r) for r in db_conn.execute("SELECT * FROM wedding_rooms ORDER BY id").fetchall()]
    assignments = db_conn.execute(
        """SELECT ra.room_id, ra.guest_id, g.name AS guest_name,
                  g.plus_one, g.plus_one_name, g.children_count
           FROM wedding_room_assignments ra
           JOIN wedding_guests g ON g.id = ra.guest_id"""
    ).fetchall()
    by_room = {}
    for a in assignments:
        by_room.setdefault(a["room_id"], []).append(dict(a))
    for room in rooms:
        room["assigned"] = by_room.get(room["id"], [])
        room["occupancy"] = sum(
            1 + (1 if a["plus_one"] else 0) + (a["children_count"] or 0)
            for a in room["assigned"]
        )
    return rooms


@router.post("/rooms", status_code=201)
async def create_room(body: RoomCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    if body.max_capacity < 1:
        raise HTTPException(status_code=400, detail="max_capacity must be ≥ 1")
    cur = db_conn.execute(
        "INSERT INTO wedding_rooms (name, room_type, max_capacity, notes) VALUES (?,?,?,?)",
        (body.name, body.room_type, body.max_capacity, body.notes),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_rooms WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/rooms/{room_id}")
async def update_room(room_id: int, body: RoomUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_rooms WHERE id=?", (room_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Room not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return dict(existing)
    # Defend against capacity ≤ 0 which would break occupancy math in templates
    if "max_capacity" in fields and (fields["max_capacity"] is None or fields["max_capacity"] < 1):
        raise HTTPException(status_code=400, detail="max_capacity must be ≥ 1")
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db_conn.execute(f"UPDATE wedding_rooms SET {set_clause} WHERE id=?", (*fields.values(), room_id))
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_rooms WHERE id=?", (room_id,)).fetchone())


@router.delete("/rooms/{room_id}", status_code=204)
async def delete_room(room_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_room_assignments WHERE room_id=?", (room_id,))
    db_conn.execute("DELETE FROM wedding_rooms WHERE id=?", (room_id,))
    db_conn.commit()


@router.post("/rooms/{room_id}/assign/{guest_id}", status_code=201)
async def assign_guest_to_room(room_id: int, guest_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    room = db_conn.execute("SELECT id, max_capacity FROM wedding_rooms WHERE id=?", (room_id,)).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    guest = db_conn.execute(
        "SELECT id, plus_one, children_count, status FROM wedding_guests WHERE id=?", (guest_id,)
    ).fetchone()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    if guest["status"] == "declined":
        raise HTTPException(status_code=400, detail="Cannot assign a declined guest to a room")

    # Compute how many beds this guest occupies and whether the room has room.
    needed = 1 + (1 if guest["plus_one"] else 0) + int(guest["children_count"] or 0)
    # Current occupancy excluding this guest (if already in this room)
    occupancy_row = db_conn.execute(
        """SELECT COALESCE(SUM(1 + CASE WHEN g.plus_one=1 THEN 1 ELSE 0 END + COALESCE(g.children_count,0)), 0)
           FROM wedding_room_assignments ra
           JOIN wedding_guests g ON g.id = ra.guest_id
           WHERE ra.room_id = ? AND ra.guest_id != ? AND g.status != 'declined'""",
        (room_id, guest_id),
    ).fetchone()
    current_occupancy = int(occupancy_row[0] or 0)
    if current_occupancy + needed > int(room["max_capacity"]):
        raise HTTPException(
            status_code=400,
            detail=f"החדר מלא ({current_occupancy}/{room['max_capacity']}). אין מקום לעוד {needed} אנשים.",
        )

    db_conn.execute(
        "INSERT INTO wedding_room_assignments (room_id, guest_id) VALUES (?,?) ON CONFLICT(guest_id) DO UPDATE SET room_id=excluded.room_id",
        (room_id, guest_id),
    )
    db_conn.commit()
    return {"room_id": room_id, "guest_id": guest_id}


@router.delete("/rooms/assignments/{guest_id}", status_code=204)
async def unassign_guest_from_room(guest_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_room_assignments WHERE guest_id=?", (guest_id,))
    db_conn.commit()
