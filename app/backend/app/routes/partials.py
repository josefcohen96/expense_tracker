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
        "WHERE t.id = ? AND t.recurrence_id IS NULL", (tx_id,)
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
    # Get only expense categories (excluding income categories)
    cats = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name").fetchall()
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
    # Get only expense categories (excluding income categories)
    cats = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name").fetchall()
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
        # Make amount negative since this is an expense
        amount_val = -abs(amount_val)
        category_int = int(category_id) if category_id is not None else None
        user_int = int(user_id) if user_id is not None else None
        account_int = int(account_id) if account_id not in (None, "") else None

        db_conn.execute(
            "UPDATE transactions SET date=?, amount=?, category_id=?, user_id=?, account_id=?, notes=?, tags=? "
            "WHERE id=? AND recurrence_id IS NULL",
            (date, amount_val, category_int, user_int, account_int, notes, tags, tx_id),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    tx = _fetch_tx_row(db_conn, tx_id)
    # Get only expense categories (excluding income categories)
    cats = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name").fetchall()
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
    db_conn.execute("DELETE FROM transactions WHERE id = ? AND recurrence_id IS NULL", (tx_id,))
    db_conn.commit()
    # מחזירים מחרוזת ריקה; HTMX יעשה swap=outerHTML => ימחק את השורה
    return HTMLResponse(content="")


# Income routes
@router.get("/income/{tx_id}/row", response_class=HTMLResponse)
async def get_income_row(
    request: Request,
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    tx = _fetch_income_row(db_conn, tx_id)
    cats = db_conn.execute("SELECT id, name FROM categories WHERE name IN ('קליניקה', 'משכורת') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse("partials/income/row.html", {
        "request": request, "tx": tx, "categories": cats, "users": users, "accounts": accs, "mode": "read",
    })


@router.get("/income/{tx_id}/edit-inline", response_class=HTMLResponse)
async def edit_income_row(
    request: Request,
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    tx = _fetch_income_row(db_conn, tx_id)
    cats = db_conn.execute("SELECT id, name FROM categories WHERE name IN ('קליניקה', 'משכורת') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse("partials/income/row.html", {
        "request": request, "tx": tx, "categories": cats, "users": users, "accounts": accs, "mode": "edit",
    })


@router.post("/income/{tx_id}/edit-inline", response_class=HTMLResponse)
async def update_income_row(
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
        # Make amount positive since this is income
        amount_val = abs(amount_val)
        category_int = int(category_id) if category_id is not None else None
        user_int = int(user_id) if user_id is not None else None
        account_int = int(account_id) if account_id not in (None, "") else None

        db_conn.execute(
            "UPDATE transactions SET date=?, amount=?, category_id=?, user_id=?, account_id=?, notes=?, tags=? "
            "WHERE id=? AND recurrence_id IS NULL",
            (date, amount_val, category_int, user_int, account_int, notes, tags, tx_id),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    tx = _fetch_income_row(db_conn, tx_id)
    cats = db_conn.execute("SELECT id, name FROM categories WHERE name IN ('קליניקה', 'משכורת') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse("partials/income/row.html", {
        "request": request, "tx": tx, "categories": cats, "users": users, "accounts": accs, "mode": "read",
    })


@router.post("/income/{tx_id}/delete-inline", response_class=HTMLResponse)
async def delete_income_row(
    tx_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    db_conn.execute("DELETE FROM transactions WHERE id = ? AND recurrence_id IS NULL", (tx_id,))
    db_conn.commit()
    # מחזירים מחרוזת ריקה; HTMX יעשה swap=outerHTML => ימחק את השורה
    return HTMLResponse(content="")


def _fetch_income_row(db_conn: sqlite3.Connection, tx_id: int):
    """Fetch income transaction row (positive amounts only)"""
    tx = db_conn.execute(
        "SELECT t.id, t.date, t.amount, t.category_id, t.user_id, t.account_id, t.notes, t.tags, "
        "c.name AS category_name, u.name AS user_name, a.name AS account_name "
        "FROM transactions t "
        "JOIN categories c ON t.category_id = c.id "
        "JOIN users u ON t.user_id = u.id "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "WHERE t.id = ? AND t.recurrence_id IS NULL AND t.amount > 0", (tx_id,)
    ).fetchone()
    if not tx:
        raise HTTPException(status_code=404, detail="Income transaction not found")
    return tx


# -----------------------------
# Recurrences inline partials
# -----------------------------
def _fetch_recurrence_row(db_conn: sqlite3.Connection, rec_id: int):
    r = db_conn.execute(
        """
        SELECT r.id,
               r.name,
               r.amount,
               r.category_id,
               r.user_id,
               r.account_id,
               r.frequency,
               r.next_charge_date,
               r.start_date,
               r.end_date,
               r.active,
               c.name AS category_name,
               u.name AS user_name,
               a.name AS account_name
          FROM recurrences r
     LEFT JOIN categories c ON r.category_id = c.id
     LEFT JOIN users u ON r.user_id = u.id
     LEFT JOIN accounts a ON r.account_id = a.id
         WHERE r.id = ?
        """,
        (rec_id,),
    ).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Recurrence not found")
    return r


@router.get("/recurrences/{rec_id}/row", response_class=HTMLResponse)
async def get_recurrence_row(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    r = _fetch_recurrence_row(db_conn, rec_id)
    return templates.TemplateResponse(
        "partials/recurrences/row.html",
        {"request": request, "r": r},
    )


@router.get("/recurrences/{rec_id}/edit-inline", response_class=HTMLResponse)
async def edit_recurrence_row(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    r = _fetch_recurrence_row(db_conn, rec_id)
    categories = db_conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse(
        "partials/recurrences/edit_row.html",
        {
            "request": request,
            "recurrence": r,
            "categories": categories,
            "users": users,
            "accounts": accounts,
        },
    )


@router.post("/recurrences/{rec_id}/edit-inline", response_class=HTMLResponse)
async def update_recurrence_row(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    body = await request.body()
    form = {k: v[0] if isinstance(v, list) else v for k, v in parse_qs(body.decode("utf-8")).items()}

    name = form.get("name")
    amount = form.get("amount")
    category_id = form.get("category_id")
    user_id = form.get("user_id")
    account_id = form.get("account_id") or None
    frequency = form.get("frequency")
    start_date = form.get("start_date")
    end_date = form.get("end_date") or None
    active = form.get("active")

    try:
        amount_val = float(amount) if amount is not None else 0.0
        category_int = int(category_id) if category_id is not None else None
        user_int = int(user_id) if user_id is not None else None
        account_int = int(account_id) if account_id not in (None, "") else None
        active_int = 1 if str(active) in ("1", "true", "True", "on") else 0

        db_conn.execute(
            """
            UPDATE recurrences
               SET name = ?, amount = ?, category_id = ?, user_id = ?, account_id = ?,
                   frequency = ?, start_date = ?, end_date = ?, active = ?
             WHERE id = ?
            """,
            (
                name,
                amount_val,
                category_int,
                user_int,
                account_int,
                frequency,
                start_date,
                end_date,
                active_int,
                rec_id,
            ),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    r = _fetch_recurrence_row(db_conn, rec_id)
    return templates.TemplateResponse(
        "partials/recurrences/row.html",
        {"request": request, "r": r},
    )


@router.post("/recurrences/{rec_id}/delete-inline", response_class=HTMLResponse)
async def delete_recurrence_row(
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    db_conn.execute("DELETE FROM recurrences WHERE id = ?", (rec_id,))
    db_conn.commit()
    return HTMLResponse(content="")
