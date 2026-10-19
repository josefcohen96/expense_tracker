from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from ...db import get_db_conn
from ...schemas.wedding import (
    SettingUpsert,
)
from ...services import overseas, wedding_plan

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Settings ────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rows = db_conn.execute("SELECT key, value FROM wedding_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


@router.post("/settings")
async def upsert_setting(body: SettingUpsert, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    if body.key == "wedding_date":
        try:
            date.fromisoformat(body.value)
        except ValueError:
            raise HTTPException(status_code=422, detail="תאריך לא תקין")
    elif body.key == "venue_capacity" and body.value != "":
        if not body.value.isdigit():
            raise HTTPException(status_code=422, detail="קיבולת חייבת להיות מספר")
    elif body.key == overseas.LEAD_DAYS_KEY:
        value = body.value.strip()
        if not value.isdigit() or not (overseas.MIN_LEAD_DAYS <= int(value) <= overseas.MAX_LEAD_DAYS):
            raise HTTPException(status_code=422, detail="זמן אספקה חייב להיות בין שבוע ל-20 שבועות")
    db_conn.execute(
        "INSERT INTO wedding_settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
        (body.key, body.value),
    )
    if body.key == "wedding_date":
        # Milestone dates are offsets from this date, so they move with it.
        wedding_plan.seed_default_milestones(db_conn)
    db_conn.commit()
    return {"key": body.key, "value": body.value}
