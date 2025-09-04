from __future__ import annotations
import os
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path as FSPath
from datetime import date
from datetime import timedelta

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

# --------- Helper Functions ---------

async def get_finance_stats(db_conn: sqlite3.Connection) -> Dict[str, float]:
    """Get current month finance statistics for sidebar."""
    try:
        # Get current month regular expenses and income from transactions
        cur = db_conn.execute("""
            SELECT 
                SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income
            FROM transactions 
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        """)
        stats = cur.fetchone()
        
        regular_expenses = stats['total_expenses'] or 0
        total_income = stats['total_income'] or 0
        
        # Get current month recurring expenses
        cur = db_conn.execute("""
            SELECT SUM(amount) as total_recurring_expenses
            FROM recurrences 
            WHERE active = 1 
            AND (
                (frequency = 'monthly' AND start_date <= date('now', 'start of month', '+1 month', '-1 day'))
                OR (frequency = 'weekly' AND start_date <= date('now', 'start of month', '+1 month', '-1 day'))
                OR (frequency = 'daily' AND start_date <= date('now', 'start of month', '+1 month', '-1 day'))
            )
        """)
        recurring_stats = cur.fetchone()
        
        recurring_expenses = recurring_stats['total_recurring_expenses'] or 0
        
        # Total expenses = regular + recurring
        total_expenses = regular_expenses + recurring_expenses
        
        return {
            "total_expenses_month": total_expenses,
            "total_income_month": total_income
        }
    except Exception as e:
        print(f"Error getting finance stats: {e}")
        return {
            "total_expenses_month": 0,
            "total_income_month": 0
        }

# --------- Pages ---------


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Home page with overview of all sections."""
    return templates.TemplateResponse("pages/index.html", {"request": request})

@router.get("/finances", response_class=HTMLResponse)
async def finances_dashboard(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Finances dashboard page."""
    # Get basic stats
    cur = db_conn.execute("""
        SELECT 
            COUNT(*) as total_transactions,
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income
        FROM transactions 
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
    """)
    stats = cur.fetchone()
    
    # Get recent transactions
    cur = db_conn.execute("""
        SELECT t.id, t.date, t.amount, c.name as category, u.name as user, 
               a.name as account, t.notes, t.tags
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        ORDER BY t.date DESC, t.id DESC
        LIMIT 5
    """)
    recent_transactions = cur.fetchall()
    
    # Get recurrences count
    cur = db_conn.execute("SELECT COUNT(*) FROM recurrences WHERE active = 1")
    recurrences_count = cur.fetchone()[0]
    
    stats_data = {
        "total_expenses": stats['total_expenses'] or 0,
        "total_income": stats['total_income'] or 0,
        "transactions_count": stats['total_transactions'] or 0,
        "recurrences_count": recurrences_count
    }
    
    # Get sidebar stats
    sidebar_stats = await get_finance_stats(db_conn)
    
    return templates.TemplateResponse("finances/index.html", {
        "request": request,
        "show_sidebar": True,
        "stats": stats_data,
        "recent_transactions": recent_transactions,
        **sidebar_stats
    })

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
            # Fallback to current month on any parsing error
            today = date.today()
            start_of_month = today.replace(day=1)
            next_month_first = date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
            end_of_month = next_month_first - timedelta(days=1)
            effective_date_from = start_of_month.isoformat()
            effective_date_to = end_of_month.isoformat()
    else:
        # Use explicit dates if provided
        effective_date_from = date_from
        effective_date_to = date_to
    
    # Build WHERE clause for filtering
    where_clause = "WHERE t.recurrence_id IS NULL AND t.amount < 0"
    params = []
    
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
        # Split tags by comma and search for any of them
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        if tag_list:
            where_clause += " AND ("
            tag_conditions = []
            for tag in tag_list:
                tag_conditions.append("t.tags LIKE ?")
                params.append(f"%{tag}%")
            where_clause += " OR ".join(tag_conditions) + ")"
    
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

@router.get("/finances/recurrences", response_class=HTMLResponse)
async def finances_recurrences_page(
    request: Request, 
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    user_id: Optional[int] = Query(None, description="Filter by user"),
    frequency: Optional[str] = Query(None, description="Filter by frequency"),
    status: Optional[str] = Query(None, description="Filter by status"),
    month: Optional[str] = Query(None, description="Filter by month YYYY-MM (active in month)"),
    sort: Optional[str] = Query("name_asc", description="Sort order"),
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    """Recurrences page with pagination and filtering."""
    offset = (page - 1) * per_page
    
    # Build WHERE clause for filtering
    where_clause = "WHERE 1=1"
    params = []
    
    if category_id:
        where_clause += " AND r.category_id = ?"
        params.append(category_id)
    
    if user_id:
        where_clause += " AND r.user_id = ?"
        params.append(user_id)
    
    if frequency:
        where_clause += " AND r.frequency = ?"
        params.append(frequency)
    
    if status:
        if status == "active":
            where_clause += " AND r.active = 1"
        elif status == "inactive":
            where_clause += " AND r.active = 0"

    # Apply month filter: show recurrences that are active during the selected month
    # Default to current month if not provided
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
        where_clause += " AND date(r.start_date) <= date(?) AND (r.end_date IS NULL OR date(r.end_date) >= date(?))"
        params.extend([end_of_month.isoformat(), start_of_month.isoformat()])
    except Exception:
        # If parsing fails, skip month filter
        pass
    
    # Get total count
    count_query = f"SELECT COUNT(*) FROM recurrences r {where_clause}"
    cur = db_conn.execute(count_query, params)
    total = cur.fetchone()[0]
    
    # Build ORDER BY clause
    order_clause = "ORDER BY "
    if sort == "name_asc":
        order_clause += "r.name ASC"
    elif sort == "name_desc":
        order_clause += "r.name DESC"
    elif sort == "amount_desc":
        order_clause += "r.amount DESC"
    elif sort == "amount_asc":
        order_clause += "r.amount ASC"
    elif sort == "start_date_desc":
        order_clause += "r.start_date DESC"
    elif sort == "start_date_asc":
        order_clause += "r.start_date ASC"
    else:
        order_clause += "r.name ASC"
    
    # Get recurrences
    query = f"""
        SELECT r.id, r.name, r.amount, c.name as category, u.name as user,
               r.frequency, r.start_date, r.end_date, r.day_of_month, 
               r.weekday, r.active
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        {where_clause}
        {order_clause}
        LIMIT ? OFFSET ?
    """
    cur = db_conn.execute(query, params + [per_page, offset])
    recurrences = cur.fetchall()
    
    # Get only expense categories (excluding income categories)
    cur = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name")
    categories = cur.fetchall()
    
    # Get users for form
    cur = db_conn.execute("SELECT id, name FROM users ORDER BY name")
    users = cur.fetchall()
    
    # Get sidebar stats
    sidebar_stats = await get_finance_stats(db_conn)
    
    return templates.TemplateResponse("finances/recurrences.html", {
        "request": request,
        "show_sidebar": True,
        "recurrences": recurrences,
        "categories": categories,
        "users": users,
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

@router.get("/finances/income", response_class=HTMLResponse)
async def finances_income_page(
    request: Request, 
    db_conn: sqlite3.Connection = Depends(get_db_conn),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    category_id: Optional[str] = Query(None, description="Filter by category"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    account_id: Optional[str] = Query(None, description="Filter by account"),
    date_from: Optional[str] = Query(None, description="Filter from date"),
    date_to: Optional[str] = Query(None, description="Filter to date"),
    amount_min: Optional[str] = Query(None, description="Minimum amount"),
    amount_max: Optional[str] = Query(None, description="Maximum amount"),
    tags: Optional[str] = Query(None, description="Filter by tags"),
    month: Optional[str] = Query(None, description="Filter by month YYYY-MM"),
    sort: Optional[str] = Query("date_desc", description="Sort order")
) -> HTMLResponse:
    """Income management page with pagination."""
    
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Build WHERE clause for filtering
    where_clause = "WHERE t.recurrence_id IS NULL AND t.amount > 0"
    params = []

    # Default to current month if no date range provided
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
            where_clause += " AND t.amount >= ?"
            params.append(amount_min_float)
        except ValueError:
            pass
    
    if amount_max and amount_max.strip():
        try:
            amount_max_float = float(amount_max)
            where_clause += " AND t.amount <= ?"
            params.append(amount_max_float)
        except ValueError:
            pass
    
    if tags and tags.strip():
        # Split tags by comma and search for any of them
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        if tag_list:
            where_clause += " AND ("
            tag_conditions = []
            for tag in tag_list:
                tag_conditions.append("t.tags LIKE ?")
                params.append(f"%{tag}%")
            where_clause += " OR ".join(tag_conditions) + ")"
    
    # Get total count for pagination
    count_query = f"SELECT COUNT(*) as total FROM transactions t {where_clause}"
    cur = db_conn.execute(count_query, params)
    total_transactions = cur.fetchone()[0]
    total_pages = (total_transactions + per_page - 1) // per_page
    
    # Build ORDER BY clause
    order_clause = "ORDER BY "
    if sort == "date_asc":
        order_clause += "t.date ASC, t.id ASC"
    elif sort == "date_desc":
        order_clause += "t.date DESC, t.id DESC"
    elif sort == "amount_desc":
        order_clause += "t.amount DESC"
    elif sort == "amount_asc":
        order_clause += "t.amount ASC"
    else:
        order_clause += "t.date DESC, t.id DESC"
    
    # Get transactions with pagination
    query = f"""
        SELECT t.id, t.date, t.amount, c.name AS category_name, u.name AS user_name, 
               a.name AS account_name, t.notes, t.tags, t.category_id, t.user_id, t.account_id 
        FROM transactions t 
        JOIN categories c ON t.category_id = c.id 
        JOIN users u ON t.user_id = u.id 
        LEFT JOIN accounts a ON t.account_id = a.id 
        {where_clause}
        {order_clause}
        LIMIT ? OFFSET ?
    """
    cur = db_conn.execute(query, params + [per_page, offset])
    txs = cur.fetchall()
    
    # Get only income categories (clinic and salary)
    cats = db_conn.execute(
        "SELECT id, name FROM categories WHERE name IN ('קליניקה', 'משכורת') ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()
    accounts = db_conn.execute(
        "SELECT id, name FROM accounts ORDER BY name").fetchall()

    # Get sidebar stats
    sidebar_stats = await get_finance_stats(db_conn)
    
    return templates.TemplateResponse(
        "finances/income.html",
        {
            "request": request,
            "show_sidebar": True,
            "transactions": txs, 
            "categories": cats, 
            "users": users,
            "accounts": accounts,
            "today": date.today().isoformat(),
            "effective_date_from": effective_date_from,
            "effective_date_to": effective_date_to,
            "current_month": (month or date.today().strftime('%Y-%m')),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_transactions,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
                "prev_page": page - 1,
                "next_page": page + 1
            },
            **sidebar_stats
        },
    )

@router.get("/api/health")
async def health_check():
    """Health check endpoint for service worker."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@router.get("/finances/statistics", response_class=HTMLResponse)
async def finances_statistics_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Statistics page with full data."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("=== FINANCES STATISTICS PAGE REQUEST START ===")
    
    # מאתחל נתונים לעמוד סטטיסטיקות (including both regular and recurring expenses, excluding income categories)
    try:
        monthly = db_conn.execute("""
            SELECT strftime('%Y-%m', date) AS ym,
                   SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS expenses
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now','-5 months','start of month')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            GROUP BY ym
            ORDER BY ym
        """).fetchall()
        
        # Debug: Check the actual data
        logger.info("=== MONTHLY EXPENSES QUERY DEBUG ===")
        logger.info(f"Monthly expenses query result: {monthly}")
        if monthly:
            for row in monthly:
                logger.info(f"Month: {row.get('ym', 'N/A')}, Expenses: {row.get('expenses', 'N/A')}")
        
        # Also check the total for current month
        current_month_total = db_conn.execute("""
            SELECT SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
        logger.info(f"Current month total expenses: {current_month_total[0] if current_month_total else 'N/A'}")
        
    except Exception as e:
        monthly = []
        logger.error(f"Error in monthly expenses query: {e}")
    
    # Get user expenses for user chart (only regular expenses, excluding recurring expenses and income categories)
    try:
        users = db_conn.execute("""
            SELECT u.name AS user_name, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
            FROM transactions t
            JOIN users u ON t.user_id = u.id
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now', '-6 months')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            AND t.recurrence_id IS NULL
            GROUP BY u.name
            ORDER BY total DESC
        """).fetchall()
    except Exception as e:
        users = []
    
    # Get monthly category breakdown for donut chart (only regular expenses, excluding recurring expenses, even with 0 amounts)
    try:
        category_monthly_rows = db_conn.execute("""
            SELECT ym.month,
                   c.name AS category,
                   COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS amount
            FROM (
                SELECT DISTINCT strftime('%Y-%m', date) AS month
                FROM transactions
                WHERE date >= date('now','start of month','-5 months')
                UNION
                SELECT strftime('%Y-%m', 'now') AS month
            ) ym
            CROSS JOIN categories c
            LEFT JOIN transactions t ON c.id = t.category_id 
                AND strftime('%Y-%m', t.date) = ym.month
                AND t.recurrence_id IS NULL
            WHERE c.name NOT IN ('משכורת', 'קליניקה')
            GROUP BY ym.month, c.id, c.name
            ORDER BY ym.month ASC, c.name ASC
        """).fetchall()
    except Exception as e:
        category_monthly_rows = []
    
    # Also get total category breakdown for other charts (only regular expenses, excluding recurring expenses, even with 0 amounts)
    try:
        category_total_rows = db_conn.execute("""
            SELECT c.name AS category,
                   COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
            FROM categories c
            LEFT JOIN transactions t ON c.id = t.category_id 
                AND t.date >= date('now','start of month','-5 months')
                AND t.recurrence_id IS NULL
            WHERE c.name NOT IN ('משכורת', 'קליניקה')
            GROUP BY c.id, c.name
            ORDER BY c.name
        """).fetchall()
    except Exception as e:
        category_total_rows = []
    
    # Get cash vs credit breakdown for last 6 months (including both regular and recurring expenses, excluding income categories)
    # First get by user and account
    try:
        cash_vs_credit_by_user = db_conn.execute("""
            SELECT strftime('%Y-%m', t.date) AS month,
                   u.name AS user_name,
                   COALESCE(a.name, 'לא מוגדר') AS account_type,
                   SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS total
            FROM transactions t
            LEFT JOIN accounts a ON t.account_id = a.id
            JOIN categories c ON t.category_id = c.id
            JOIN users u ON t.user_id = u.id
            WHERE t.date >= date('now','start of month','-6 months')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            GROUP BY month, u.name, a.name
            ORDER BY month ASC, u.name ASC, a.name ASC
        """).fetchall()
    except Exception as e:
        cash_vs_credit_by_user = []
    
    # Then get totals by account (all users combined)
    try:
        cash_vs_credit_totals = db_conn.execute("""
            SELECT strftime('%Y-%m', t.date) AS month,
                   COALESCE(a.name, 'לא מוגדר') AS account_type,
                   SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS total
            FROM transactions t
            LEFT JOIN accounts a ON t.account_id = a.id
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now','start of month','-6 months')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            GROUP BY month, a.name
            ORDER BY month ASC, a.name ASC
        """).fetchall()
    except Exception as e:
        cash_vs_credit_totals = []
    
    # Combine both results
    cash_vs_credit = []
    
    try:
        # Create user data with cash and credit amounts per month
        user_monthly_data = {}
        for row in cash_vs_credit_by_user:
            month = row['month']
            user_name = row['user_name']
            account_type = row['account_type']
            total = row['total']
            
            if month not in user_monthly_data:
                user_monthly_data[month] = {}
            
            if user_name not in user_monthly_data[month]:
                user_monthly_data[month][user_name] = {'cash': 0, 'credit': 0}
            
            if account_type == 'Cash':
                user_monthly_data[month][user_name]['cash'] += total
            elif account_type == 'Credit Card':
                user_monthly_data[month][user_name]['credit'] += total
            # Handle other account types - add to credit by default
            else:
                user_monthly_data[month][user_name]['credit'] += total
    except Exception as e:
        user_monthly_data = {}
    
    try:
        # Add user-specific data (one row per user per month)
        for month, users in user_monthly_data.items():
            for user_name, amounts in users.items():
                total_amount = amounts['cash'] + amounts['credit']
                cash_vs_credit.append({
                    'month': month,
                    'user_name': user_name,
                    'account_type': 'User',
                    'total': total_amount,
                    'cash_amount': amounts['cash'],
                    'credit_amount': amounts['credit'],
                    'is_total': False
                })
        
        # Create combined totals by month (all users and accounts combined)
        monthly_totals = {}
        for row in cash_vs_credit_totals:
            month = row['month']
            if month not in monthly_totals:
                monthly_totals[month] = {'cash': 0, 'credit': 0}
            
            if row['account_type'] == 'Cash':
                monthly_totals[month]['cash'] += row['total']
            elif row['account_type'] == 'Credit Card':
                monthly_totals[month]['credit'] += row['total']
            # Handle other account types - add to credit by default
            else:
                monthly_totals[month]['credit'] += row['total']
        
        # Add combined totals data
        for month, totals in monthly_totals.items():
            total_amount = totals['cash'] + totals['credit']
            cash_vs_credit.append({
                'month': month,
                'user_name': 'סה"כ',
                'account_type': 'Combined',
                'total': total_amount,
                'cash_amount': totals['cash'],
                'credit_amount': totals['credit'],
                'is_total': True
            })
    except Exception as e:
        pass
    
    # Get top 5 expenses in last 3 months (regular expenses only, excluding income categories)
    try:
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
            AND t.recurrence_id IS NULL  -- exclude recurring transactions
            AND c.name NOT IN ('משכורת', 'קליניקה')
            ORDER BY ABS(t.amount) DESC
            LIMIT 5
        """).fetchall()
    except Exception as e:
        top_expenses = []
    
    # הוצאות קבועות לפי חודש (excluding income categories)
    try:
        recurring_monthly = db_conn.execute("""
            SELECT strftime('%Y-%m', t.date) AS month,
                   COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now', '-6 months')
            AND t.recurrence_id IS NOT NULL
            AND c.name NOT IN ('משכורת', 'קליניקה')
            GROUP BY strftime('%Y-%m', t.date)
            ORDER BY month ASC
        """).fetchall()
    except Exception as e:
        recurring_monthly = []
    
    # Ensure database connection has row_factory set
    try:
        if not hasattr(db_conn, 'row_factory') or db_conn.row_factory is None:
            db_conn.row_factory = sqlite3.Row
    except Exception as e:
        pass
    
    # Helper function to safely convert query results to dictionaries
    def safe_dict_convert(row):
        try:
            if hasattr(row, 'keys'):
                return dict(row)
            elif isinstance(row, (list, tuple)):
                # Handle tuple/list results by creating a dict with column names
                return {"value": row[0] if len(row) == 1 else row}
            else:
                return {"value": row}
        except Exception as e:
            return {"value": 0}
    
    # Calculate summary statistics for the current month (including both regular and recurring expenses)
    try:
        current_month_expenses = db_conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        current_month_expenses = {'total': 0}
    
    try:
        previous_month_expenses = db_conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now', '-1 month')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        previous_month_expenses = {'total': 0}
    
    try:
        current_month_income = db_conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        current_month_income = {'total': 0}
    
    # Get transaction count for current month (including both regular and recurring transactions)
    try:
        current_month_transactions = db_conn.execute("""
            SELECT COUNT(*) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        current_month_transactions = {'total': 0}
    
    # Get recurring transactions count for current month
    try:
        current_month_recurring = db_conn.execute("""
            SELECT COUNT(*) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            AND t.recurrence_id IS NOT NULL
        """).fetchone()
    except Exception as e:
        current_month_recurring = {'total': 0}
    
    # Get regular transactions count for current month (excluding recurring transactions)
    try:
        current_month_regular = db_conn.execute("""
            SELECT COUNT(*) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            AND t.recurrence_id IS NULL
        """).fetchone()
    except Exception as e:
        current_month_regular = {'total': 0}
    
    try:
        previous_month_income = db_conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now', '-1 month')
            AND c.name IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        previous_month_income = {'total': 0}
    
    # Get total expenses for last 6 months (including both regular and recurring expenses)
    try:
        total_expenses_6months = db_conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now', '-6 months')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        total_expenses_6months = {'total': 0}
    
    # Calculate changes
    try:
        expenses_change = 0
        if previous_month_expenses['total'] > 0:
            expenses_change = ((current_month_expenses['total'] - previous_month_expenses['total']) / previous_month_expenses['total']) * 100
        
        income_change = 0
        if previous_month_income['total'] > 0:
            income_change = ((current_month_income['total'] - previous_month_income['total']) / previous_month_income['total']) * 100
        
        balance_month = current_month_income['total'] - current_month_expenses['total']
        balance_change = 0
        if (previous_month_income['total'] - previous_month_expenses['total']) > 0:
            balance_change = ((balance_month - (previous_month_income['total'] - previous_month_expenses['total'])) / (previous_month_income['total'] - previous_month_expenses['total'])) * 100
    except Exception as e:
        expenses_change = 0
        income_change = 0
        balance_month = 0
        balance_change = 0
    
    # Count active categories this month
    try:
        categories_count = db_conn.execute("""
            SELECT COUNT(DISTINCT c.id) as count
            FROM categories c
            JOIN transactions t ON c.id = t.category_id
            WHERE strftime('%Y-%m', t.date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        categories_count = {'count': 0}
    
    # Get sidebar stats
    sidebar_stats = await get_finance_stats(db_conn)
    
    try:
        template_data = {
            "request": request,
            "show_sidebar": True,
            "monthly_expenses": [safe_dict_convert(r) for r in (monthly or [])],
            "user_expenses": [safe_dict_convert(r) for r in (users or [])],
            "recurring_user_expenses": [safe_dict_convert(r) for r in (recurring_monthly or [])],
            "category_expenses": [safe_dict_convert(r) for r in (category_monthly_rows or [])],
            "category_totals": [safe_dict_convert(r) for r in (category_total_rows or [])],
            "cash_vs_credit": [safe_dict_convert(r) for r in (cash_vs_credit or [])],
            "top_expenses": [safe_dict_convert(r) for r in (top_expenses or [])],
            "recurring_monthly": [safe_dict_convert(r) for r in (recurring_monthly or [])],
            "total_expenses_month": current_month_expenses['total'],
            "total_income_month": current_month_income['total'],
            "balance_month": balance_month,
            "categories_count": categories_count['count'],
            "expenses_change": expenses_change,
            "income_change": income_change,
            "balance_change": balance_change,
            "total_transactions_month": current_month_transactions['total'],
            "total_recurring_month": current_month_recurring['total'],
            "total_regular_month": current_month_regular['total'],
            "total_expenses_6months": total_expenses_6months['total'],
            **sidebar_stats
        }
    except Exception as e:
        template_data = {
            "request": request,
            "show_sidebar": True,
            "monthly_expenses": [],
            "user_expenses": [],
            "recurring_user_expenses": [],
            "category_expenses": [],
            "category_totals": [],
            "cash_vs_credit": [],
            "top_expenses": [],
            "recurring_monthly": [],
            "total_expenses_month": 0,
            "total_income_month": 0,
            "balance_month": 0,
            "categories_count": 0,
            "expenses_change": 0,
            "income_change": 0,
            "balance_change": 0,
            "total_transactions_month": 0,
            "total_recurring_month": 0,
            "total_regular_month": 0,
            **sidebar_stats
        }
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Error in finances_statistics_page: %s", str(e))
        template_data = {
            "request": request,
            "show_sidebar": True,
            "monthly_expenses": [],
            "user_expenses": [],
            "recurring_user_expenses": [],
            "category_expenses": [],
            "category_totals": [],
            "cash_vs_credit": [],
            "top_expenses": [],
            "recurring_monthly": [],
            "total_expenses_month": 0,
            "total_income_month": 0,
            "balance_month": 0,
            "categories_count": 0,
            "expenses_change": 0,
            "income_change": 0,
            "balance_change": 0,
            "total_transactions_month": 0,
            "total_recurring_month": 0,
            "total_regular_month": 0,
            **sidebar_stats
        }
    
    logger.info("=== FINANCES STATISTICS PAGE REQUEST END ===")
    logger.info(f"Template data keys: {list(template_data.keys())}")
    logger.info(f"Monthly expenses count: {len(template_data.get('monthly_expenses', []))}")
    logger.info(f"Top expenses count: {len(template_data.get('top_expenses', []))}")
    logger.info(f"Total expenses month: {template_data.get('total_expenses_month', 0)}")
    logger.info(f"Total income month: {template_data.get('total_income_month', 0)}")
    logger.info(f"Total transactions month: {template_data.get('total_transactions_month', 0)}")
    logger.info(f"Total recurring month: {template_data.get('total_recurring_month', 0)}")
    logger.info(f"Total regular month: {template_data.get('total_regular_month', 0)}")
    
    return templates.TemplateResponse("finances/statistics.html", template_data)

@router.get("/finances/backup", response_class=HTMLResponse)
async def finances_backup_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Backup page."""
    backups = []
    try:
        import os
        backup_service_path = os.path.join(os.path.dirname(__file__), '..', 'services', 'backup_service.py')
        if os.path.exists(backup_service_path):
            from ..services.backup_service import list_backup_files
            backups = list_backup_files()
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Backup service file not found at: %s", backup_service_path)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Failed to fetch backup list for finances backup page")
        backups = []
    
    # Get sidebar stats
    sidebar_stats = await get_finance_stats(db_conn)
    
    return templates.TemplateResponse("finances/backup.html", {
        "request": request,
        "show_sidebar": True,
        "backups": backups,
        **sidebar_stats
    })

@router.get("/finances/challenges", response_class=HTMLResponse)
async def finances_challenges_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    """Challenges page."""
    # Get sidebar stats
    sidebar_stats = await get_finance_stats(db_conn)
    
    return templates.TemplateResponse("finances/challenges.html", {
        "request": request,
        "show_sidebar": True,
        **sidebar_stats
    })

# New section routes
@router.get("/dreams", response_class=HTMLResponse)
async def dreams_page(request: Request) -> HTMLResponse:
    """Dreams page."""
    return templates.TemplateResponse("dreams/index.html", {"request": request})

@router.get("/goals", response_class=HTMLResponse)
async def goals_page(request: Request) -> HTMLResponse:
    """Goals page."""
    return templates.TemplateResponse("goals/index.html", {"request": request})

@router.get("/memories", response_class=HTMLResponse)
async def memories_page(request: Request) -> HTMLResponse:
    """Memories page."""
    return templates.TemplateResponse("memories/index.html", {"request": request})

@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request) -> HTMLResponse:
    """Calendar page."""
    return templates.TemplateResponse("calendar/index.html", {"request": request})


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request, 
    db_conn: sqlite3.Connection = Depends(get_db_conn),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    category_id: Optional[int] = Query(None, description="Filter by category ID")
) -> HTMLResponse:
    """Transactions page with pagination and filtering."""
    
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Build WHERE clause for filtering
    where_clause = "WHERE t.recurrence_id IS NULL AND t.amount < 0"
    params = []
    
    if category_id:
        where_clause += " AND t.category_id = ?"
        params.append(category_id)
    
    # Get total count for pagination
    count_query = f"SELECT COUNT(*) as total FROM transactions t {where_clause}"
    count_result = db_conn.execute(count_query, params).fetchone()
    total_transactions = count_result["total"]
    total_pages = (total_transactions + per_page - 1) // per_page
    
    # Get transactions with pagination and filtering
    query = f"""
        SELECT t.id, t.date, t.amount, c.name AS category_name, u.name AS user_name, 
        a.name AS account_name, t.notes, t.tags, t.category_id, t.user_id, t.account_id 
        FROM transactions t 
        JOIN categories c ON t.category_id = c.id 
        JOIN users u ON t.user_id = u.id 
        LEFT JOIN accounts a ON t.account_id = a.id 
        {where_clause}
        ORDER BY t.date DESC, t.id DESC 
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, offset])
    txs = db_conn.execute(query, params).fetchall()
    
    # Get only expense categories (excluding income categories)
    cats = db_conn.execute(
        "SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name").fetchall()
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
    
    # Get only income categories (clinic and salary)
    cats = db_conn.execute(
        "SELECT id, name FROM categories WHERE name IN ('קליניקה', 'משכורת') ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()

    return templates.TemplateResponse(
        "pages/income.html",
        {
            "request": request, 
            "transactions": txs, 
            "categories": cats, 
            "users": users, 
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
    notes = form.get("notes") or None
    tags = form.get("tags") or None

    try:
        amount_val = float(amount) if amount is not None else 0.0
        # Make amount positive since this is income
        amount_val = abs(amount_val)
        category_int = int(category_id) if category_id is not None else None
        user_int = int(user_id) if user_id is not None else None
        db_conn.execute(
            "INSERT INTO transactions (date, amount, category_id, user_id, notes, tags) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date, amount_val, category_int, user_int, notes, tags),
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
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    category_id: Optional[int] = Query(None, description="Filter by category ID")
) -> HTMLResponse:
    """Recurrences page with pagination and filtering."""
    
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Build WHERE clause for filtering
    where_clause = ""
    params = []
    
    if category_id:
        where_clause = "WHERE r.category_id = ?"
        params.append(category_id)
    
    # Get total count for pagination
    count_query = f"SELECT COUNT(*) as total FROM recurrences r {where_clause}"
    count_result = db_conn.execute(count_query, params).fetchone()
    total_recurrences = count_result["total"]
    total_pages = (total_recurrences + per_page - 1) // per_page
    
    # Get recurrences with pagination and filtering
    query = f"""
        SELECT r.id, r.name, r.amount, c.name AS category_name, u.name AS user_name, 
        a.name AS account_name, r.frequency, r.start_date, r.end_date, r.day_of_month, r.weekday, r.active 
        FROM recurrences r 
        JOIN categories c ON r.category_id = c.id 
        JOIN users u ON r.user_id = u.id 
        LEFT JOIN accounts a ON r.account_id = a.id 
        {where_clause}
        ORDER BY r.name 
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, offset])
    recs = db_conn.execute(query, params).fetchall()
    
    # Get only expense categories (excluding income categories)
    cats = db_conn.execute(
        "SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute(
        "SELECT id, name FROM users ORDER BY id").fetchall()
    accs = db_conn.execute(
        "SELECT id, name FROM accounts ORDER BY name").fetchall()
    
    return templates.TemplateResponse(
        "pages/recurrences.html",
        {
            "request": request, 
            "recurrences": recs,
            "categories": cats, 
            "users": users,
            "accounts": accs,
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
        account_id = int(form.get("account_id")) if form.get("account_id") else None
        start_date = form.get("start_date")
        frequency = form.get("frequency")
        day_of_month = int(form.get("day_of_month")) if form.get("day_of_month") else None
        weekday = int(form.get("weekday")) if form.get("weekday") else None
        end_date = form.get("end_date") or None
        
        # Insert the recurrence
        cur = db_conn.execute(
            "INSERT INTO recurrences (name, amount, category_id, user_id, account_id, start_date, end_date, frequency, day_of_month, weekday, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                amount,
                category_id,
                user_id,
                account_id,
                start_date,
                end_date,
                frequency,
                day_of_month,
                weekday,
                1,  # active
            ),
        )
        db_conn.commit()
        
        # Apply recurring transactions using existing recurrence module (best-effort)
        from .. import recurrence as recurrence_mod
        try:
            recurrence_mod.apply_recurring()
        except Exception:
            # Non-fatal: creation committed; scheduler application can be run later
            pass
        
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
        "SELECT r.*, c.name AS category_name, u.name AS user_name, a.name AS account_name "
        "FROM recurrences r "
        "JOIN categories c ON r.category_id = c.id "
        "JOIN users u ON r.user_id = u.id "
        "LEFT JOIN accounts a ON r.account_id = a.id "
        "WHERE r.id = ?", (recurrence_id,)
    ).fetchone()
    
    if not recurrence:
        raise HTTPException(status_code=404, detail="Recurrence not found")
    
    # Get only expense categories (excluding income categories)
    categories = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    
    return templates.TemplateResponse(
        "partials/recurrences/edit_row.html",
        {
            "request": request,
            "recurrence": dict(recurrence),
            "categories": categories,
            "users": users,
            "accounts": accounts
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
        account_id = int(form.get("account_id")) if form.get("account_id") else None
        start_date = form.get("start_date")
        frequency = form.get("frequency")
        day_of_month = int(form.get("day_of_month")) if form.get("day_of_month") else None
        weekday = int(form.get("weekday")) if form.get("weekday") else None
        end_date = form.get("end_date") or None
        # active comes as "1" or "0" from select
        active = 1 if form.get("active") == "1" else 0
        
        # Update the recurrence
        db_conn.execute(
            "UPDATE recurrences SET name=?, amount=?, category_id=?, user_id=?, account_id=?, start_date=?, end_date=?, frequency=?, day_of_month=?, weekday=?, active=? WHERE id=?",
            (
                name,
                amount,
                category_id,
                user_id,
                account_id,
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
        
        # Apply recurring transactions using existing recurrence module
        from .. import recurrence as recurrence_mod
        try:
            recurrence_mod.apply_recurring()
        except Exception:
            # Non-fatal; the edit itself was committed
            pass
        
        # Return the updated row
        recurrence = db_conn.execute(
            "SELECT r.*, c.name AS category_name, u.name AS user_name, a.name AS account_name "
            "FROM recurrences r "
            "JOIN categories c ON r.category_id = c.id "
            "JOIN users u ON r.user_id = u.id "
            "LEFT JOIN accounts a ON r.account_id = a.id "
            "WHERE r.id = ?", (recurrence_id,)
        ).fetchone()
        
        return templates.TemplateResponse(
            "partials/recurrences/row.html",
            {
                "request": request,
                # Template expects "r" context key
                "r": dict(recurrence)
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
        "SELECT r.*, c.name AS category_name, u.name AS user_name, a.name AS account_name "
        "FROM recurrences r "
        "JOIN categories c ON r.category_id = c.id "
        "JOIN users u ON r.user_id = u.id "
        "LEFT JOIN accounts a ON r.account_id = a.id "
        "WHERE r.id = ?", (recurrence_id,)
    ).fetchone()
    
    if not recurrence:
        raise HTTPException(status_code=404, detail="Recurrence not found")
    
    return templates.TemplateResponse(
        "partials/recurrences/row.html",
        {
            "request": request,
            # Template expects "r" context key
            "r": dict(recurrence)
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
    
    # מאתחל נתונים לעמוד סטטיסטיקות (including both regular and recurring expenses, excluding income categories)
    monthly = db_conn.execute("""
        SELECT strftime('%Y-%m', date) AS ym,
               SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS expenses
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now','-5 months','start of month')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY ym
        ORDER BY ym
    """).fetchall()
    
    # Get user expenses for user chart (including both regular and recurring expenses, excluding income categories)
    users = db_conn.execute("""
        SELECT u.name AS user_name, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY u.name
        ORDER BY total DESC
    """).fetchall()
    
    # Debug: Check if users query returned results
    print(f"DEBUG: users query returned {len(users) if users else 0} results")
    if users:
        print(f"DEBUG: First user result: {users[0]}")
        print(f"DEBUG: First user result type: {type(users[0])}")

    # Get monthly category breakdown for donut chart (including all expense categories and both regular and recurring expenses, even with 0 amounts)
    category_monthly_rows = db_conn.execute("""
        SELECT ym.month,
               c.name AS category,
               COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS amount
        FROM (
            SELECT DISTINCT strftime('%Y-%m', date) AS month
            FROM transactions
            WHERE date >= date('now','start of month','-5 months')
            UNION
            SELECT strftime('%Y-%m', 'now') AS month
        ) ym
        CROSS JOIN categories c
        LEFT JOIN transactions t ON c.id = t.category_id 
            AND strftime('%Y-%m', t.date) = ym.month
        WHERE c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY ym.month, c.id, c.name
        ORDER BY ym.month ASC, c.name ASC
    """).fetchall()
    
    # Also get total category breakdown for other charts (including all expense categories and both regular and recurring expenses, even with 0 amounts)
    category_total_rows = db_conn.execute("""
        SELECT c.name AS category,
               COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM categories c
        LEFT JOIN transactions t ON c.id = t.category_id 
            AND t.date >= date('now','start of month','-5 months')
        WHERE c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY c.id, c.name
        ORDER BY c.name
    """).fetchall()
    
    # Get cash vs credit breakdown for last 6 months (including both regular and recurring expenses, excluding income categories)
    # First get by user and account
    cash_vs_credit_by_user = db_conn.execute("""
        SELECT strftime('%Y-%m', t.date) AS month,
               u.name AS user_name,
               COALESCE(a.name, 'לא מוגדר') AS account_type,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS total
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        JOIN categories c ON t.category_id = c.id
        JOIN users u ON t.user_id = u.id
        WHERE t.date >= date('now','start of month','-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY month, u.name, a.name
        ORDER BY month ASC, u.name ASC, a.name ASC
    """).fetchall()
    
    # Then get totals by account (all users combined)
    cash_vs_credit_totals = db_conn.execute("""
        SELECT strftime('%Y-%m', t.date) AS month,
               COALESCE(a.name, 'לא מוגדר') AS account_type,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS total
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now','start of month','-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY month, a.name
        ORDER BY month ASC, a.name ASC
    """).fetchall()
    
    # Combine both results
    cash_vs_credit = []
    
    # Create user data with cash and credit amounts per month
    user_monthly_data = {}
    for row in cash_vs_credit_by_user:
        month = row['month']
        user_name = row['user_name']
        account_type = row['account_type']
        total = row['total']
        
        if month not in user_monthly_data:
            user_monthly_data[month] = {}
        
        if user_name not in user_monthly_data[month]:
            user_monthly_data[month][user_name] = {'cash': 0, 'credit': 0}
        
        if account_type == 'Cash':
            user_monthly_data[month][user_name]['cash'] += total
        elif account_type == 'Credit Card':
            user_monthly_data[month][user_name]['credit'] += total
        # Handle other account types - add to credit by default
        else:
            user_monthly_data[month][user_name]['credit'] += total
    
    # Add user-specific data (one row per user per month)
    for month, users in user_monthly_data.items():
        for user_name, amounts in users.items():
            total_amount = amounts['cash'] + amounts['credit']
            cash_vs_credit.append({
                'month': month,
                'user_name': user_name,
                'account_type': 'User',
                'total': total_amount,
                'cash_amount': amounts['cash'],
                'credit_amount': amounts['credit'],
                'is_total': False
            })
    
    # Create combined totals by month (all users and accounts combined)
    monthly_totals = {}
    for row in cash_vs_credit_totals:
        month = row['month']
        if month not in monthly_totals:
            monthly_totals[month] = {'cash': 0, 'credit': 0}
        
        if row['account_type'] == 'Cash':
            monthly_totals[month]['cash'] += row['total']
        elif row['account_type'] == 'Credit Card':
            monthly_totals[month]['credit'] += row['total']
        # Handle other account types - add to credit by default
        else:
            monthly_totals[month]['credit'] += row['total']
    
    # Add combined totals data
    for month, totals in monthly_totals.items():
        total_amount = totals['cash'] + totals['credit']
        cash_vs_credit.append({
            'month': month,
            'user_name': 'סה"כ',
            'account_type': 'Combined',
            'total': total_amount,
            'cash_amount': totals['cash'],
            'credit_amount': totals['credit'],
            'is_total': True
        })
    
    # Get top 5 expenses in last 3 months (regular expenses only, excluding income categories)
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
        AND t.recurrence_id IS NULL  -- exclude recurring transactions
        AND c.name NOT IN ('משכורת', 'קליניקה')
        ORDER BY ABS(t.amount) DESC
        LIMIT 5
    """).fetchall()
    
    # הוצאות קבועות לפי חודש (excluding income categories)
    recurring_monthly = db_conn.execute("""
        SELECT strftime('%Y-%m', t.date) AS month,
               COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NOT NULL
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY strftime('%Y-%m', t.date)
        ORDER BY month ASC
    """).fetchall()
    
    # Ensure database connection has row_factory set
    if not hasattr(db_conn, 'row_factory') or db_conn.row_factory is None:
        db_conn.row_factory = sqlite3.Row
    
    # Helper function to safely convert query results to dictionaries
    def safe_dict_convert(row):
        if hasattr(row, 'keys'):
            return dict(row)
        elif isinstance(row, (list, tuple)):
            # Handle tuple/list results by creating a dict with column names
            return {"value": row[0] if len(row) == 1 else row}
        else:
            return {"value": row}
    
    # Debug logging for monthly expenses
    logger.info("=== MONTHLY EXPENSES DEBUG ===")
    logger.info(f"Monthly expenses raw data: {monthly}")
    logger.info(f"Monthly expenses length: {len(monthly) if monthly else 0}")
    if monthly:
        for item in monthly:
            logger.info(f"Month: {item.get('ym', 'N/A')}, Expenses: {item.get('expenses', 'N/A')}")
    
    template_data = {
        "request": request,
        "monthly_expenses": [safe_dict_convert(r) for r in (monthly or [])],
        "user_expenses": [safe_dict_convert(r) for r in (users or [])],
        "recurring_user_expenses": [safe_dict_convert(r) for r in (recurring_monthly or [])],
        "category_expenses": [safe_dict_convert(r) for r in (category_monthly_rows or [])],
        "category_totals": [safe_dict_convert(r) for r in (category_total_rows or [])],
        "cash_vs_credit": [safe_dict_convert(r) for r in (cash_vs_credit or [])],
        "top_expenses": [safe_dict_convert(r) for r in (top_expenses or [])],  # *** ADDED THIS! ***
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
			WHERE (c.name IS NULL OR c.name NOT IN ('משכורת', 'קליניקה'))
			{where}
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
