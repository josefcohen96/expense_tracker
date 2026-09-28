"""
קריאה לזירה — the push-subscription API behind the profile card on /workouts.

Lives under /api/workouts/push so every trainee (Yonatan included) can reach it through
WORKOUTS_PREFIXES. The texts themselves are built in services/push_service.py.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ..db import get_db_conn
from ..routes.workouts import _resolve_user_id
from ..schemas.push import PushSubscriptionSchema, PushUnsubscribeSchema
from ..services import push_service

router = APIRouter(prefix="/api/workouts/push", tags=["workouts-push"])


def _user_id(request: Request, db_conn: sqlite3.Connection) -> int:
    user_id = _resolve_user_id(request, db_conn)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


def _require_enabled() -> None:
    if not push_service.is_enabled():
        raise HTTPException(status_code=503, detail="Push notifications are not configured")


@router.get("/key")
async def api_push_key() -> dict:
    config = push_service.vapid_config()
    return {"enabled": config is not None, "public_key": config["public_key"] if config else None}


@router.post("/subscribe")
async def api_push_subscribe(
    body: PushSubscriptionSchema,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> dict:
    _require_enabled()
    user_id = _user_id(request, db_conn)
    push_service.save_subscription(db_conn, user_id, body.endpoint, body.keys.p256dh, body.keys.auth)
    return {"ok": True}


@router.delete("/subscribe")
async def api_push_unsubscribe(
    body: PushUnsubscribeSchema,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> dict:
    user_id = _user_id(request, db_conn)
    push_service.delete_subscription(db_conn, user_id, body.endpoint)
    return {"ok": True}


@router.post("/test")
async def api_push_test(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> dict:
    _require_enabled()
    user_id = _user_id(request, db_conn)
    return {"sent": push_service.send_to_user(db_conn, user_id, push_service.test_message())}
