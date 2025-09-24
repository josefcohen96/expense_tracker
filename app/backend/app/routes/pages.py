from __future__ import annotations
import sqlite3
from typing import Any, Dict, Optional
from datetime import date, timedelta
from pathlib import Path as FSPath

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from ..db import get_db_conn

# ===== Templates dir (frontend) =====
ROOT_DIR = FSPath(__file__).resolve().parents[3]  # .../expense_tracker/app
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["pages"])

# --------- Helper Functions ---------
async def get_finance_stats(db_conn: sqlite3.Connection) -> Dict[str, float]:
    """Get current month finance statistics for sidebar."""
    try:
        cur = db_conn.execute(
            """
            SELECT 
                SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income
            FROM transactions 
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            """
        )
        stats = cur.fetchone()
        return {
            "total_expenses_month": (stats["total_expenses"] or 0) if stats else 0,
            "total_income_month": (stats["total_income"] or 0) if stats else 0,
        }
    except Exception:
        return {"total_expenses_month": 0, "total_income_month": 0}

# --------- Pages ---------
@router.get("/", response_class=HTMLResponse)
async def index(_: Request) -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

# Service worker at root scope
@router.get("/sw.js")
async def service_worker() -> FileResponse:
    sw_path = STATIC_DIR / "js" / "sw.js"
    if not sw_path.exists():
        # fallback: return empty JS to avoid 404 noise
        from starlette.responses import Response
        return Response("", media_type="application/javascript")
    return FileResponse(str(sw_path), media_type="application/javascript")

# Legacy redirects for removed pages
@router.get("/finances")
async def redirect_finances() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/finances/income")
async def redirect_finances_income() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/finances/recurrences")
async def redirect_finances_recurrences() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/finances/statistics")
async def redirect_finances_statistics() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/finances/backup")
async def redirect_finances_backup() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/income")
async def redirect_income() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/recurrences")
async def redirect_recurrences() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/challenges")
async def redirect_challenges() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/statistics")
async def redirect_statistics() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/backup")
async def redirect_backup() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/transactions")
async def redirect_transactions() -> RedirectResponse:
    return RedirectResponse(url="/finances/transactions", status_code=status.HTTP_302_FOUND)

@router.get("/finances/transactions", response_class=HTMLResponse)
async def finances_transactions_page(
    request: Request, 
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category_id: Optional[str] = Query(None, description="Filter by category"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    account_id: Optional[str] = Query(None, description="Filter by account"),
    date_from: Optional[str] = Query(None, description="Filter from date"),
    date_to: Optional[str] = Query(None, description="Filter to date"),
    month: Optional[str] = Query(None, description="Filter by month YYYY-MM"),
    amount_min: Optional[str] = Query(None, description="Minimum amount"),
    amount_max: Optional[str] = Query(None, description="Maximum amount"),
    transaction_type: Optional[str] = Query(None, description="Transaction type: income or expense"),
    tags: Optional[str] = Query(None, description="Filter by tags"),
    sort: Optional[str] = Query("date_desc", description="Sort order"),
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Transactions page with pagination and filtering."""
    offset = (page - 1) * per_page

    # Compute effective month date range if no explicit range is provided
    effective_date_from = None
    effective_date_to = None
    if not (date_from and date_from.strip()) and not (date_to and date_to.strip()):
        try:
            if month and len(month) == 7 and month[4] == '-':
                y, m = month.split('-')
                year, mon = int(y), int(m)
                start_of_month = date(year, mon, 1)
                next_month_first = date(year + (1 if mon == 12 else 0), 1 if mon == 12 else mon + 1, 1)
            else:
                today = date.today()
                start_of_month = today.replace(day=1)
                next_month_first = date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
            end_of_month = next_month_first - timedelta(days=1)
            effective_date_from = start_of_month.isoformat()
            effective_date_to = end_of_month.isoformat()
        except Exception:
            today = date.today()
            start_of_month = today.replace(day=1)
            next_month_first = date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
            end_of_month = next_month_first - timedelta(days=1)
            effective_date_from = start_of_month.isoformat()
            effective_date_to = end_of_month.isoformat()
    else:
        effective_date_from = date_from
        effective_date_to = date_to

    # Build WHERE clause for filtering
    where_clause = "WHERE t.recurrence_id IS NULL AND t.amount < 0"
    params: list[Any] = []

    # Handle transaction type filter
    if transaction_type and transaction_type.strip():
        if transaction_type == "income":
            where_clause = "WHERE t.recurrence_id IS NULL AND t.amount > 0"
        elif transaction_type == "expense":
            where_clause = "WHERE t.recurrence_id IS NULL AND t.amount < 0"

    if category_id and category_id.strip():
        try:
            category_id_int = int(category_id)
            where_clause += " AND t.category_id = ?"
            params.append(category_id_int)
        except ValueError:
            pass

    if user_id and user_id.strip():
        try:
            user_id_int = int(user_id)
            where_clause += " AND t.user_id = ?"
            params.append(user_id_int)
        except ValueError:
            pass

    if account_id and account_id.strip():
        try:
            account_id_int = int(account_id)
            where_clause += " AND t.account_id = ?"
            params.append(account_id_int)
        except ValueError:
            pass

    if effective_date_from and effective_date_from.strip():
        where_clause += " AND t.date >= ?"
        params.append(effective_date_from)

    if effective_date_to and effective_date_to.strip():
        where_clause += " AND t.date <= ?"
        params.append(effective_date_to)

    if amount_min and amount_min.strip():
        try:
            amount_min_float = float(amount_min)
            where_clause += " AND ABS(t.amount) >= ?"
            params.append(abs(amount_min_float))
        except ValueError:
            pass

    if amount_max and amount_max.strip():
        try:
            amount_max_float = float(amount_max)
            where_clause += " AND ABS(t.amount) <= ?"
            params.append(abs(amount_max_float))
        except ValueError:
            pass

    if tags and tags.strip():
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        if tag_list:
            where_clause += " AND (" + " OR ".join(["t.tags LIKE ?"] * len(tag_list)) + ")"
            params.extend([f"%{tag}%" for tag in tag_list])

    # Get total count
    count_query = f"SELECT COUNT(*) FROM transactions t {where_clause}"
    cur = db_conn.execute(count_query, params)
    total = cur.fetchone()[0]

    # Build ORDER BY clause
    order_clause = "ORDER BY "
    if sort == "date_asc":
        order_clause += "t.date ASC, t.id ASC"
    elif sort == "amount_desc":
        order_clause += "ABS(t.amount) DESC, t.date DESC"
    elif sort == "amount_asc":
        order_clause += "ABS(t.amount) ASC, t.date DESC"
    else:  # date_desc (default)
        order_clause += "t.date DESC, t.id DESC"

    # Get transactions
    query = f"""
        SELECT t.id, t.date, t.amount, c.name as category, u.name as user, 
               a.name as account, t.notes, t.tags, t.recurrence_id
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        {where_clause}
        {order_clause}
        LIMIT ? OFFSET ?
    """
    cur = db_conn.execute(query, params + [per_page, offset])
    transactions = cur.fetchall()

    # Get only expense categories (excluding income categories)
    cur = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name")
    categories = cur.fetchall()

    # Get users and accounts for form
    cur = db_conn.execute("SELECT id, name FROM users ORDER BY name")
    users = cur.fetchall()

    cur = db_conn.execute("SELECT id, name FROM accounts ORDER BY name")
    accounts = cur.fetchall()

    # Get sidebar stats
    sidebar_stats = await get_finance_stats(db_conn)

    return templates.TemplateResponse("finances/transactions.html", {
        "request": request,
        "show_sidebar": True,
        "transactions": transactions,
        "categories": categories,
        "users": users,
        "accounts": accounts,
        "effective_date_from": effective_date_from,
        "effective_date_to": effective_date_to,
        "current_month": (month or date.today().strftime('%Y-%m')),
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
            "has_prev": page > 1,
            "has_next": page < (total + per_page - 1) // per_page,
            "prev_page": page - 1,
            "next_page": page + 1
        },
        **sidebar_stats
    })
