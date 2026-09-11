import calendar
from datetime import date, timedelta
from typing import List
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from .. import schemas
from ..db import get_db_conn
from .. import recurrence
from ..recurrence import _clamp_day

router = APIRouter(prefix="/api/recurrences", tags=["recurrences"])
system_router = APIRouter(prefix="/api/system", tags=["system"])


def _next_charge_date_for_frequency(
    frequency: str,
    day_of_month: int | None,
    weekday: int | None,
) -> str:
    """Compute a sensible initial next_charge_date for a given frequency."""
    today = date.today()

    if frequency == "monthly":
        dom = int(day_of_month) if day_of_month is not None else 1
        y, m = today.year, today.month
        tentative = _clamp_day(y, m, dom).isoformat()
        if tentative < today.isoformat():
            m += 1
            if m > 12:
                y, m = y + 1, 1
            tentative = _clamp_day(y, m, dom).isoformat()
        return tentative

    if frequency == "weekly":
        target = int(weekday) if weekday is not None else 6
        delta = (target - today.weekday()) % 7
        next_dt = today if delta == 0 else today + timedelta(days=delta)
        return next_dt.isoformat()

    if frequency == "yearly":
        mm, dd = 8, 1
        y = today.year
        candidate = f"{y:04d}-{mm:02d}-{dd:02d}"
        if candidate < today.isoformat():
            candidate = f"{y+1:04d}-{mm:02d}-{dd:02d}"
        return candidate

    # Unknown frequency — schedule for tomorrow as a safe fallback
    return (today + timedelta(days=1)).isoformat()


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
    next_charge_date = rec.next_charge_date or _next_charge_date_for_frequency(
        rec.frequency, rec.day_of_month, rec.weekday
    )

    cur = db_conn.execute(
        "INSERT INTO recurrences (name, amount, category_id, user_id, frequency, day_of_month, weekday, next_charge_date, active, account_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rec.name,
            rec.amount,
            rec.category_id,
            rec.user_id,
            rec.frequency,
            rec.day_of_month,
            rec.weekday,
            next_charge_date,
            1 if rec.active else 0,
            rec.account_id,
        ),
    )
    # Commit before calling apply_recurring so the new row is visible to its connection
    db_conn.commit()
    new_id = cur.lastrowid

    # Immediately materialize any past-due occurrences (idempotent)
    recurrence.apply_recurring()

    row = db_conn.execute("SELECT * FROM recurrences WHERE id = ?", (new_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Failed to load created recurrence")
    return schemas.Recurrence(**dict(row))


@router.patch("/{rec_id}", response_model=schemas.Recurrence)
async def api_update_recurrence(
    rec_id: int,
    update: schemas.RecurrenceUpdate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Recurrence:
    """Update an existing recurring transaction."""
    fields = update.dict(exclude_unset=True)

    # Recalculate next_charge_date when frequency changes and the caller didn't provide one
    if "frequency" in fields and "next_charge_date" not in fields:
        fields["next_charge_date"] = _next_charge_date_for_frequency(
            fields["frequency"],
            fields.get("day_of_month"),
            fields.get("weekday"),
        )

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
    row = db_conn.execute("SELECT id FROM recurrences WHERE id = ?", (rec_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Recurrence not found")
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

    due_date = payload.date or date.today().isoformat()
    amount = payload.amount if payload.amount is not None else -abs(rec["amount"])

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
