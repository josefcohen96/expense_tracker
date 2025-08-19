"""Entry point for the FastAPI application.

This module sets up the API routes for both HTML pages and JSON
endpoints. It initialises the database on startup and applies
recurring transactions. The HTML pages are rendered using
Jinja2 templates and styled with Tailwind via CDN. The JSON
endpoints expose the underlying data for programmatic access.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict, Any
import sqlite3
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, recurrence, backup, schemas

from datetime import datetime


app = FastAPI(title="CoupleBudget Local", version="0.1.0")

# Set up templates and static files directories
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    # Initialise the database and seed defaults
    db.initialise_database()
    # Apply recurring transactions up to today
    try:
        inserted = recurrence.apply_recurring()
        if inserted:
            print(f"Applied {inserted} recurring transactions on startup.")
    except Exception as exc:
        print(f"Failed to apply recurring transactions: {exc}")
    # Optional: create auto-backup on startup if enabled
    try:
        if str(os.getenv("AUTO_BACKUP_ON_STARTUP", "1")) in {"1", "true", "True"}:
            bpath = backup.create_backup(only_if_no_backup_today=True)
            print(f"Startup backup ensured at: {bpath}")
    except Exception as exc:
        print(f"Startup backup failed: {exc}")


@app.on_event("shutdown")
def on_shutdown() -> None:
    # Optional: create auto-backup on shutdown if enabled
    try:
        if str(os.getenv("AUTO_BACKUP_ON_SHUTDOWN", "1")) in {"1", "true", "True"}:
            bpath = backup.create_backup(only_if_no_backup_today=True)
            print(f"Shutdown backup ensured at: {bpath}")
    except Exception as exc:
        print(f"Shutdown backup failed: {exc}")


def get_db_conn() -> sqlite3.Connection:
    conn = db.get_connection()
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ------------------------- HTML Pages -------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Render the dashboard with simple summaries."""
    # Compute simple stats: total number of transactions, total expenses, total income
    stats: Dict[str, Any] = {
        "transactions_count": 0,
        "total_expenses": 0.0,
        "total_income": 0.0,
    }
    cur = db_conn.execute("SELECT COUNT(*), SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) FROM transactions")
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


@app.get("/transactions", response_class=HTMLResponse)
async def transactions_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Display a list of transactions and a form to add a new one."""
    # Fetch all transactions ordered by date desc
    txs = db_conn.execute(
        "SELECT t.id, t.date, t.amount, c.name AS category_name, u.name AS user_name, a.name AS account_name, t.notes, t.tags "
        "FROM transactions t "
        "JOIN categories c ON t.category_id = c.id "
        "JOIN users u ON t.user_id = u.id "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "ORDER BY t.date DESC, t.id DESC"
    ).fetchall()
    # Fetch categories, users and accounts for the form
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


@app.post("/transactions")
async def create_transaction(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    """Handle submission of a new transaction from the HTML form.

    This route extracts form data manually to avoid relying on
    `python-multipart`, which may not be installed in all
    environments.
    """
    form = await request.form()
    date = form.get("date")
    amount = form.get("amount")
    category_id = form.get("category_id")
    user_id = form.get("user_id")
    account_id = form.get("account_id") or None
    notes = form.get("notes") or None
    tags = form.get("tags") or None
    try:
        # Convert amount to float; category_id and user_id to int
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


@app.get("/recurrences", response_class=HTMLResponse)
async def recurrences_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Display recurring rules and a form to create a new one."""
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


@app.post("/recurrences")
async def create_recurrence(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    """Handle submission of a new recurring rule from the HTML form.

    Extracts form fields manually to avoid dependency on
    `python-multipart`.
    """
    form = await request.form()
    name = form.get("name")
    amount = form.get("amount")
    category_id = form.get("category_id")
    user_id = form.get("user_id")
    start_date = form.get("start_date")
    frequency = form.get("frequency")
    day_of_month = form.get("day_of_month") or None
    weekday = form.get("weekday") or None
    # Validate frequency
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


@app.get("/backup", response_class=HTMLResponse)
async def backup_page(request: Request) -> HTMLResponse:
    """Display backup management page."""
    backups = backup.list_backups()
    return templates.TemplateResponse(
        "backup.html",
        {
            "request": request,
            "backups": backups,
        },
    )


@app.post("/backup/create")
async def backup_create() -> RedirectResponse:
    """Trigger creation of an Excel backup and redirect back to backup page."""
    backup.create_backup()
    return RedirectResponse(url="/backup", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/backup/restore/{file_name}")
async def backup_restore_file(file_name: str) -> RedirectResponse:
    """Restore the database from a named backup file and redirect."""
    file_path = backup.BACKUP_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        backup.restore_from_backup(file_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/backup", status_code=status.HTTP_303_SEE_OTHER)




# Download backup file
@app.get("/backup/download/{file_name}")
async def backup_download(file_name: str) -> FileResponse:
    """Download a backup file."""
    file_path = backup.BACKUP_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(str(file_path), filename=file_name)


# ------------------------- API Endpoints -------------------------

api_prefix = "/api"


@app.get(f"{api_prefix}/transactions", response_model=List[schemas.Transaction])
async def api_get_transactions(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category_id: Optional[int] = None,
    user_id: Optional[int] = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> List[schemas.Transaction]:
    """Return transactions with optional filtering by date range, category and user."""
    query = "SELECT * FROM transactions WHERE 1=1"
    params: List[Any] = []
    if from_date:
        query += " AND date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND date <= ?"
        params.append(to_date)
    if category_id:
        query += " AND category_id = ?"
        params.append(category_id)
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY date DESC, id DESC"
    rows = db_conn.execute(query, params).fetchall()
    return [schemas.Transaction(**dict(row)) for row in rows]


@app.post(f"{api_prefix}/transactions", response_model=schemas.Transaction)
async def api_create_transaction(tr: schemas.TransactionCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> schemas.Transaction:
    """Create a new transaction from JSON payload."""
    cur = db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tr.date,
            tr.amount,
            tr.category_id,
            tr.user_id,
            tr.account_id,
            tr.notes,
            tr.tags,
            tr.recurrence_id,
            tr.period_key,
        ),
    )
    db_conn.commit()
    new_id = cur.lastrowid
    return schemas.Transaction(id=new_id, **tr.dict())


@app.put(f"{api_prefix}/transactions/{{tx_id}}", response_model=schemas.Transaction)
async def api_update_transaction(tx_id: int, update: schemas.TransactionUpdate, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> schemas.Transaction:
    """Update an existing transaction."""
    # Build dynamic update query
    fields = update.dict(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
    params = list(fields.values()) + [tx_id]
    db_conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ?", params)
    db_conn.commit()
    row = db_conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return schemas.Transaction(**dict(row))


@app.delete(f"{api_prefix}/transactions/{{tx_id}}")
async def api_delete_transaction(tx_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> JSONResponse:
    """Delete a transaction and return a success flag."""
    db_conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    db_conn.commit()
    return JSONResponse(content={"deleted": True})


@app.get(f"{api_prefix}/recurrences", response_model=List[schemas.Recurrence])
async def api_get_recurrences(db_conn: sqlite3.Connection = Depends(get_db_conn)) -> List[schemas.Recurrence]:
    rows = db_conn.execute("SELECT * FROM recurrences").fetchall()
    return [schemas.Recurrence(**dict(row)) for row in rows]


@app.post(f"{api_prefix}/recurrences", response_model=schemas.Recurrence)
async def api_create_recurrence(rec: schemas.RecurrenceCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> schemas.Recurrence:
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


@app.patch(f"{api_prefix}/recurrences/{{rec_id}}", response_model=schemas.Recurrence)
async def api_update_recurrence(rec_id: int, update: schemas.RecurrenceCreate, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> schemas.Recurrence:
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


@app.post(f"{api_prefix}/system/apply-recurring")
async def api_apply_recurring() -> JSONResponse:
    """Manually apply recurring transactions and report the count of new transactions."""
    inserted = recurrence.apply_recurring()
    return JSONResponse(content={"inserted": inserted})


@app.post(f"{api_prefix}/backup/excel")
async def api_backup_create() -> JSONResponse:
    path = backup.create_backup()
    return JSONResponse(content={"file": path.name})


@app.get(f"{api_prefix}/backup/list", response_model=schemas.BackupList)
async def api_backup_list() -> schemas.BackupList:
    backups = backup.list_backups()
    items = [schemas.BackupItem(**b) for b in backups]
    return schemas.BackupList(backups=items)


@app.post(f"{api_prefix}/backup/restore")
async def api_backup_restore(request: Request) -> JSONResponse:
    """Restore database from raw XLSX bytes posted in the body.

    The entire request body should contain the binary contents of an Excel
    file. This avoids reliance on `python-multipart` for file
    uploads.
    """
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")
    tmp_path = backup.BACKUP_DIR / f"api_restore_{datetime.now().timestamp()}.xlsx"
    with open(tmp_path, "wb") as f:
        f.write(data)
    try:
        counts = backup.restore_from_backup(tmp_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))
    tmp_path.unlink(missing_ok=True)
    return JSONResponse(content={"restored": True, "counts": counts})