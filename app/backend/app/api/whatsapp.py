"""
תרשום — the WhatsApp webhook (Meta Cloud API) and a browser endpoint for the grammar.

The two webhook routes are @public: Meta has no session. GET answers the verification
handshake with WHATSAPP_VERIFY_TOKEN; POST is accepted only with a valid
X-Hub-Signature-256 made with WHATSAPP_APP_SECRET. Both secrets are read at call time,
so an unset variable turns the route off. Replies are sent after the response from a
background task, so Meta never waits on the Graph API. The grammar itself lives in
services/whatsapp.py.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import sqlite3
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from ..auth import public
from ..db import get_db_conn
from ..schemas.whatsapp import TestMessage
from ..services import whatsapp
from ..services.people import find_person, household

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

_OFF = "וואטסאפ כבוי"
_BAD_TOKEN = "אסימון לא תקין"
_BAD_SIGNATURE = "חתימה לא תקינה"
_NOT_HOUSEHOLD = "רק יוסף וקארינה יכולים לרשום מהצ'אט"


@router.get("/webhook")
@public
async def api_whatsapp_verify(request: Request) -> PlainTextResponse:
    """Meta's subscription handshake: echo hub.challenge when the verify token matches."""
    expected = (os.environ.get("WHATSAPP_VERIFY_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail=_OFF)
    params = request.query_params
    supplied = params.get("hub.verify_token") or ""
    if params.get("hub.mode") != "subscribe" or not hmac.compare_digest(
        supplied.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail=_BAD_TOKEN)
    return PlainTextResponse(params.get("hub.challenge") or "")


def _incoming_messages(payload: Any) -> list[dict]:
    """Every entry[].changes[].value.messages[] item, in order; status payloads have none."""
    found: list[dict] = []
    if not isinstance(payload, dict):
        return found
    entries = payload.get("entry")
    for entry in entries if isinstance(entries, list) else []:
        changes = entry.get("changes") if isinstance(entry, dict) else None
        for change in changes if isinstance(changes, list) else []:
            value = change.get("value") if isinstance(change, dict) else None
            messages = value.get("messages") if isinstance(value, dict) else None
            for message in messages if isinstance(messages, list) else []:
                if isinstance(message, dict):
                    found.append(message)
    return found


@router.post("/webhook")
@public
async def api_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> dict:
    """Incoming chat messages. Always 200 once the signature passes, so Meta does not retry."""
    secret = (os.environ.get("WHATSAPP_APP_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=403, detail=_OFF)
    body = await request.body()
    if not whatsapp.verify_signature(secret, body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=401, detail=_BAD_SIGNATURE)

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        logger.warning("WhatsApp webhook: signed body is not JSON")
        return {"handled": 0}

    handled = 0
    for message in _incoming_messages(payload):
        wa_id = str(message.get("from") or "")
        user = whatsapp.sender_for(wa_id)
        if user is None:
            logger.warning("WhatsApp message from an unknown number ignored")
            continue
        message_id = message.get("id")
        if whatsapp.already_seen(message_id):
            continue
        if message.get("type") != "text":
            reply = whatsapp.TEXT_ONLY
        else:
            text = ((message.get("text") or {}).get("body")) or ""
            try:
                reply = whatsapp.handle_message(db_conn, user, text)
            except Exception:
                logger.exception("WhatsApp message failed")
                try:
                    db_conn.rollback()
                except Exception:
                    pass
                reply = whatsapp.SOMETHING_WRONG
        background_tasks.add_task(whatsapp.send_text, wa_id, reply, message_id)
        handled += 1
    return {"handled": handled}


@router.post("/test")
async def api_whatsapp_test(
    body: TestMessage,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> dict:
    """Run one chat line for real as the signed-in user (rows are written) and return the
    reply here instead of sending it to WhatsApp."""
    user = getattr(request.state, "user", None) or request.session.get("user")
    if find_person(household(db_conn), user) is None:
        raise HTTPException(status_code=403, detail=_NOT_HOUSEHOLD)
    return {"reply": whatsapp.handle_message(db_conn, user, body.text)}
