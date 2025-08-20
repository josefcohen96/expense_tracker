from typing import List
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from .. import schemas
from ..db import get_db_conn
from ..services.recurrence_service import apply_recurring_transactions  # <- שירות  :contentReference[oaicite:4]{index=4}

router = APIRouter(prefix="/api/recurrences", tags=["recurrences"])
system_router = APIRouter(prefix="/api/system", tags=["system"])

@router.get("", response_model=List[schemas.Recurrence])
async def api_get_recurrences(
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> List[schemas.Recurrence]:
    rows = db_conn.execute("SELECT * FROM recurrences").fetchall()
    return [schemas.Recurrence(**dict(row)) for row in rows]

@router.post("", response_model=schemas.Recurrence)
async def api_create_recurrence(
    rec: schemas.RecurrenceCreate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Recurrence:
    cur = db_conn.execute(
        "INSERT INTO recurrences (name, amount, category_id, user_id, start_date, end_date, frequency, day_of_month, weekday, custom_cron, account_id, active) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rec.name,
            rec.amount,
            rec.category_id,
            rec.user_id,
            rec.start_date,
            rec.end_date,
            rec.frequency,
            rec.day_of_month,
            rec.weekday,
            rec.custom_cron,
            rec.account_id,
            1 if rec.active else 0,
        ),
    )
    db_conn.commit()
    new_id = cur.lastrowid
    return schemas.Recurrence(id=new_id, **rec.dict())

@router.patch("/{rec_id}", response_model=schemas.Recurrence)
async def api_update_recurrence(
    rec_id: int,
    update: schemas.RecurrenceCreate,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> schemas.Recurrence:
    fields = update.dict(exclude_unset=True)
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

@system_router.post("/apply-recurring")
async def api_apply_recurring() -> JSONResponse:
    inserted = apply_recurring_transactions()  # שימוש בשירות
    return JSONResponse(content={"inserted": inserted})
