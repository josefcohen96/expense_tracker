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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ..db import get_db_conn

router = APIRouter(prefix="/api/wedding", tags=["wedding"])

# Directory for uploaded vendor files: app/uploads/vendor_files/
_UPLOADS_DIR = Path(__file__).resolve().parents[3] / "uploads" / "vendor_files"
_ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}
_ALLOWED_EXT  = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp"}
_MAX_SIZE_MB  = 15


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

class GuestCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    group_name: Optional[str] = None
    status: str = "pending"
    plus_one: int = 0
    plus_one_name: Optional[str] = None
    children_count: int = 0
    needs_transport: int = 0
    table_number: Optional[int] = None
    notes: Optional[str] = None

class GuestUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = None
    plus_one: Optional[int] = None
    plus_one_name: Optional[str] = None
    children_count: Optional[int] = None
    needs_transport: Optional[int] = None
    table_number: Optional[int] = None
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
            instagram_url, facebook_url, location)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (body.name, body.category, body.contact_name, body.phone,
         body.price_quoted, body.what_included, body.status,
         body.deposit_amount, body.deposit_paid_date, body.notes,
         body.instagram_url, body.facebook_url, body.location),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM wedding_vendors WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.put("/vendors/{vendor_id}")
async def update_vendor(vendor_id: int, body: VendorUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_vendors WHERE id=?", (vendor_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
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
        db_conn.execute(
            """INSERT INTO vendor_quote_items
               (vendor_id, description, quantity, unit_price, apply_vat, sort_order)
               VALUES (?,?,?,?,?,?)""",
            (vendor_id, item.description, item.quantity, item.unit_price, item.apply_vat, i),
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
           (name, phone, group_name, status, plus_one, plus_one_name, children_count, needs_transport, table_number, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (body.name, body.phone, body.group_name, body.status,
         body.plus_one, body.plus_one_name, body.children_count,
         body.needs_transport, body.table_number, body.notes),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_guests WHERE id=?", (cur.lastrowid,)).fetchone())


@router.put("/guests/{guest_id}")
async def update_guest(guest_id: int, body: GuestUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_guests WHERE id=?", (guest_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Guest not found")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        return dict(existing)
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db_conn.execute(
        f"UPDATE wedding_guests SET {set_clause} WHERE id=?",
        (*fields.values(), guest_id),
    )
    db_conn.commit()
    return dict(db_conn.execute("SELECT * FROM wedding_guests WHERE id=?", (guest_id,)).fetchone())


@router.delete("/guests/{guest_id}", status_code=204)
async def delete_guest(guest_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_guests WHERE id=?", (guest_id,))
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
    updates = body.model_dump(exclude_none=True)
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
    updates = body.model_dump(exclude_none=True)
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
        raise HTTPException(status_code=400, detail=f"סוג קובץ לא נתמך. מותר: PDF, JPG, PNG, GIF")

    # Read content and check size
    content = await file.read()
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
    mime_type = mime_map.get(ext, "application/octet-stream")

    # Store file
    stored_name = f"{uuid.uuid4().hex}{ext}"
    vendor_dir = _UPLOADS_DIR / str(vendor_id)
    vendor_dir.mkdir(parents=True, exist_ok=True)
    (vendor_dir / stored_name).write_bytes(content)

    # Save metadata
    cur = db_conn.execute(
        "INSERT INTO vendor_files (vendor_id, original_name, stored_name, file_size, mime_type) VALUES (?,?,?,?,?)",
        (vendor_id, orig_name, stored_name, len(content), mime_type),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM vendor_files WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.get("/files/{file_id}")
async def get_vendor_file(file_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    row = db_conn.execute("SELECT * FROM vendor_files WHERE id=?", (file_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = _UPLOADS_DIR / str(row["vendor_id"]) / row["stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path=str(file_path),
        media_type=row["mime_type"],
        filename=row["original_name"],
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
