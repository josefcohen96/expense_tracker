from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

from .. import db
from ..services.whatsapp_service import get_whatsapp_service


router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


@router.get("/webhook")
async def verify_webhook(request: Request):
    """
    Meta verification endpoint.
    Expects query params: 'hub.mode', 'hub.verify_token', 'hub.challenge'
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    verify_token = os.getenv("META_VERIFY_TOKEN", "")

    if mode == "subscribe" and token == verify_token and challenge is not None:
        return PlainTextResponse(content=str(challenge), status_code=200)
    return PlainTextResponse(content="Forbidden", status_code=403)


@router.post("/webhook")
async def receive_webhook(payload: Dict[str, Any]):
    """
    Receive WhatsApp messages from Meta and process them.
    """
    service = get_whatsapp_service(db.get_db_path())
    inserted = await service.handle_incoming(payload)
    # Always return 200 to Meta
    return JSONResponse({"received": True, "created": bool(inserted), "transaction": inserted})


class IngestRequest(BaseModel):
    phone: str
    text: str


@router.post("/ingest")
async def ingest_message(req: IngestRequest):
    """
    Lightweight endpoint for n8n: accept phone + raw text, parse and insert.
    Does NOT send WhatsApp message back; returns a reply string to use from n8n.
    """
    service = get_whatsapp_service(db.get_db_path())
    inserted = service.create_expense_transaction(req.phone, req.text)
    reply = f"נקלטה הוצאה של {abs(inserted['amount']):.2f}- ₪ בתאריך {inserted['date']}. תודה!"
    return JSONResponse({"created": True, "transaction": inserted, "reply": reply})


