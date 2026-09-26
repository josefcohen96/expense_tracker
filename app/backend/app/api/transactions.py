from typing import List, Optional, Any
import hmac
import os
import sqlite3
from datetime import date as _date
from io import BytesIO
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from .. import schemas
from ..auth import public
from ..db import get_db_conn
from ..services import card_statement
from ..services.cache_service import cache_service
from openpyxl import Workbook

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# Single source of truth for income category names (Hebrew).
# Statistics queries and the transactions API both use this to identify income vs expense.
INCOME_CATEGORIES: tuple[str, ...] = ("משכורת", "קליניקה")

# Keep this import lazy to avoid circular imports — statistics imports INCOME_CATEGORIES from here.
def _invalidate_stats_cache() -> None:
    cache_service.invalidate("top_expenses_3months")
    cache_service.invalidate("statistics_full")


def _is_income_category(db_conn: sqlite3.Connection, category_id: Optional[int]) -> bool:
    """Return True if the category id corresponds to an income category."""
    if category_id is None:
        return False
    row = db_conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not row:
        return False
    return row[0] in INCOME_CATEGORIES

def _is_saving_category(db_conn: sqlite3.Connection, category_id: Optional[int]) -> bool:
    """Return True if the category is marked as a savings category."""
    if category_id is None:
        return False
    row = db_conn.execute("SELECT is_saving FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not row:
        return False
    return bool(row[0])

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

# ─── Card statement import (Max xlsx) ───────────────────────────────────────

_NOT_A_MAX_STATEMENT = "הקובץ לא נראה כמו דוח של max"
_CREDIT_CARD_ACCOUNT = "כרטיס אשראי"
_AUTO_IMPORT_OFF = "ייבוא אוטומטי כבוי"
_BAD_IMPORT_TOKEN = "אסימון לא תקין"


def _insert_import_rows(
    db_conn: sqlite3.Connection,
    user_id: Optional[int],
    account_id: Optional[int],
    rows: List[tuple],
) -> List[int]:
    """Insert statement rows as ordinary transactions and drop the stats cache.

    rows: (iso date, statement charge, category_id, merchant) — a charge becomes a
    negative amount, a refund a positive one. Shared by the page import and the
    mailbox import so the two paths cannot drift.
    """
    created: List[int] = []
    for iso, amount, category_id, merchant in rows:
        cur = db_conn.execute(
            "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (
                iso,
                -round(amount, 2),
                category_id,
                user_id,
                account_id,
                card_statement.normalise_merchant(merchant) or None,
            ),
        )
        created.append(cur.lastrowid)
    db_conn.commit()
    _invalidate_stats_cache()
    return created


def _import_categories(db_conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """The categories an imported charge may take: everything but income (as the transactions page)."""
    placeholders = ",".join("?" * len(INCOME_CATEGORIES))
    return db_conn.execute(
        f"SELECT id, name, is_saving FROM categories WHERE TRIM(name) NOT IN ({placeholders}) ORDER BY name",
        INCOME_CATEGORIES,
    ).fetchall()


@router.post("/import/preview")
async def api_import_preview(
    request: Request,
    file: UploadFile = File(...),
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Parse a Max statement and say, per row, whether the app already has it."""
    content = await file.read()
    try:
        parsed = card_statement.parse_statement(content)
    except ValueError:
        raise HTTPException(status_code=400, detail=_NOT_A_MAX_STATEMENT)

    categories = _import_categories(db_conn)
    rows = card_statement.classify(db_conn, parsed["rows"])
    counts = {"new": 0, "exists": 0, "recurring": 0}
    out_rows = []
    for index, row in enumerate(rows):
        category_id, source = card_statement.guess_category(
            db_conn, row["merchant"], row["max_category"], categories
        )
        counts[row["status"]] += 1
        out_rows.append({
            "index": index,
            "date": row["date"],
            "merchant": row["merchant"],
            "amount": row["amount"],
            "max_category": row["max_category"],
            "sheet": row["sheet"],
            "status": row["status"],
            "matched_id": row["matched_id"],
            "category_id": category_id,
            "category_source": source,
        })

    session_user = getattr(request.state, "user", None) or request.session.get("user")
    account = db_conn.execute(
        "SELECT id FROM accounts WHERE name = ?", (_CREDIT_CARD_ACCOUNT,)
    ).fetchone()
    return JSONResponse(content={
        "holder": parsed["holder"],
        "statement_month": parsed["statement_month"],
        "card_last4": parsed["card_last4"],
        "user_id": card_statement.guess_payer(db_conn, parsed["holder"], session_user),
        "account_id": account["id"] if account else None,
        "rows": out_rows,
        "counts": counts,
    })


@router.post("/import")
async def api_import_transactions(
    body: schemas.ImportRequest,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Add the kept statement rows as ordinary transactions (charge → negative amount)."""
    if not body.rows:
        raise HTTPException(status_code=400, detail="אין עסקאות להוספה")
    if not db_conn.execute("SELECT 1 FROM users WHERE id = ?", (body.user_id,)).fetchone():
        raise HTTPException(status_code=400, detail="משתמש לא קיים")
    if body.account_id is not None and not db_conn.execute(
        "SELECT 1 FROM accounts WHERE id = ?", (body.account_id,)
    ).fetchone():
        raise HTTPException(status_code=400, detail="חשבון לא קיים")
    category_ids = {r.category_id for r in body.rows}
    placeholders = ",".join("?" * len(category_ids))
    known = {
        r[0] for r in db_conn.execute(
            f"SELECT id FROM categories WHERE id IN ({placeholders})", tuple(category_ids)
        ).fetchall()
    }
    if category_ids - known:
        raise HTTPException(status_code=400, detail="קטגוריה לא קיימת")
    dates = []
    for r in body.rows:
        try:
            dates.append(_date.fromisoformat(r.date).isoformat())
        except ValueError:
            raise HTTPException(status_code=400, detail="תאריך לא תקין")

    created = _insert_import_rows(
        db_conn,
        body.user_id,
        body.account_id,
        [(iso, r.amount, r.category_id, r.merchant) for r, iso in zip(body.rows, dates)],
    )
    return JSONResponse(content={
        "created": created,
        "count": len(created),
        "date_from": min(dates),
        "date_to": max(dates),
    })


@router.post("/import/auto")
@public
async def api_import_auto(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Mailbox import (Google Apps Script): add only the statement's new rows, no session.

    Guarded by the IMPORT_TOKEN bearer token instead of a login. The token is checked
    before the upload is read, so an unauthorised caller never gets the file parsed.
    """
    expected = os.environ.get("IMPORT_TOKEN") or ""
    if not expected.strip():
        raise HTTPException(status_code=403, detail=_AUTO_IMPORT_OFF)
    scheme, _, supplied = (request.headers.get("authorization") or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied.strip().encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail=_BAD_IMPORT_TOKEN)

    form = await request.form()
    upload = form.get("file")
    if upload is None or isinstance(upload, str):
        raise HTTPException(status_code=400, detail=_NOT_A_MAX_STATEMENT)
    content = await upload.read()
    try:
        parsed = card_statement.parse_statement(content)
    except ValueError:
        raise HTTPException(status_code=400, detail=_NOT_A_MAX_STATEMENT)

    categories = _import_categories(db_conn)
    rows = card_statement.classify(db_conn, parsed["rows"])
    skipped = {"exists": 0, "recurring": 0}
    to_add: List[tuple] = []
    unsorted = 0
    for row in rows:
        if row["status"] != "new":
            skipped[row["status"]] += 1
            continue
        category_id, source = card_statement.guess_category(
            db_conn, row["merchant"], row["max_category"], categories
        )
        if source == "fallback":
            unsorted += 1
        to_add.append((row["date"], row["amount"], category_id, row["merchant"]))

    created: List[int] = []
    if to_add:
        account = db_conn.execute(
            "SELECT id FROM accounts WHERE name = ?", (_CREDIT_CARD_ACCOUNT,)
        ).fetchone()
        created = _insert_import_rows(
            db_conn,
            card_statement.guess_payer(db_conn, parsed["holder"], None),
            account["id"] if account else None,
            to_add,
        )
    added_dates = [r[0] for r in to_add]
    return JSONResponse(content={
        "added": len(created),
        "skipped": skipped,
        "unsorted": unsorted,
        "created": created,
        "holder": parsed["holder"],
        "statement_month": parsed["statement_month"],
        "date_from": min(added_dates) if added_dates else None,
        "date_to": max(added_dates) if added_dates else None,
    })


@router.post("/import/undo")
async def api_import_undo(
    body: schemas.ImportUndoRequest,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Delete the rows an import created. Recurrence-booked rows are never touched."""
    ids = sorted(set(body.ids))
    deleted = 0
    if ids:
        placeholders = ",".join("?" * len(ids))
        cur = db_conn.execute(
            f"DELETE FROM transactions WHERE id IN ({placeholders}) AND recurrence_id IS NULL",
            ids,
        )
        deleted = cur.rowcount
        db_conn.commit()
    _invalidate_stats_cache()
    return JSONResponse(content={"deleted": deleted})


# The transactions page edits with PUT, API clients with PATCH; both are a partial update.
@router.put("/{tx_id}", response_model=schemas.Transaction)
@router.patch("/{tx_id}", response_model=schemas.Transaction)
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
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if row["recurrence_id"] and row["period_key"]:
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
