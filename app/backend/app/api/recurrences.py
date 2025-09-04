from typing import List
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from .. import schemas
from ..db import get_db_conn
from .. import recurrence  # Use direct import instead of service

router = APIRouter(prefix="/api/recurrences", tags=["recurrences"])
system_router = APIRouter(prefix="/api/system", tags=["system"])

@router.get("", response_model=List[schemas.Recurrence])
async def api_get_recurrences(
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> List[schemas.Recurrence]:
    """Get all recurring transactions."""
    rows = db_conn.execute("SELECT * FROM recurrences").fetchall()
    return [schemas.Recurrence(**dict(row)) for row in rows]

@router.post("", response_model=schemas.Recurrence)
async def api_create_recurrence(
    rec: schemas.RecurrenceCreate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Recurrence:
    """Create a new recurring transaction."""
    # Set scheduling defaults only when fields are missing
    frequency = rec.frequency
    start_date = rec.start_date
    day_of_month = rec.day_of_month
    weekday = rec.weekday

    # Provide sensible defaults
    from datetime import date
    today_iso = date.today().isoformat()

    if frequency == "monthly":
        if day_of_month is None:
            day_of_month = 1
        if not start_date:
            # default to today to satisfy NOT NULL constraint
            start_date = today_iso
    elif frequency == "weekly":
        if weekday is None:
            weekday = 6  # Sunday default
        if not start_date:
            start_date = today_iso
    elif frequency == "yearly":
        if not start_date:
            year = date.today().year
            start_date = f"{year:04d}-08-01"

    # Align with current DB schema (no custom_cron/account_id columns)
    cur = db_conn.execute(
        "INSERT INTO recurrences (name, amount, category_id, user_id, start_date, end_date, frequency, day_of_month, weekday, active) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rec.name,
            rec.amount,
            rec.category_id,
            rec.user_id,
            start_date,
            rec.end_date,
            frequency,
            day_of_month,
            weekday,
            1 if rec.active else 0,
        ),
    )
    db_conn.commit()
    new_id = cur.lastrowid
    # Return with effective values (including defaults applied)
    return schemas.Recurrence(
        id=new_id,
        name=rec.name,
        amount=rec.amount,
        category_id=rec.category_id,
        user_id=rec.user_id,
        start_date=start_date,
        end_date=rec.end_date,
        frequency=frequency,
        day_of_month=day_of_month,
        weekday=weekday,
        custom_cron=rec.custom_cron,
        account_id=rec.account_id,
        active=rec.active,
    )

@router.patch("/{rec_id}", response_model=schemas.Recurrence)
async def api_update_recurrence(
    rec_id: int,
    update: schemas.RecurrenceCreate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Recurrence:
    """Update an existing recurring transaction."""
    fields = update.dict(exclude_unset=True)
    # Enforce canonical schedule rules on update as well
    if "frequency" in fields:
        freq = fields["frequency"]
        if freq == "monthly":
            # Only set default day if not provided
            if fields.get("day_of_month") is None:
                fields["day_of_month"] = 1
        elif freq == "weekly":
            if fields.get("weekday") is None:
                fields["weekday"] = 6
        elif freq == "yearly":
            if not fields.get("start_date"):
                from datetime import date
                year = date.today().year
                fields["start_date"] = f"{year:04d}-08-01"
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
    params = list(fields.values()) + [rec_id]
    db_conn.execute(f"UPDATE recurrences SET {set_clause} WHERE id = ?", params)
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM recurrences WHERE id = ?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Recurrence not found")
    return schemas.Recurrence(**dict(row))

@router.delete("/{rec_id}")
async def api_delete_recurrence(
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Delete a recurring transaction."""
    db_conn.execute("DELETE FROM recurrences WHERE id = ?", (rec_id,))
    db_conn.commit()
    return JSONResponse(content={"deleted": True})

@system_router.post("/apply-recurring")
async def api_apply_recurring() -> JSONResponse:
    """Apply recurring transactions manually."""
    inserted = recurrence.apply_recurring()
    return JSONResponse(content={"inserted": inserted})


@router.post("/{rec_id}/apply-once")
async def api_apply_recurrence_once(
    rec_id: int,
    payload: schemas.RecurrenceApplyOnce,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Insert a single transaction occurrence for a recurrence without altering its schedule.

    - date: optional; defaults to today or next due date logic if omitted
    - amount: optional override; defaults to recurrence amount
    - notes: optional notes
    """
    rec = db_conn.execute("SELECT * FROM recurrences WHERE id = ?", (rec_id,)).fetchone()
    if not rec:
        raise HTTPException(status_code=404, detail="Recurrence not found")

    from datetime import date as _date
    target_date = payload.date or _date.today().isoformat()
    base_amount = float(rec["amount"])
    amount = float(payload.amount) if payload.amount is not None else base_amount
    # Ensure negative (expense)
    amount = -abs(amount)

    # Link to the recurrence but with a custom non-conflicting period_key so it won't block
    # the regular monthly/weekly/yearly generator which uses canonical keys.
    base_key = f"adhoc:{target_date}"
    period_key = base_key

    # Ensure UNIQUE(recurrence_id, period_key)
    suffix = 1
    while True:
        exists = db_conn.execute(
            "SELECT 1 FROM transactions WHERE recurrence_id = ? AND period_key = ? LIMIT 1",
            (rec_id, period_key),
        ).fetchone()
        if not exists:
            break
        suffix += 1
        period_key = f"{base_key}-{suffix}"

    cur = db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            target_date,
            amount,
            rec["category_id"],
            rec["user_id"],
            rec["account_id"] if "account_id" in rec.keys() else None,
            payload.notes,
            None,
            rec_id,
            period_key,
        ),
    )
    db_conn.commit()
    return JSONResponse(content={"inserted": True, "transaction_id": cur.lastrowid})
