from typing import List, Optional, Any
import sqlite3
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from .. import schemas
from ..db import get_db_conn
from ..services.cache_service import cache_service
from openpyxl import Workbook

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
    if category_id is not None:
        query += " AND category_id = ?"
        params.append(category_id)
    if user_id is not None:
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
    """Delete a transaction. If it's a recurring instance, mark the period as skipped and delete it."""
    # Check if this is a recurring instance; if so, record a skip
    row = db_conn.execute(
        "SELECT recurrence_id, period_key FROM transactions WHERE id = ?",
        (tx_id,),
    ).fetchone()
    if row and row["recurrence_id"] and row["period_key"]:
        db_conn.execute(
            "INSERT OR IGNORE INTO recurrence_skips (recurrence_id, period_key) VALUES (?, ?)",
            (row["recurrence_id"], row["period_key"]),
        )
        db_conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    else:
        db_conn.execute("DELETE FROM transactions WHERE id = ? AND recurrence_id IS NULL", (tx_id,))
    db_conn.commit()
    
    # Clear cache when transaction is deleted
    cache_service.invalidate("top_expenses_3months")
    
    return JSONResponse(content={"deleted": True})

@router.post("/{tx_id}/duplicate")
async def api_duplicate_transaction(
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Duplicate a transaction by id and return the new id."""
    row = db_conn.execute(
        "SELECT date, amount, category_id, user_id, account_id, notes, tags "
        "FROM transactions WHERE id = ? AND recurrence_id IS NULL",
        (tx_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    cur = db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            row["date"],
            row["amount"],
            row["category_id"],
            row["user_id"],
            row["account_id"],
            row["notes"],
            row["tags"],
        ),
    )
    db_conn.commit()
    new_id = cur.lastrowid
    cache_service.invalidate("top_expenses_3months")
    return JSONResponse(content={"duplicated": True, "id": new_id})

@router.get("/export")
async def api_export_transactions(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category_id: Optional[int] = None,
    user_id: Optional[int] = None,
    account_id: Optional[int] = None,
    amount_min: Optional[float] = None,
    amount_max: Optional[float] = None,
    tags: Optional[str] = None,
    sort: Optional[str] = "date_desc",
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    """Export filtered transactions to an Excel file (xlsx)."""
    where_clause = "WHERE t.recurrence_id IS NULL"
    params: List[Any] = []

    # Removed transaction_type filter: export now includes all transactions unless filtered by other params

    if category_id:
        where_clause += " AND t.category_id = ?"
        params.append(category_id)
    if user_id:
        where_clause += " AND t.user_id = ?"
        params.append(user_id)
    if account_id:
        where_clause += " AND t.account_id = ?"
        params.append(account_id)
    if from_date:
        where_clause += " AND t.date >= ?"
        params.append(from_date)
    if to_date:
        where_clause += " AND t.date <= ?"
        params.append(to_date)
    if amount_min is not None:
        where_clause += " AND ABS(t.amount) >= ?"
        params.append(abs(amount_min))
    if amount_max is not None:
        where_clause += " AND ABS(t.amount) <= ?"
        params.append(abs(amount_max))
    if tags and tags.strip():
        tag_list = [tg.strip() for tg in tags.split(',') if tg.strip()]
        if tag_list:
            where_clause += " AND (" + " OR ".join(["t.tags LIKE ?"] * len(tag_list)) + ")"
            params.extend([f"%{tg}%" for tg in tag_list])

    order_clause = "ORDER BY "
    if sort == "date_asc":
        order_clause += "t.date ASC, t.id ASC"
    elif sort == "amount_desc":
        order_clause += "ABS(t.amount) DESC, t.date DESC"
    elif sort == "amount_asc":
        order_clause += "ABS(t.amount) ASC, t.date DESC"
    else:
        order_clause += "t.date DESC, t.id DESC"

    query = f"""
        SELECT t.id, t.date, t.amount, c.name as category, u.name as user, 
               a.name as account, t.notes, t.tags
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        {where_clause}
        {order_clause}
    """
    rows = db_conn.execute(query, params).fetchall()

    # Build workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    headers = [
        "ID", "Date", "Amount", "Category", "User", "Account", "Notes", "Tags"
    ]
    ws.append(headers)
    for r in rows:
        ws.append([
            r["id"],
            r["date"],
            float(r["amount"] or 0),
            r["category"],
            r["user"],
            r["account"],
            r["notes"],
            r["tags"],
        ])

    # Stream response
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    filename = "transactions_export.xlsx"
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )
