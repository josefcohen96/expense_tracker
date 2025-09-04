from typing import List, Optional, Any
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from .. import schemas
from ..db import get_db_conn
from ..services.cache_service import cache_service

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _is_income_category(db_conn: sqlite3.Connection, category_id: Optional[int]) -> bool:
    """Return True if the category id corresponds to an income category."""
    if category_id is None:
        return False
    row = db_conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not row:
        return False
    name = row[0]
    return name in ("משכורת", "קליניקה")

@router.get("", response_model=List[schemas.Transaction])
async def api_get_transactions(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category_id: Optional[int] = None,
    user_id: Optional[int] = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> List[schemas.Transaction]:
    """Get transactions with optional filtering."""
    query = "SELECT * FROM transactions WHERE recurrence_id IS NULL"
    params: List[Any] = []
    
    if from_date:
        query += " AND date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND date <= ?"
        params.append(to_date)
    if category_id:
        query += " AND category_id = ?"
        params.append(category_id)
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    
    query += " ORDER BY date DESC, id DESC"
    rows = db_conn.execute(query, params).fetchall()
    return [schemas.Transaction(**dict(row)) for row in rows]

@router.post("", response_model=schemas.Transaction)
async def api_create_transaction(
    tr: schemas.TransactionCreate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Transaction:
    """Create a new transaction (expense)."""
    # Determine sign by category (income categories stay positive)
    is_income = _is_income_category(db_conn, tr.category_id)
    amount = abs(tr.amount) if is_income else -abs(tr.amount)
    
    cur = db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tr.date,
            amount,
            tr.category_id,
            tr.user_id,
            tr.account_id,
            tr.notes,
            tr.tags,
            tr.recurrence_id,
            tr.period_key,
        ),
    )
    db_conn.commit()
    new_id = cur.lastrowid
    
    # Clear cache when new transaction is added
    cache_service.invalidate("top_expenses_3months")
    
    # Return with the negative amount
    tr_dict = tr.dict()
    tr_dict['amount'] = amount
    return schemas.Transaction(id=new_id, **tr_dict)

@router.put("/{tx_id}", response_model=schemas.Transaction)
async def api_update_transaction(
    tx_id: int,
    update: schemas.TransactionUpdate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Transaction:
    """Update an existing transaction."""
    fields = update.dict(exclude_unset=True)
    
    # If amount is being updated, preserve sign according to (new or existing) category
    if 'amount' in fields:
        # Determine the effective category for sign
        effective_category_id: Optional[int]
        if 'category_id' in fields and fields['category_id'] is not None:
            effective_category_id = fields['category_id']
        else:
            row = db_conn.execute("SELECT category_id FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            effective_category_id = row[0] if row else None
        is_income = _is_income_category(db_conn, effective_category_id)
        fields['amount'] = abs(fields['amount']) if is_income else -abs(fields['amount'])
    
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
    params = list(fields.values()) + [tx_id]
    db_conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ? AND recurrence_id IS NULL", params)
    db_conn.commit()
    
    # Clear cache when transaction is updated
    cache_service.invalidate("top_expenses_3months")
    
    row = db_conn.execute("SELECT * FROM transactions WHERE id = ? AND recurrence_id IS NULL", (tx_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return schemas.Transaction(**dict(row))

@router.delete("/{tx_id}")
async def api_delete_transaction(
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Delete a transaction."""
    db_conn.execute("DELETE FROM transactions WHERE id = ? AND recurrence_id IS NULL", (tx_id,))
    db_conn.commit()
    
    # Clear cache when transaction is deleted
    cache_service.invalidate("top_expenses_3months")
    
    return JSONResponse(content={"deleted": True})
