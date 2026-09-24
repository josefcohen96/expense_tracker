"""
Spanish between sets — the queue, the reviews, the stats.

Under the workouts prefix on purpose: services/access.py already lets a workouts-only
login (Yonatan) through `/api/workouts/*` and keeps renovation-only logins out.
Each caller sees and writes only their own reviews (keyed by users.id).
"""
from __future__ import annotations

import sqlite3
from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from ..db import get_db_conn
from ..routes.workouts import _resolve_user_id
from ..schemas.spanish import SpanishReviewCreate
from ..services import spanish

router = APIRouter(prefix="/api/workouts/spanish", tags=["workouts"])


def _user_id(request: Request, db_conn: sqlite3.Connection) -> int:
    user_id = _resolve_user_id(request, db_conn)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


@router.get("/queue")
async def get_queue(
    request: Request,
    limit: int = Query(15, ge=1, le=50),
    new_cap: int = Query(spanish.DEFAULT_NEW_CAP, ge=0, le=30),
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    user_id = _user_id(request, db_conn)
    return spanish.snapshot(db_conn, user_id, date_cls.today(), limit=limit, new_cap=new_cap)


@router.get("/stats")
async def get_stats(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    user_id = _user_id(request, db_conn)
    return spanish.snapshot(db_conn, user_id, date_cls.today(), limit=0)["stats"]


@router.post("/reviews", status_code=201)
async def post_review(
    body: SpanishReviewCreate,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    user_id = _user_id(request, db_conn)
    spanish.record_review(db_conn, user_id, body.item_id, body.grade, body.mode, body.context)
    today = date_cls.today()
    deck = spanish.load_deck()
    reviews = spanish.fetch_reviews(db_conn, user_id)
    states = spanish.item_states(reviews)
    state = states[body.item_id]
    return JSONResponse(status_code=201, content={
        "item_id": body.item_id,
        "stage": state["stage"],
        "due_on": state["due_on"].isoformat(),
        "stats": spanish.stats(deck, reviews, today, states=states),
    })
