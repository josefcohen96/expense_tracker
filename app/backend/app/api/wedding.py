"""
Wedding module API endpoints.
CRUD for vendors, guests, tasks, budget items, settings, and file attachments.
"""
from __future__ import annotations
import sqlite3
import uuid
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ..db import get_db_conn

router = APIRouter(prefix="/api/wedding", tags=["wedding"])

# Directory for uploaded vendor files: app/uploads/vendor_files/
_UPLOADS_DIR = Path(__file__).resolve().parents[3] / "uploads" / "vendor_files"
_ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}
_ALLOWED_EXT  = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MAX_SIZE_MB  = 15

# Magic bytes for file-type sniffing (defense-in-depth alongside extension check)
_MAGIC_BYTES = {
    "application/pdf": [b"%PDF-"],
    "image/jpeg":      [b"\xff\xd8\xff"],
    "image/png":       [b"\x89PNG\r\n\x1a\n"],
    "image/gif":       [b"GIF87a", b"GIF89a"],
    "image/webp":      [b"RIFF"],  # also has "WEBP" at offset 8
}

def _sniff_mime(content: bytes) -> Optional[str]:
    if not content:
        return None
    for mime, signatures in _MAGIC_BYTES.items():
        for sig in signatures:
            if content.startswith(sig):
                # Extra check for WebP: "WEBP" marker at offset 8
                if mime == "image/webp":
                    if len(content) >= 12 and content[8:12] == b"WEBP":
                        return mime
                else:
                    return mime
    return None


# ─── Schemas ────────────────────────────────────────────────────────────────

class VendorCreate(BaseModel):
    name: str
    category: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    price_quoted: Optional[float] = None
    what_included: Optional[str] = None
    status: str = "not_contacted"
    deposit_amount: Optional[float] = None
    deposit_paid_date: Optional[str] = None
    notes: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    location: Optional[str] = None
    inclusions: Optional[str] = None

class VendorUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    price_quoted: Optional[float] = None
    what_included: Optional[str] = None
    status: Optional[str] = None
    deposit_amount: Optional[float] = None
    deposit_paid_date: Optional[str] = None
    notes: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    location: Optional[str] = None
    inclusions: Optional[str] = None

class GuestCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    group_name: Optional[str] = None
    status: str = "pending"
    plus_one: int = 0
    plus_one_name: Optional[str] = None
    children_count: int = 0
    needs_transport: int = 0
    staying_overnight: int = 0
    table_number: Optional[int] = None
    notes: Optional[str] = None
    meal_type: str = "regular"
    food_notes: Optional[str] = None
    plus_one_meal_type: str = "regular"

class GuestUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = None
    plus_one: Optional[int] = None
    plus_one_name: Optional[str] = None
    children_count: Optional[int] = None
    needs_transport: Optional[int] = None
    staying_overnight: Optional[int] = None
    table_number: Optional[int] = None
    notes: Optional[str] = None
    meal_type: Optional[str] = None
    food_notes: Optional[str] = None
    plus_one_meal_type: Optional[str] = None

class RoomCreate(BaseModel):
    name: str
    room_type: str = "יחידים"
    max_capacity: int = 2
    notes: Optional[str] = None

class RoomUpdate(BaseModel):
    name: Optional[str] = None
    room_type: Optional[str] = None
    max_capacity: Optional[int] = None
    notes: Optional[str] = None

class TaskCreate(BaseModel):
    title: str
    category: str = "general"
    due_date: Optional[str] = None
    priority: str = "medium"
    notes: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    completed: Optional[int] = None
    priority: Optional[str] = None
    notes: Optional[str] = None

class BudgetItemCreate(BaseModel):
    name: str
    category: str = "other"
    budgeted_amount: float = 0
    actual_amount: float = 0
    notes: Optional[str] = None

class BudgetItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    budgeted_amount: Optional[float] = None
    actual_amount: Optional[float] = None
    notes: Optional[str] = None

class SettingUpsert(BaseModel):
    key: str
    value: str

class QuoteItem(BaseModel):
    id: Optional[int] = None
    description: str
    quantity: float = 1
    unit_price: float = 0
    apply_vat: int = 1
    sort_order: int = 0

class TimelineEventCreate(BaseModel):
    day: str
    title: str
    description: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    category: str = "general"

class TimelineEventUpdate(BaseModel):
    day: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    category: Optional[str] = None


# ─── Vendors ────────────────────────────────────────────────────────────────

@router.get("/vendors")
async def list_vendors(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute("SELECT * FROM wedding_vendors ORDER BY category, name").fetchall()
    return [dict(r) for r in rows]


@router.post("/vendors", status_code=201)
async def create_vendor(body: VendorCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    cur = db_conn.execute(
        """INSERT INTO wedding_vendors
           (name, category, contact_name, phone, price_quoted, what_included,
            status, deposit_amount, deposit_paid_date, notes,
            instagram_url, facebook_url, location, inclusions)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (body.name, body.category, body.contact_name, body.phone,
         body.price_quoted, body.what_included, body.status,
         body.deposit_amount, body.deposit_paid_date, body.notes,
         body.instagram_url, body.facebook_url, body.location, body.inclusions),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM wedding_vendors WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.put("/vendors/{vendor_id}")
async def update_vendor(vendor_id: int, body: VendorUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_vendors WHERE id=?", (vendor_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return dict(existing)
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db_conn.execute(
        f"UPDATE wedding_vendors SET {set_clause} WHERE id=?",
        (*fields.values(), vendor_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_vendors WHERE id=?", (vendor_id,)).fetchone())


@router.delete("/vendors/{vendor_id}", status_code=204)
async def delete_vendor(vendor_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM vendor_quote_items WHERE vendor_id=?", (vendor_id,))
    db_conn.execute("DELETE FROM wedding_vendors WHERE id=?", (vendor_id,))
    db_conn.commit()


# ─── Quote Items ─────────────────────────────────────────────────────────────

VAT_RATE = 0.17

def _recalculate_price_quoted(vendor_id: int, db_conn: sqlite3.Connection) -> float:
    rows = db_conn.execute(
        "SELECT quantity, unit_price, apply_vat FROM vendor_quote_items WHERE vendor_id=?",
        (vendor_id,)
    ).fetchall()
    if not rows:
        # Clear the vendor's price_quoted when all line items are removed
        db_conn.execute("UPDATE wedding_vendors SET price_quoted=0 WHERE id=?", (vendor_id,))
        return 0.0
    pre_vat = sum(r["quantity"] * r["unit_price"] for r in rows)
    vat = sum(r["quantity"] * r["unit_price"] for r in rows if r["apply_vat"]) * VAT_RATE
    total = round(pre_vat + vat, 2)
    db_conn.execute("UPDATE wedding_vendors SET price_quoted=? WHERE id=?", (total, vendor_id))
    return total


@router.get("/vendors/{vendor_id}/quote-items")
async def get_quote_items(vendor_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM vendor_quote_items WHERE vendor_id=? ORDER BY sort_order, id",
        (vendor_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.put("/vendors/{vendor_id}/quote-items")
async def replace_quote_items(
    vendor_id: int,
    items: list[QuoteItem],
    db_conn: sqlite3.Connection = Depends(get_db_conn)
):
    if not db_conn.execute("SELECT 1 FROM wedding_vendors WHERE id=?", (vendor_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Vendor not found")
    db_conn.execute("DELETE FROM vendor_quote_items WHERE vendor_id=?", (vendor_id,))
    for i, item in enumerate(items):
        # Normalize apply_vat to strict 0/1 to prevent unexpected truthy values
        apply_vat = 1 if item.apply_vat else 0
        # Sanitize numeric fields against negatives
        qty = max(0.0, float(item.quantity or 0))
        price = max(0.0, float(item.unit_price or 0))
        db_conn.execute(
            """INSERT INTO vendor_quote_items
               (vendor_id, description, quantity, unit_price, apply_vat, sort_order)
               VALUES (?,?,?,?,?,?)""",
            (vendor_id, item.description, qty, price, apply_vat, i),
        )
    total = _recalculate_price_quoted(vendor_id, db_conn)
    db_conn.commit()
    rows = db_conn.execute(
        "SELECT * FROM vendor_quote_items WHERE vendor_id=? ORDER BY sort_order, id",
        (vendor_id,)
    ).fetchall()
    return {"items": [dict(r) for r in rows], "total": total}


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


# ─── Tasks ──────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM wedding_tasks ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date ASC"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/tasks", status_code=201)
async def create_task(body: TaskCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    cur = db_conn.execute(
        "INSERT INTO wedding_tasks (title, category, due_date, priority, notes) VALUES (?,?,?,?,?)",
        (body.title, body.category, body.due_date, body.priority, body.notes),
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


# ─── Budget Items ────────────────────────────────────────────────────────────

@router.get("/budget-items")
async def list_budget_items(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute("SELECT * FROM wedding_budget_items ORDER BY category, name").fetchall()
    return [dict(r) for r in rows]


@router.post("/budget-items", status_code=201)
async def create_budget_item(body: BudgetItemCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    cur = db_conn.execute(
        "INSERT INTO wedding_budget_items (name, category, budgeted_amount, actual_amount, notes) VALUES (?,?,?,?,?)",
        (body.name, body.category, body.budgeted_amount, body.actual_amount, body.notes),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_budget_items WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/budget-items/{item_id}")
async def update_budget_item(item_id: int, body: BudgetItemUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_budget_items WHERE id=?", (item_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Budget item not found")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return dict(existing)
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db_conn.execute(
        f"UPDATE wedding_budget_items SET {set_clause} WHERE id=?",
        (*updates.values(), item_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_budget_items WHERE id=?", (item_id,)).fetchone())


@router.delete("/budget-items/{item_id}", status_code=204)
async def delete_budget_item(item_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_budget_items WHERE id=?", (item_id,))
    db_conn.commit()


# ─── Settings ────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute("SELECT key, value FROM wedding_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


@router.post("/settings")
async def upsert_setting(body: SettingUpsert, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute(
        "INSERT INTO wedding_settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
        (body.key, body.value),
    )
    db_conn.commit()
    return {"key": body.key, "value": body.value}


# ─── Vendor File Attachments ─────────────────────────────────────────────────

@router.get("/vendors/{vendor_id}/files")
async def list_vendor_files(vendor_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute(
        "SELECT * FROM vendor_files WHERE vendor_id=? ORDER BY uploaded_at DESC",
        (vendor_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/vendors/{vendor_id}/files", status_code=201)
async def upload_vendor_file(
    vendor_id: int,
    file: UploadFile = File(...),
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    if not db_conn.execute("SELECT 1 FROM wedding_vendors WHERE id=?", (vendor_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Validate extension
    orig_name = file.filename or "file"
    ext = Path(orig_name).suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="סוג קובץ לא נתמך. מותר: PDF, JPG, PNG, GIF, WEBP")

    # Read content and check size
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="הקובץ ריק")
    size_mb = len(content) / (1024 * 1024)
    if size_mb > _MAX_SIZE_MB:
        raise HTTPException(status_code=400, detail=f"הקובץ גדול מדי (מקסימום {_MAX_SIZE_MB}MB)")

    # Determine mime type from extension
    mime_map = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    declared_mime = mime_map.get(ext, "application/octet-stream")

    # Verify magic bytes match the declared extension — defense against renamed payloads
    detected_mime = _sniff_mime(content)
    if detected_mime is None or detected_mime != declared_mime:
        raise HTTPException(
            status_code=400,
            detail="תוכן הקובץ אינו תואם לסיומת. ודא שהקובץ הוא PDF/תמונה אמיתי.",
        )

    # Store file under a UUID name so original_name can't influence the path
    stored_name = f"{uuid.uuid4().hex}{ext}"
    vendor_dir = _UPLOADS_DIR / str(vendor_id)
    vendor_dir.mkdir(parents=True, exist_ok=True)
    (vendor_dir / stored_name).write_bytes(content)

    # Save metadata (truncate display name to avoid pathological lengths)
    safe_orig = orig_name[:255]
    cur = db_conn.execute(
        "INSERT INTO vendor_files (vendor_id, original_name, stored_name, file_size, mime_type) VALUES (?,?,?,?,?)",
        (vendor_id, safe_orig, stored_name, len(content), declared_mime),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM vendor_files WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.get("/files/{file_id}")
async def get_vendor_file(file_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    row = db_conn.execute("SELECT * FROM vendor_files WHERE id=?", (file_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = (_UPLOADS_DIR / str(row["vendor_id"]) / row["stored_name"]).resolve()
    # Guard against path-traversal: stored_name should be UUID-only, but verify.
    try:
        file_path.relative_to(_UPLOADS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    # Use inline disposition so the browser (including iOS Safari) renders the file
    # instead of prompting a download. All allowed types (PDF, images) display natively.
    mime = row["mime_type"]
    encoded_name = quote(row["original_name"], safe="")
    disposition = f"inline; filename=\"{row['original_name']}\"; filename*=UTF-8''{encoded_name}"
    return FileResponse(
        path=str(file_path),
        media_type=mime,
        headers={"Content-Disposition": disposition},
    )


@router.delete("/files/{file_id}", status_code=204)
async def delete_vendor_file(file_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    row = db_conn.execute("SELECT * FROM vendor_files WHERE id=?", (file_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = _UPLOADS_DIR / str(row["vendor_id"]) / row["stored_name"]
    if file_path.exists():
        file_path.unlink()
    db_conn.execute("DELETE FROM vendor_files WHERE id=?", (file_id,))
    db_conn.commit()


# ─── Notes ────────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    content: Optional[str] = None
    color: str = "white"
    pinned: int = 0

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    color: Optional[str] = None
    pinned: Optional[int] = None


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


# ─── Ideas ────────────────────────────────────────────────────────────────────

class IdeaCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "כללי"
    status: str = "new"
    color: str = "white"

class IdeaUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None


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


# ─── Seating Chart ────────────────────────────────────────────────────────────

class SeatingTableCreate(BaseModel):
    name: str
    shape: str = "round"
    capacity: int = 8
    x: float = 100
    y: float = 100
    color: str = "rose"
    notes: Optional[str] = None

class SeatingTableUpdate(BaseModel):
    name: Optional[str] = None
    shape: Optional[str] = None
    capacity: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    color: Optional[str] = None
    notes: Optional[str] = None

class SeatingTablePositions(BaseModel):
    tables: list  # [{id, x, y}]

class SeatingAssign(BaseModel):
    table_id: int
    seat_number: int
    guest_id: int
    extra_seats: list[int] = []


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
        if si < 0 or si >= capacity:
            raise HTTPException(status_code=400, detail=f"Seat number {si} is outside table capacity (0-{capacity - 1})")
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


# ─── Invite Tokens ───────────────────────────────────────────────────────────

# Default base URL used when no request context is available. Can be overridden by
# the PUBLIC_BASE_URL environment variable for staging/custom domains.
DEFAULT_BASE_URL = "https://expensetracker-production-2084.up.railway.app"


def _resolve_base_url(request: Optional[Request]) -> str:
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
