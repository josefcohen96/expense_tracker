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
    # Determine next_charge_date if not provided
    from datetime import date, timedelta
    frequency = rec.frequency
    day_of_month = rec.day_of_month
    weekday = rec.weekday
    next_charge_date = rec.next_charge_date

    def clamp_day(year: int, month: int, day: int) -> str:
        import calendar
        last = calendar.monthrange(year, month)[1]
        if day < 1:
            day = 1
        if day > last:
            day = last
        return f"{year:04d}-{month:02d}-{day:02d}"

    if not next_charge_date:
        today = date.today()
        if frequency == "monthly":
            if day_of_month is None:
                day_of_month = 1
            y, m = today.year, today.month
            tentative = clamp_day(y, m, int(day_of_month))
            if tentative < today.isoformat():
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1
                tentative = clamp_day(y, m, int(day_of_month))
            next_charge_date = tentative
        elif frequency == "weekly":
            if weekday is None:
                weekday = 6
            delta = (int(weekday) - today.weekday()) % 7
            next_dt = today if delta == 0 else today + timedelta(days=delta)
            next_charge_date = next_dt.isoformat()
        elif frequency == "yearly":
            # Default Aug 1st
            mm, dd = 8, 1
            y = today.year
            candidate = f"{y:04d}-{mm:02d}-{dd:02d}"
            if candidate < today.isoformat():
                candidate = f"{y+1:04d}-{mm:02d}-{dd:02d}"
            next_charge_date = candidate
        else:
            next_charge_date = (today + timedelta(days=1)).isoformat()

    # Insert according to schema (including optional account_id)
    cur = db_conn.execute(
        "INSERT INTO recurrences (name, amount, category_id, user_id, frequency, day_of_month, weekday, next_charge_date, active, account_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rec.name,
            rec.amount,
            rec.category_id,
            rec.user_id,
            frequency,
            day_of_month,
            weekday,
            next_charge_date,
            1 if rec.active else 0,
            rec.account_id,
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
        frequency=frequency,
        day_of_month=day_of_month,
        weekday=weekday,
        next_charge_date=next_charge_date,
        custom_cron=rec.custom_cron,
        account_id=rec.account_id,
        active=rec.active,
    )

@router.patch("/{rec_id}", response_model=schemas.Recurrence)
async def api_update_recurrence(
    rec_id: int,
    update: schemas.RecurrenceUpdate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Recurrence:
    """Update an existing recurring transaction."""
    fields = update.dict(exclude_unset=True)
    # Adjust defaults if frequency changes and next_charge_date not provided
    if "frequency" in fields and "next_charge_date" not in fields:
        from datetime import date, timedelta
        freq = fields["frequency"]
        today = date.today()
        if freq == "monthly":
            dom = fields.get("day_of_month", 1)
            def clamp_day(year: int, month: int, day: int) -> str:
                import calendar
                last = calendar.monthrange(year, month)[1]
                if day < 1:
                    day = 1
                if day > last:
                    day = last
                return f"{year:04d}-{month:02d}-{day:02d}"
            y, m = today.year, today.month
            tentative = clamp_day(y, m, int(dom))
            if tentative < today.isoformat():
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1
                tentative = clamp_day(y, m, int(dom))
            fields["next_charge_date"] = tentative
        elif freq == "weekly":
            wday = fields.get("weekday", 6)
            delta = (int(wday) - today.weekday()) % 7
            next_dt = today if delta == 0 else today + timedelta(days=delta)
            fields["next_charge_date"] = next_dt.isoformat()
        elif freq == "yearly":
            mm, dd = 8, 1
            y = today.year
            candidate = f"{y:04d}-{mm:02d}-{dd:02d}"
            if candidate < today.isoformat():
                candidate = f"{y+1:04d}-{mm:02d}-{dd:02d}"
            fields["next_charge_date"] = candidate
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
    """Run recurrence materialization once, on demand."""
    inserted = recurrence.apply_recurring()
    return JSONResponse(content={"inserted": inserted, "status": "ok"})


@router.post("/{rec_id}/apply-once")
async def api_apply_recurrence_once(
    rec_id: int,
    payload: schemas.RecurrenceApplyOnce,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> JSONResponse:
    """Insert a single occurrence immediately for the given recurrence id and date.

    If date is omitted, uses today's date. Amount defaults to the recurrence amount.
    """
    row = db_conn.execute("SELECT * FROM recurrences WHERE id = ?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Recurrence not found")
    rec = dict(row)

    from datetime import date as _date
    due_date = payload.date or _date.today().isoformat()
    amount = payload.amount if payload.amount is not None else -abs(rec["amount"])  # ensure expense

    cur = db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            due_date,
            amount,
            rec["category_id"],
            rec["user_id"],
            rec.get("account_id"),
            payload.notes,
            None,
            rec_id,
            due_date,
        ),
    )
    db_conn.commit()
    return JSONResponse(content={"inserted": True, "transaction_id": cur.lastrowid})
