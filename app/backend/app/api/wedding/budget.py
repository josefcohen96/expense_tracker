from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    BudgetItemCreate,
    BudgetItemUpdate,
)

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


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
