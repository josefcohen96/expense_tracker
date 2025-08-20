from __future__ import annotations
import sqlite3
from typing import Any, Dict
from pathlib import Path as FSPath
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..db import get_db_conn

ROOT_DIR = FSPath(__file__).resolve().parents[3]  # .../expense_tracker/app
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(tags=["partials"])

def _fetch_tx_row(db_conn: sqlite3.Connection, tx_id: int):
    tx = db_conn.execute(
        "SELECT t.id, t.date, t.amount, t.category_id, t.user_id, t.account_id, t.notes, t.tags, "
        "c.name AS category_name, u.name AS user_name, a.name AS account_name "
        "FROM transactions t "
        "JOIN categories c ON t.category_id = c.id "
        "JOIN users u ON t.user_id = u.id "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "WHERE t.id = ?", (tx_id,)
    ).fetchone()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx

@router.get("/transactions/{tx_id}/row", response_class=HTMLResponse)
async def get_transaction_row(
    request: Request,
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    tx = _fetch_tx_row(db_conn, tx_id)
    cats = db_conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse("partials/transactions/row.html", {
        "request": request, "tx": tx, "categories": cats, "users": users, "accounts": accs, "mode": "read",
    })

@router.get("/transactions/{tx_id}/edit-inline", response_class=HTMLResponse)
async def edit_transaction_row(
    request: Request,
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    tx = _fetch_tx_row(db_conn, tx_id)
    cats = db_conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse("partials/transactions/row.html", {
        "request": request, "tx": tx, "categories": cats, "users": users, "accounts": accs, "mode": "edit",
    })

@router.post("/transactions/{tx_id}/edit-inline", response_class=HTMLResponse)
async def update_transaction_row(
    request: Request,
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    body = await request.body()
    form = {k: v[0] if isinstance(v, list) else v for k, v in parse_qs(body.decode("utf-8")).items()}

    date = form.get("date")
    amount = form.get("amount")
    category_id = form.get("category_id")
    user_id = form.get("user_id")
    account_id = form.get("account_id") or None
    notes = form.get("notes") or None
    tags = form.get("tags") or None

    try:
        amount_val = float(amount) if amount is not None else 0.0
        category_int = int(category_id) if category_id is not None else None
        user_int = int(user_id) if user_id is not None else None
        account_int = int(account_id) if account_id not in (None, "") else None

        db_conn.execute(
            "UPDATE transactions SET date=?, amount=?, category_id=?, user_id=?, account_id=?, notes=?, tags=? "
            "WHERE id=?",
            (date, amount_val, category_int, user_int, account_int, notes, tags, tx_id),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    tx = _fetch_tx_row(db_conn, tx_id)
    cats = db_conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse("partials/transactions/row.html", {
        "request": request, "tx": tx, "categories": cats, "users": users, "accounts": accs, "mode": "read",
    })

@router.post("/transactions/{tx_id}/delete-inline", response_class=HTMLResponse)
async def delete_transaction_row(
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    db_conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    db_conn.commit()
    # מחזירים מחרוזת ריקה; HTMX יעשה swap=outerHTML => ימחק את השורה
    return HTMLResponse(content="")
