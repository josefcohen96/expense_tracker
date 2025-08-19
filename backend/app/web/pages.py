from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from ..legacy import db as legacy_db
from ..legacy import backup as legacy_backup
from ..core import config


router = APIRouter()

templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


def mount_static(app) -> None:
    if config.STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


def get_db_conn() -> sqlite3.Connection:
    conn = legacy_db.get_connection()
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    stats: Dict[str, Any] = {
        "transactions_count": 0,
        "total_expenses": 0.0,
        "total_income": 0.0,
    }
    cur = db_conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) FROM transactions"
    )
    row = cur.fetchone()
    if row:
        stats["transactions_count"] = row[0] or 0
        stats["total_expenses"] = abs(row[1] or 0.0)
        stats["total_income"] = row[2] or 0.0
    cur.close()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": stats,
        },
    )


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    txs = db_conn.execute(
        "SELECT t.id, t.date, t.amount, c.name AS category_name, u.name AS user_name, a.name AS account_name, t.notes, t.tags "
        "FROM transactions t "
        "JOIN categories c ON t.category_id = c.id "
        "JOIN users u ON t.user_id = u.id "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "ORDER BY t.date DESC, t.id DESC"
    ).fetchall()
    cats = db_conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse(
        "transactions.html",
        {
            "request": request,
            "transactions": txs,
            "categories": cats,
            "users": users,
            "accounts": accs,
        },
    )


@router.post("/transactions")
async def create_transaction(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    form = await request.form()
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
            "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                date,
                amount_val,
                category_int,
                user_int,
                account_int,
                notes,
                tags,
            ),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/transactions", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recurrences", response_class=HTMLResponse)
async def recurrences_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    recs = db_conn.execute(
        "SELECT r.id, r.name, r.amount, c.name AS category_name, u.name AS user_name, r.frequency, r.start_date, r.end_date, r.day_of_month, r.weekday, r.active "
        "FROM recurrences r "
        "JOIN categories c ON r.category_id = c.id "
        "JOIN users u ON r.user_id = u.id "
        "ORDER BY r.name"
    ).fetchall()
    cats = db_conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    return templates.TemplateResponse(
        "recurrences.html",
        {
            "request": request,
            "recurrences": recs,
            "categories": cats,
            "users": users,
        },
    )


@router.post("/recurrences")
async def create_recurrence(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    form = await request.form()
    name = form.get("name")
    amount = form.get("amount")
    category_id = form.get("category_id")
    user_id = form.get("user_id")
    start_date = form.get("start_date")
    frequency = form.get("frequency")
    day_of_month = form.get("day_of_month") or None
    weekday = form.get("weekday") or None
    allowed = {"monthly", "weekly", "yearly"}
    if frequency not in allowed:
        raise HTTPException(status_code=400, detail="Invalid frequency")
    try:
        amount_val = float(amount) if amount is not None else 0.0
        cat_int = int(category_id) if category_id is not None else None
        user_int = int(user_id) if user_id is not None else None
        day_int = int(day_of_month) if day_of_month not in (None, "") else None
        weekday_int = int(weekday) if weekday not in (None, "") else None
        db_conn.execute(
            "INSERT INTO recurrences (name, amount, category_id, user_id, start_date, frequency, day_of_month, weekday, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (
                name,
                amount_val,
                cat_int,
                user_int,
                start_date,
                frequency,
                day_int,
                weekday_int,
            ),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/recurrences", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/backup", response_class=HTMLResponse)
async def backup_page(request: Request) -> HTMLResponse:
    backups = legacy_backup.list_backups()
    return templates.TemplateResponse(
        "backup.html",
        {
            "request": request,
            "backups": backups,
        },
    )


@router.post("/backup/create")
async def backup_create() -> RedirectResponse:
    legacy_backup.create_backup()
    return RedirectResponse(url="/backup", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/backup/restore/{file_name}")
async def backup_restore_file(file_name: str) -> RedirectResponse:
    file_path = legacy_backup.BACKUP_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    legacy_backup.restore_from_backup(file_path)
    return RedirectResponse(url="/backup", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/backup/download/{file_name}")
async def backup_download(file_name: str) -> FileResponse:
    file_path = legacy_backup.BACKUP_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(str(file_path), filename=file_name)

