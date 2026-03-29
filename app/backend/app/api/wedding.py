"""
Wedding module API endpoints.
CRUD for vendors, guests, tasks, budget items, and settings.
"""
from __future__ import annotations
import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..db import get_db_conn

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


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
            status, deposit_amount, deposit_paid_date, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (body.name, body.category, body.contact_name, body.phone,
         body.price_quoted, body.what_included, body.status,
         body.deposit_amount, body.deposit_paid_date, body.notes),
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
    db_conn.execute("DELETE FROM wedding_vendors WHERE id=?", (vendor_id,))
    db_conn.commit()


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
