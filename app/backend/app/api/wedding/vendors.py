from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    QuoteItem,
    VendorCreate,
    VendorUpdate,
)

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


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
            instagram_url, facebook_url, location, inclusions, portions_ordered)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (body.name, body.category, body.contact_name, body.phone,
         body.price_quoted, body.what_included, body.status,
         body.deposit_amount, body.deposit_paid_date, body.notes,
         body.instagram_url, body.facebook_url, body.location, body.inclusions,
         body.portions_ordered),
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
