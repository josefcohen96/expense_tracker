from typing import List, Optional, Any
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from .. import schemas
from ..db import get_db_conn
from ..services.cache_service import cache_service

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

@router.get("", response_model=List[schemas.Transaction])
async def api_get_transactions(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category_id: Optional[int] = None,
    user_id: Optional[int] = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> List[schemas.Transaction]:
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
    cur = db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tr.date,
            tr.amount,
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
    
    # Note: Challenge evaluation is now handled by CRON job
    
    return schemas.Transaction(id=new_id, **tr.dict())

@router.put("/{tx_id}", response_model=schemas.Transaction)
async def api_update_transaction(
    tx_id: int,
    update: schemas.TransactionUpdate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Transaction:
    fields = update.dict(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
    params = list(fields.values()) + [tx_id]
    db_conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ? AND recurrence_id IS NULL", params)
    db_conn.commit()
    
    # Clear cache when transaction is updated
    cache_service.invalidate("top_expenses_3months")
    
    # Note: Challenge evaluation is now handled by CRON job
    
    row = db_conn.execute("SELECT * FROM transactions WHERE id = ? AND recurrence_id IS NULL", (tx_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return schemas.Transaction(**dict(row))

@router.delete("/{tx_id}")
async def api_delete_transaction(
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    db_conn.execute("DELETE FROM transactions WHERE id = ? AND recurrence_id IS NULL", (tx_id,))
    db_conn.commit()
    
    # Clear cache when transaction is deleted
    cache_service.invalidate("top_expenses_3months")
    
    # Note: Challenge evaluation is now handled by CRON job
    
    return JSONResponse(content={"deleted": True})
