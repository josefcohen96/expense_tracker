from __future__ import annotations
import os
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path as FSPath
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from ..db import get_db_conn
# ===== Templates dir (frontend) =====
ROOT_DIR = FSPath(__file__).resolve().parents[3]  # .../expense_tracker/app
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["pages"])

# --------- Pages ---------


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Dashboard: counters for total txs / total expenses / total income."""
    stats: Dict[str, Any] = {"transactions_count": 0,
                             "total_expenses": 0.0, "total_income": 0.0}
    # Calculate expenses from regular transactions
    cur = db_conn.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), "
        "SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) "
        "FROM transactions WHERE recurrence_id IS NULL"
    )
    row = cur.fetchone()
    regular_expenses = abs(row[1] or 0.0) if row else 0.0
    regular_income = row[2] or 0.0 if row else 0.0
    regular_count = row[0] or 0 if row else 0
    
    # Calculate expenses from recurring transactions
    cur = db_conn.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), "
        "SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) "
        "FROM transactions WHERE recurrence_id IS NOT NULL"
    )
    row = cur.fetchone()
    recurring_expenses = abs(row[1] or 0.0) if row else 0.0
    recurring_income = row[2] or 0.0 if row else 0.0
    recurring_count = row[0] or 0 if row else 0
    
    # Total everything
    stats["transactions_count"] = regular_count + recurring_count
    stats["total_expenses"] = regular_expenses + recurring_expenses
    stats["total_income"] = regular_income + recurring_income
    cur.close()
    return templates.TemplateResponse("pages/index.html", {"request": request, "stats": stats})


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request, 
    db_conn: sqlite3.Connection = Depends(get_db_conn),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
) -> HTMLResponse:
    """Transactions page with pagination only."""
    
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Get total count for pagination
    count_result = db_conn.execute(
        "SELECT COUNT(*) as total FROM transactions t "
        "WHERE t.recurrence_id IS NULL AND t.amount < 0"
    ).fetchone()
    total_transactions = count_result["total"]
    total_pages = (total_transactions + per_page - 1) // per_page
    
    # Get transactions with pagination
    txs = db_conn.execute(
        "SELECT t.id, t.date, t.amount, c.name AS category_name, u.name AS user_name, "
        "a.name AS account_name, t.notes, t.tags, t.category_id, t.user_id, t.account_id "
        "FROM transactions t "
        "JOIN categories c ON t.category_id = c.id "
        "JOIN users u ON t.user_id = u.id "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "WHERE t.recurrence_id IS NULL AND t.amount < 0 "
        "ORDER BY t.date DESC, t.id DESC "
        "LIMIT ? OFFSET ?",
        (per_page, offset)
    ).fetchall()
    
    cats = db_conn.execute(
        "SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute(
        "SELECT id, name FROM accounts ORDER BY name").fetchall()

    return templates.TemplateResponse(
        "pages/transactions.html",
        {
            "request": request, 
            "transactions": txs, 
            "categories": cats, 
            "users": users, 
            "accounts": accs, 
            "today": date.today().isoformat(),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_transactions,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
                "prev_page": page - 1,
                "next_page": page + 1
            }
        },
    )


@router.get("/income", response_class=HTMLResponse)
async def income_page(
    request: Request, 
    db_conn: sqlite3.Connection = Depends(get_db_conn),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
) -> HTMLResponse:
    """Income page with pagination only."""
    
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Get total count for pagination
    count_result = db_conn.execute(
        "SELECT COUNT(*) as total FROM transactions t "
        "WHERE t.recurrence_id IS NULL AND t.amount > 0"
    ).fetchone()
    total_transactions = count_result["total"]
    total_pages = (total_transactions + per_page - 1) // per_page
    
    # Get transactions with pagination
    txs = db_conn.execute(
        "SELECT t.id, t.date, t.amount, c.name AS category_name, u.name AS user_name, "
        "a.name AS account_name, t.notes, t.tags, t.category_id, t.user_id, t.account_id "
        "FROM transactions t "
        "JOIN categories c ON t.category_id = c.id "
        "JOIN users u ON t.user_id = u.id "
        "LEFT JOIN accounts a ON t.account_id = a.id "
        "WHERE t.recurrence_id IS NULL AND t.amount > 0 "
        "ORDER BY t.date DESC, t.id DESC "
        "LIMIT ? OFFSET ?",
        (per_page, offset)
    ).fetchall()
    
    cats = db_conn.execute(
        "SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute(
        "SELECT id, name FROM accounts ORDER BY name").fetchall()

    return templates.TemplateResponse(
        "pages/income.html",
        {
            "request": request, 
            "transactions": txs, 
            "categories": cats, 
            "users": users, 
            "accounts": accs, 
            "today": date.today().isoformat(),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_transactions,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
                "prev_page": page - 1,
                "next_page": page + 1
            }
        },
    )


@router.post("/transactions")
async def create_transaction(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    """HTML form submission (no python-multipart)."""
    from urllib.parse import parse_qs
    body = await request.body()
    form = {k: v[0] if isinstance(v, list) else v for k, v in parse_qs(
        body.decode("utf-8")).items()}
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
            "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, amount_val, category_int, user_int, account_int, notes, tags),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return RedirectResponse(url="/transactions", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/income")
async def create_income(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    """HTML form submission for income (positive amounts)."""
    from urllib.parse import parse_qs
    body = await request.body()
    form = {k: v[0] if isinstance(v, list) else v for k, v in parse_qs(
        body.decode("utf-8")).items()}
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
            "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, amount_val, category_int, user_int, account_int, notes, tags),
        )
        db_conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return RedirectResponse(url="/income", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recurrences", response_class=HTMLResponse)
async def recurrences_page(
    request: Request, 
    db_conn: sqlite3.Connection = Depends(get_db_conn),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
) -> HTMLResponse:
    """Recurrences page with pagination only."""
    
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Get total count for pagination
    count_result = db_conn.execute(
        "SELECT COUNT(*) as total FROM recurrences r"
    ).fetchone()
    total_recurrences = count_result["total"]
    total_pages = (total_recurrences + per_page - 1) // per_page
    
    # Get recurrences with pagination
    recs = db_conn.execute(
        "SELECT r.id, r.name, r.amount, c.name AS category_name, u.name AS user_name, "
        "r.frequency, r.start_date, r.end_date, r.day_of_month, r.weekday, r.active "
        "FROM recurrences r "
        "JOIN categories c ON r.category_id = c.id "
        "JOIN users u ON r.user_id = u.id "
        "ORDER BY r.name "
        "LIMIT ? OFFSET ?",
        (per_page, offset)
    ).fetchall()
    
    cats = db_conn.execute(
        "SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()
    
    return templates.TemplateResponse(
        "pages/recurrences.html",
        {
            "request": request, 
            "recurrences": recs,
            "categories": cats, 
            "users": users,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_recurrences,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
                "prev_page": page - 1,
                "next_page": page + 1
            }
        },
    )


@router.post("/recurrences")
async def create_recurrence(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    """Handle form submission for creating a new recurrence."""
    from urllib.parse import parse_qs
    body = await request.body()
    form = {k: v[0] if isinstance(v, list) else v for k, v in parse_qs(
        body.decode("utf-8")).items()}
    
    try:
        # Extract form data
        name = form.get("name")
        amount = float(form.get("amount", 0))
        # Make amount negative since this is an expense
        amount = -abs(amount)
        category_id = int(form.get("category_id"))
        user_id = int(form.get("user_id"))
        start_date = form.get("start_date")
        frequency = form.get("frequency")
        day_of_month = int(form.get("day_of_month")) if form.get("day_of_month") else None
        weekday = int(form.get("weekday")) if form.get("weekday") else None
        end_date = form.get("end_date") or None
        
        # Insert the recurrence
        cur = db_conn.execute(
            "INSERT INTO recurrences (name, amount, category_id, user_id, start_date, end_date, frequency, day_of_month, weekday, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                amount,
                category_id,
                user_id,
                start_date,
                end_date,
                frequency,
                day_of_month,
                weekday,
                1,  # active
            ),
        )
        db_conn.commit()
        
        # Apply recurring transactions to add the expense to the database
        from ..services.recurrence_service import apply_recurring_transactions
        apply_recurring_transactions()
        
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return RedirectResponse(url="/recurrences", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recurrences/{recurrence_id}/edit-inline", response_class=HTMLResponse)
async def edit_recurrence_inline(
    recurrence_id: int, 
    request: Request, 
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Get edit form for a recurrence."""
    recurrence = db_conn.execute(
        "SELECT r.*, c.name AS category_name, u.name AS user_name "
        "FROM recurrences r "
        "JOIN categories c ON r.category_id = c.id "
        "JOIN users u ON r.user_id = u.id "
        "WHERE r.id = ?", (recurrence_id,)
    ).fetchone()
    
    if not recurrence:
        raise HTTPException(status_code=404, detail="Recurrence not found")
    
    categories = db_conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    
    return templates.TemplateResponse(
        "partials/recurrences/edit_row.html",
        {
            "request": request,
            "recurrence": dict(recurrence),
            "categories": categories,
            "users": users
        }
    )


@router.post("/recurrences/{recurrence_id}/edit-inline", response_class=HTMLResponse)
async def update_recurrence_inline(
    recurrence_id: int,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Update a recurrence."""
    from urllib.parse import parse_qs
    body = await request.body()
    form = {k: v[0] if isinstance(v, list) else v for k, v in parse_qs(
        body.decode("utf-8")).items()}
    
    try:
        # Extract form data
        name = form.get("name")
        amount = float(form.get("amount", 0))
        # Make amount negative since this is an expense
        amount = -abs(amount)
        category_id = int(form.get("category_id"))
        user_id = int(form.get("user_id"))
        start_date = form.get("start_date")
        frequency = form.get("frequency")
        day_of_month = int(form.get("day_of_month")) if form.get("day_of_month") else None
        weekday = int(form.get("weekday")) if form.get("weekday") else None
        end_date = form.get("end_date") or None
        active = 1 if form.get("active") else 0
        
        # Update the recurrence
        db_conn.execute(
            "UPDATE recurrences SET name=?, amount=?, category_id=?, user_id=?, start_date=?, end_date=?, frequency=?, day_of_month=?, weekday=?, active=? WHERE id=?",
            (
                name,
                amount,
                category_id,
                user_id,
                start_date,
                end_date,
                frequency,
                day_of_month,
                weekday,
                active,
                recurrence_id,
            ),
        )
        db_conn.commit()
        
        # Apply recurring transactions to update the database
        from ..services.recurrence_service import apply_recurring_transactions
        apply_recurring_transactions()
        
        # Return the updated row
        recurrence = db_conn.execute(
            "SELECT r.*, c.name AS category_name, u.name AS user_name "
            "FROM recurrences r "
            "JOIN categories c ON r.category_id = c.id "
            "JOIN users u ON r.user_id = u.id "
            "WHERE r.id = ?", (recurrence_id,)
        ).fetchone()
        
        return templates.TemplateResponse(
            "partials/recurrences/row.html",
            {
                "request": request,
                "recurrence": dict(recurrence)
            }
        )
        
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/recurrences/{recurrence_id}/delete-inline", response_class=HTMLResponse)
async def delete_recurrence_inline(
    recurrence_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Delete a recurrence."""
    try:
        # Delete all transactions associated with this recurrence
        db_conn.execute("DELETE FROM transactions WHERE recurrence_id = ?", (recurrence_id,))
        
        # Delete the recurrence
        db_conn.execute("DELETE FROM recurrences WHERE id = ?", (recurrence_id,))
        db_conn.commit()
        
        # Return empty response (row will be removed from table)
        return HTMLResponse("")
        
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/recurrences/{recurrence_id}/row", response_class=HTMLResponse)
async def get_recurrence_row(
    recurrence_id: int,
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Get a single recurrence row for display."""
    recurrence = db_conn.execute(
        "SELECT r.*, c.name AS category_name, u.name AS user_name "
        "FROM recurrences r "
        "JOIN categories c ON r.category_id = c.id "
        "JOIN users u ON r.user_id = u.id "
        "WHERE r.id = ?", (recurrence_id,)
    ).fetchone()
    
    if not recurrence:
        raise HTTPException(status_code=404, detail="Recurrence not found")
    
    return templates.TemplateResponse(
        "partials/recurrences/row.html",
        {
            "request": request,
            "recurrence": dict(recurrence)
        }
    )


@router.get("/backup", response_class=HTMLResponse)
async def backup_page(request: Request) -> HTMLResponse:
    from ..api import backup as backup_mod
    import logging
    logger = logging.getLogger(__name__)

    try:
        backups_model = await backup_mod.api_backup_list()
        raw_backups = backups_model.backups if backups_model is not None else []
    except Exception:
        logger.exception("Failed to fetch backup list for page")
        raw_backups = []

    backups = []
    for b in raw_backups:
        try:
            # support pydantic model attributes or plain dicts with various key names
            file_name = (
                getattr(b, "file_name", None)
                or getattr(b, "file", None)
                or getattr(b, "name", None)
                or (b.get("file_name") if isinstance(b, dict) else None)
                or (b.get("file") if isinstance(b, dict) else None)
                or (b.get("name") if isinstance(b, dict) else None)
            )
            created_at = (
                getattr(b, "created_at", None)
                or getattr(b, "created", None)
                or (b.get("created_at") if isinstance(b, dict) else None)
                or (b.get("created") if isinstance(b, dict) else None)
            )
            size = (
                getattr(b, "size", None)
                or (b.get("size") if isinstance(b, dict) else None)
            )

            # if metadata missing, try to stat the file in BACKUP_DIR
            if (created_at in (None, "")) and file_name:
                try:
                    p = backup_mod.BACKUP_DIR / file_name
                    if p.exists():
                        created_at = datetime.fromtimestamp(p.stat().st_mtime).isoformat()
                        size = p.stat().st_size if size in (None, 0) else size
                except Exception:
                    logger.debug("Cannot stat backup file %s", file_name, exc_info=True)

            backups.append({
                "file_name": file_name or "",
                "created_at": created_at or "",
                "size": int(size or 0),
            })
        except Exception:
            logger.exception("Failed to normalize backup item")
            continue

    return templates.TemplateResponse("pages/backup.html", {"request": request, "backups": backups})


@router.post("/backup/create")
async def backup_create(db_conn: sqlite3.Connection = Depends(get_db_conn)) -> RedirectResponse:
    from ..api import backup as backup_mod
    # pass DB connection to the create function so the service can query transactions
    try:
        path = backup_mod.create_backup(db_conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return RedirectResponse(url="/backup", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/backup/restore/{file_name}")
async def backup_restore_file(file_name: str) -> RedirectResponse:
    from ..api import backup as backup_mod
    file_path = backup_mod.BACKUP_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        backup_mod.restore_from_backup(file_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/backup", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/backup/download/{file_name}")
async def backup_download(file_name: str) -> FileResponse:
    from ..api import backup as backup_mod
    file_path = backup_mod.BACKUP_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(str(file_path), filename=file_name)


@router.get("/statistics", response_class=HTMLResponse)
async def statistics_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    
    # מאתחל נתונים לעמוד סטטיסטיקות
    monthly = db_conn.execute("""
        SELECT strftime('%Y-%m', date) AS ym,
               SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS expenses
        FROM transactions
        WHERE date >= date('now','-5 months','start of month')
        AND recurrence_id IS NULL
        GROUP BY ym
        ORDER BY ym
    """).fetchall()
    
    # Get user expenses for user chart
    users = db_conn.execute("""
        SELECT u.name AS user_name, ABS(SUM(t.amount)) AS total
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NULL
        GROUP BY u.name
        ORDER BY total DESC
    """).fetchall()

    # Get monthly category breakdown for donut chart
    category_monthly_rows = db_conn.execute("""
        SELECT strftime('%Y-%m', t.date) AS month,
               c.name AS category,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS amount
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now','start of month','-5 months')
        AND t.recurrence_id IS NULL
        GROUP BY month, c.name
        ORDER BY month ASC, c.name ASC
    """).fetchall()
    
    # Also get total category breakdown for other charts
    category_total_rows = db_conn.execute("""
        SELECT c.name AS category,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now','start of month','-5 months')
        AND t.recurrence_id IS NULL
        GROUP BY c.name
        ORDER BY c.name
    """).fetchall()
    
    # Get top 5 expenses in last 3 months
    top_expenses = db_conn.execute("""
        SELECT 
            t.id,
            t.date,
            t.amount,
            t.notes,
            c.name AS category,
            u.name AS user_name,
            a.name AS account_name
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.date >= date('now', '-3 months')
        AND t.amount < 0  -- רק הוצאות (סכומים שליליים)
        AND t.recurrence_id IS NULL
        ORDER BY ABS(t.amount) DESC
        LIMIT 5
    """).fetchall()
    
    # הוצאות קבועות לפי חודש (כמו MONTHLY)
    recurring_monthly = db_conn.execute("""
        SELECT strftime('%Y-%m', t.date) AS month,
               ABS(SUM(t.amount)) AS total
        FROM transactions t
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NOT NULL
        GROUP BY strftime('%Y-%m', t.date)
        ORDER BY month ASC
    """).fetchall()
    
    template_data = {
        "request": request,
        "monthly_expenses": [dict(r) for r in (monthly or [])],
        "user_expenses": [dict(r) for r in (users or [])],
        "recurring_user_expenses": [dict(r) for r in (recurring_monthly or [])],
        "category_expenses": [dict(r) for r in (category_monthly_rows or [])],
        "category_totals": [dict(r) for r in (category_total_rows or [])],
        "top_expenses": [dict(r) for r in (top_expenses or [])],  # *** ADDED THIS! ***
    }
    
    return templates.TemplateResponse("pages/statistics.html", template_data)


def _find_db_file() -> Optional[FSPath]:
	# mirror logic used by backup_service
	candidates = [
		os.getenv("COUPLEBUDGET_DB"),
		"data.db", "couplebudget.db", "db.sqlite3", "app.db", "database.db"
	]
	root_dir = FSPath(__file__).resolve().parents[3]  # .../expense_tracker/app
	for c in candidates:
		if not c:
			continue
		p = FSPath(c) if FSPath(c).is_absolute() else root_dir / c
		if p.exists():
			return p
	return None

def _open_conn() -> sqlite3.Connection:
	db_path = _find_db_file()
	if not db_path:
		raise RuntimeError("DB file not found")
	conn = sqlite3.connect(str(db_path))
	conn.row_factory = sqlite3.Row
	return conn

@router.get("/statistics/category")
async def statistics_category(months: Optional[str] = Query(default=None)) -> List[Dict]:
	"""
	Return aggregated expenses by category with per-month breakdown.
	Params:
	- months: optional CSV of YYYY-MM values to filter on.
	Response items: { month: 'YYYY-MM', category: 'Name', amount: number }
	"""
	try:
		conn = _open_conn()
		params: list = []
		where = ""
		if months:
			parts = [m.strip() for m in months.split(",") if m.strip()]
			if parts:
				where = f" AND strftime('%Y-%m', t.date) IN ({','.join(['?']*len(parts))})"
				params.extend(parts)
		sql = f"""
			SELECT strftime('%Y-%m', t.date) AS month,
			       COALESCE(c.name, 'אחר') AS category,
			       SUM(t.amount) AS amount
			FROM transactions t
			LEFT JOIN categories c ON t.category_id = c.id
			WHERE t.recurrence_id IS NULL {where}
			GROUP BY month, category
			ORDER BY month ASC, category ASC
		"""
		rows = conn.execute(sql, params).fetchall()
		return [{"month": r["month"], "category": r["category"], "amount": float(r["amount"] or 0)} for r in rows]
	except Exception as exc:
		raise HTTPException(status_code=500, detail=str(exc))
	finally:
		try:
			conn.close()
		except Exception:
			pass


@router.get("/challenges", response_class=HTMLResponse)
async def challenges_page(
    request: Request, 
    db_conn: sqlite3.Connection = Depends(get_db_conn),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=50, description="Items per page"),
    sort_by: str = Query("start_date", description="Sort by column"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)")
) -> HTMLResponse:
    """Challenges page with user progress and level system."""
    # Get user ID (for now, using user 1)
    user_id = 1
    
    # Validate sort_by parameter for challenge history
    valid_sort_columns = ["start_date", "challenge_name", "status", "points_earned"]
    if sort_by not in valid_sort_columns:
        sort_by = "start_date"
    
    # Validate sort_order parameter
    if sort_order not in ["asc", "desc"]:
        sort_order = "desc"
    
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Get user points and level
    points_row = db_conn.execute("""
        SELECT * FROM user_points WHERE user_id = ?
    """, (user_id,)).fetchone()
    
    if not points_row:
        # Create user points record if doesn't exist
        db_conn.execute("""
            INSERT INTO user_points (user_id, total_points, current_level, level_progress)
            VALUES (?, 0, 'bronze', 0)
        """, (user_id,))
        db_conn.commit()
        
        points_info = {
            "total_points": 0,
            "current_level": "bronze",
            "level_progress": 0,
            "next_level": "silver",
            "points_to_next": 100
        }
    else:
        total_points = points_row["total_points"]
        current_level = points_row["current_level"]
        
        # Calculate level progress
        level_thresholds = {
            "bronze": 0,
            "silver": 100,
            "gold": 300,
            "platinum": 600,
            "master": 1000
        }
        
        current_threshold = level_thresholds.get(current_level, 0)
        next_level = "master"
        points_to_next = 0
        
        for level, threshold in level_thresholds.items():
            if threshold > total_points:
                next_level = level
                points_to_next = threshold - total_points
                break
        
        level_progress = 0
        if current_level != "master":
            level_progress = ((total_points - current_threshold) / (level_thresholds[next_level] - current_threshold)) * 100
        
        points_info = {
            "total_points": total_points,
            "current_level": current_level,
            "level_progress": round(level_progress, 1),
            "next_level": next_level,
            "points_to_next": points_to_next
        }
    
    # Get all challenges with user progress
    challenges = db_conn.execute("""
        SELECT * FROM challenges WHERE is_active = 1
    """).fetchall()
    
    challenges_with_progress = []
    for challenge_row in challenges:
        challenge = dict(challenge_row)
        
        # Get user's active challenge for this challenge type
        user_challenge_row = db_conn.execute("""
            SELECT * FROM user_challenges 
            WHERE user_id = ? AND challenge_id = ? AND status = 'active'
            ORDER BY start_date DESC LIMIT 1
        """, (user_id, challenge["id"])).fetchone()
        
        user_challenge = None
        progress_percentage = 0
        days_remaining = 0
        is_completed = False
        is_failed = False
        
        if user_challenge_row:
            user_challenge = dict(user_challenge_row)
            
            # Calculate progress
            if challenge["target_value"] > 0:
                progress_percentage = min(100, (user_challenge["current_progress"] / challenge["target_value"]) * 100)
            else:
                # For "no spending" challenges, progress is based on days completed
                from datetime import datetime, date
                start_date = datetime.strptime(user_challenge["start_date"], "%Y-%m-%d").date()
                end_date = datetime.strptime(user_challenge["end_date"], "%Y-%m-%d").date()
                today = date.today()
                
                total_days = (end_date - start_date).days
                days_completed = (today - start_date).days
                
                if total_days > 0:
                    progress_percentage = min(100, (days_completed / total_days) * 100)
                
                days_remaining = max(0, (end_date - today).days)
                
                # Check if completed or failed
                if today >= end_date:
                    if user_challenge["current_progress"] == 0:  # No violations
                        is_completed = True
                    else:
                        is_failed = True
        
        challenges_with_progress.append({
            **challenge,
            "user_challenge": user_challenge,
            "progress_percentage": progress_percentage,
            "days_remaining": days_remaining,
            "is_completed": is_completed,
            "is_failed": is_failed
        })
    
    # Get total count for challenge history pagination
    count_result = db_conn.execute("""
        SELECT COUNT(*) as total FROM user_challenges uc
        JOIN challenges c ON uc.challenge_id = c.id
        WHERE uc.user_id = ?
    """, (user_id,)).fetchone()
    total_history = count_result["total"]
    total_pages = (total_history + per_page - 1) // per_page
    
    # Build the ORDER BY clause for challenge history
    order_clause = f"ORDER BY {sort_by} {sort_order.upper()}"
    if sort_by == "start_date":
        order_clause += ", uc.id DESC"  # Secondary sort for consistent ordering
    
    # Get challenge history with pagination and sorting
    history = db_conn.execute(f"""
        SELECT 
            c.name as challenge_name,
            uc.start_date,
            uc.status,
            uc.points_earned
        FROM user_challenges uc
        JOIN challenges c ON uc.challenge_id = c.id
        WHERE uc.user_id = ?
        {order_clause}
        LIMIT ? OFFSET ?
    """, (user_id, per_page, offset)).fetchall()
    
    return templates.TemplateResponse("pages/challenges.html", {
        "request": request,
        "challenges": challenges_with_progress,
        "challenge_history": [dict(r) for r in history],
        "user_level": points_info["current_level"],
        "total_points": points_info["total_points"],
        "level_progress": points_info["level_progress"],
        "points_to_next": points_info["points_to_next"],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_history,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1
        },
        "sorting": {
            "sort_by": sort_by,
            "sort_order": sort_order
        }
    })
