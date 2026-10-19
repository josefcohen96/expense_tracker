from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    SeatingAssign,
    SeatingTableCreate,
    SeatingTablePositions,
    SeatingTableUpdate,
)

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Seating Chart ────────────────────────────────────────────────────────────

@router.get("/seating")
async def get_seating(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    tables = [dict(r) for r in db_conn.execute(
        "SELECT * FROM wedding_seating_tables ORDER BY created_at"
    ).fetchall()]
    assignments = [dict(r) for r in db_conn.execute(
        """SELECT a.*, g.name as guest_name, g.group_name, g.status as guest_status
           FROM wedding_seating_assignments a
           JOIN wedding_guests g ON g.id = a.guest_id"""
    ).fetchall()]
    unassigned = [dict(r) for r in db_conn.execute(
        """SELECT g.id, g.name, g.group_name, g.status, g.plus_one, g.plus_one_name, g.children_count
           FROM wedding_guests g
           WHERE g.id NOT IN (SELECT guest_id FROM wedding_seating_assignments)
           AND g.status != 'declined'
           ORDER BY g.group_name, g.name"""
    ).fetchall()]
    # attach assignments to tables
    assign_map: dict = {}
    for a in assignments:
        tid = a["table_id"]
        assign_map.setdefault(tid, {})[a["seat_number"]] = a
    for t in tables:
        t["assignments"] = assign_map.get(t["id"], {})
    return {"tables": tables, "unassigned": unassigned}


@router.post("/seating/tables", status_code=201)
async def create_seating_table(body: SeatingTableCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    cur = db_conn.execute(
        "INSERT INTO wedding_seating_tables (name, shape, capacity, x, y, color, notes) VALUES (?,?,?,?,?,?,?)",
        (body.name, body.shape, body.capacity, body.x, body.y, body.color, body.notes),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_seating_tables WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/seating/tables/{table_id}")
async def update_seating_table(table_id: int, body: SeatingTableUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_seating_tables WHERE id=?", (table_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Table not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return dict(existing)
    # Validate capacity ≥ 1 to prevent broken occupancy math
    if "capacity" in fields and (fields["capacity"] is None or fields["capacity"] < 1):
        raise HTTPException(status_code=400, detail="capacity must be ≥ 1")
    # If capacity is reduced, drop any out-of-range seat assignments
    if "capacity" in fields and fields["capacity"] is not None and fields["capacity"] < existing["capacity"]:
        db_conn.execute(
            "DELETE FROM wedding_seating_assignments WHERE table_id=? AND seat_number>?",
            (table_id, fields["capacity"]),
        )
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db_conn.execute(f"UPDATE wedding_seating_tables SET {set_clause} WHERE id=?", (*fields.values(), table_id))
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_seating_tables WHERE id=?", (table_id,)).fetchone())


@router.post("/seating/tables/positions")
async def update_table_positions(body: SeatingTablePositions, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    for item in body.tables:
        try:
            tid = int(item["id"])
            x = float(item["x"])
            y = float(item["y"])
        except (KeyError, TypeError, ValueError):
            continue
        db_conn.execute(
            "UPDATE wedding_seating_tables SET x=?, y=? WHERE id=?",
            (x, y, tid),
        )
    db_conn.commit()
    return {"ok": True}


@router.delete("/seating/tables/{table_id}", status_code=204)
async def delete_seating_table(table_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_seating_assignments WHERE table_id=?", (table_id,))
    db_conn.execute("DELETE FROM wedding_seating_tables WHERE id=?", (table_id,))
    db_conn.commit()


@router.post("/seating/assign", status_code=201)
async def assign_guest(body: SeatingAssign, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    # Validate table exists and grab its capacity
    table = db_conn.execute(
        "SELECT id, capacity FROM wedding_seating_tables WHERE id=?", (body.table_id,)
    ).fetchone()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    if not db_conn.execute("SELECT 1 FROM wedding_guests WHERE id=?", (body.guest_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Guest not found")

    # Dedupe + validate seat numbers fall within 1..capacity
    capacity = int(table["capacity"])
    seen = set()
    all_seats: list[int] = []
    for s in [body.seat_number] + list(body.extra_seats or []):
        try:
            si = int(s)
        except (TypeError, ValueError):
            continue
        if si < 1 or si > capacity:
            raise HTTPException(status_code=400, detail=f"Seat number {si} is outside table capacity (1-{capacity})")
        if si in seen:
            continue
        seen.add(si)
        all_seats.append(si)
    if not all_seats:
        raise HTTPException(status_code=400, detail="No valid seats provided")

    try:
        # Treat as single transaction so partial failure doesn't leave inconsistent state
        # Remove any prior assignments for this guest
        db_conn.execute("DELETE FROM wedding_seating_assignments WHERE guest_id=?", (body.guest_id,))
        # Free target seats (may belong to other guests)
        placeholders = ",".join("?" * len(all_seats))
        db_conn.execute(
            f"DELETE FROM wedding_seating_assignments WHERE table_id=? AND seat_number IN ({placeholders})",
            (body.table_id, *all_seats),
        )
        # Insert one row per seat
        for seat in all_seats:
            db_conn.execute(
                "INSERT INTO wedding_seating_assignments (table_id, seat_number, guest_id) VALUES (?,?,?)",
                (body.table_id, seat, body.guest_id),
            )
        db_conn.commit()
    except Exception:
        db_conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to assign seats")
    return {"ok": True, "seats": all_seats}


@router.delete("/seating/assign/{guest_id}", status_code=204)
async def unassign_guest(guest_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_seating_assignments WHERE guest_id=?", (guest_id,))
    db_conn.commit()
