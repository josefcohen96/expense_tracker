from __future__ import annotations
import sqlite3
from typing import Any, Dict, Optional, List
from datetime import date, timedelta, datetime
from pathlib import Path as FSPath
import calendar

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
    try:
        cur = db_conn.execute(
            """
            SELECT 
                SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income,
                COUNT(*) as total_transactions
            FROM transactions 
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            """
        )
        stats = cur.fetchone()
        recurrences_count_row = db_conn.execute("SELECT COUNT(*) as cnt FROM recurrences WHERE active = 1").fetchone()
        return {
            "total_expenses_month": (stats["total_expenses"] or 0) if stats else 0,
            "total_income_month": (stats["total_income"] or 0) if stats else 0,
            "total_transactions_month": (stats["total_transactions"] or 0) if stats else 0,
            "recurrences_count": (recurrences_count_row["cnt"] if recurrences_count_row else 0),
        }
    except Exception:
        return {"total_expenses_month": 0, "total_income_month": 0, "total_transactions_month": 0, "recurrences_count": 0}

# --------- Pages ---------
@router.get("/", response_class=HTMLResponse)
async def index(_: Request) -> RedirectResponse:
    return RedirectResponse(url="/finances", status_code=status.HTTP_302_FOUND)

@router.get("/sw.js")
async def service_worker() -> FileResponse:
    sw_path = STATIC_DIR / "js" / "sw.js"
    if not sw_path.exists():
        from starlette.responses import Response
        return Response("", media_type="application/javascript")
    return FileResponse(str(sw_path), media_type="application/javascript")

@router.get("/finances", response_class=HTMLResponse)
async def finances_dashboard(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    cur = db_conn.execute(
        """
        SELECT 
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income,
            COUNT(*) as total_transactions
        FROM transactions 
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        """
    )
    stats_row = cur.fetchone()

    recent = db_conn.execute(
        """
        SELECT t.id, t.date, t.amount, c.name as category, u.name as user, a.name as account, t.notes
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        ORDER BY t.date DESC, t.id DESC
        LIMIT 5
        """
    ).fetchall()

    rec_count = db_conn.execute("SELECT COUNT(*) as cnt FROM recurrences WHERE active = 1").fetchone()

    return templates.TemplateResponse("finances/index.html", {
        "request": request,
        "stats": {
            "total_expenses": (stats_row["total_expenses"] or 0) if stats_row else 0,
            "total_income": (stats_row["total_income"] or 0) if stats_row else 0,
            "transactions_count": (stats_row["total_transactions"] or 0) if stats_row else 0,
            "recurrences_count": (rec_count["cnt"] if rec_count else 0),
        },
        "recent_transactions": recent,
    })

@router.get("/finances/transactions", response_class=HTMLResponse)
async def finances_transactions_page(
    request: Request, 
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    amount_min: Optional[str] = Query(None),
    amount_max: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    sort: Optional[str] = Query("date_desc"),
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    offset = (page - 1) * per_page
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

    where_clause = "WHERE t.recurrence_id IS NULL AND t.amount < 0"
    params: list[Any] = []

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

    count_query = f"SELECT COUNT(*) FROM transactions t {where_clause}"
    cur = db_conn.execute(count_query, params)
    total = cur.fetchone()[0]

    order_clause = "ORDER BY "
    if sort == "date_asc":
        order_clause += "t.date ASC, t.id ASC"
    elif sort == "amount_desc":
        order_clause += "ABS(t.amount) DESC, t.date DESC"
    elif sort == "amount_asc":
        order_clause += "ABS(t.amount) ASC, t.date DESC"
    else:
        order_clause += "t.date DESC, t.id DESC"

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

    cur = db_conn.execute("SELECT id, name FROM categories ORDER BY name")
    categories = cur.fetchall()
    cur = db_conn.execute("SELECT id, name FROM users ORDER BY name")
    users = cur.fetchall()
    cur = db_conn.execute("SELECT id, name FROM accounts ORDER BY name")
    accounts = cur.fetchall()

    sidebar = await get_finance_stats(db_conn)

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
        **sidebar
    })

@router.get("/finances/income", response_class=HTMLResponse)
async def finances_income_page(
    request: Request, 
    db_conn: sqlite3.Connection = Depends(get_db_conn),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    amount_min: Optional[str] = Query(None),
    amount_max: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    sort: Optional[str] = Query("date_desc")
) -> HTMLResponse:
    offset = (page - 1) * per_page

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

    where_clause = "WHERE t.recurrence_id IS NULL AND t.amount > 0"
    params: list[Any] = []

    if category_id and category_id.strip():
        try:
            cid = int(category_id)
            where_clause += " AND t.category_id = ?"
            params.append(cid)
        except ValueError:
            pass

    if user_id and user_id.strip():
        try:
            uid = int(user_id)
            where_clause += " AND t.user_id = ?"
            params.append(uid)
        except ValueError:
            pass

    if account_id and account_id.strip():
        try:
            aid = int(account_id)
            where_clause += " AND t.account_id = ?"
            params.append(aid)
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
        tag_list = [tg.strip() for tg in tags.split(',') if tg.strip()]
        if tag_list:
            where_clause += " AND (" + " OR ".join(["t.tags LIKE ?"] * len(tag_list)) + ")"
            params.extend([f"%{tg}%" for tg in tag_list])

    count_query = f"SELECT COUNT(*) as total FROM transactions t {where_clause}"
    total_transactions = db_conn.execute(count_query, params).fetchone()[0]
    total_pages = (total_transactions + per_page - 1) // per_page

    order_clause = "ORDER BY "
    if sort == "date_asc":
        order_clause += "t.date ASC, t.id ASC"
    elif sort == "amount_desc":
        order_clause += "t.amount DESC"
    elif sort == "amount_asc":
        order_clause += "t.amount ASC"
    else:
        order_clause += "t.date DESC, t.id DESC"

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
    txs = db_conn.execute(query, params + [per_page, offset]).fetchall()

    cats = db_conn.execute(
        "SELECT id, name FROM categories WHERE name IN ('קליניקה', 'משכורת') ORDER BY name"
    ).fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()

    sidebar = await get_finance_stats(db_conn)

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
            **sidebar
        },
    )

@router.get("/finances/recurrences", response_class=HTMLResponse)
async def finances_recurrences_page(
    request: Request, 
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    frequency: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    sort: Optional[str] = Query("name_asc"),
    db_conn: sqlite3.Connection = Depends(get_db_conn)
) -> HTMLResponse:
    offset = (page - 1) * per_page

    where_clause = "WHERE 1=1"
    params: list[Any] = []

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
        pass

    count_query = f"SELECT COUNT(*) FROM recurrences r {where_clause}"
    total = db_conn.execute(count_query, params).fetchone()[0]

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
    recurrences_rows = db_conn.execute(query, params + [per_page, offset]).fetchall()

    # Compute charge date for display
    try:
        sel_year, sel_month = (start_of_month.year, start_of_month.month)
    except Exception:
        today_fallback = date.today()
        sel_year, sel_month = (today_fallback.year, today_fallback.month)

    def _first_weekday_in_month(year: int, month: int, weekday_py: int) -> date:
        month_first = date(year, month, 1)
        offset = (weekday_py - month_first.weekday()) % 7
        return month_first + timedelta(days=offset)

    computed_recurrences: List[Dict[str, Any]] = []
    for row in recurrences_rows:
        r = dict(row)
        charge_date_str = ""
        try:
            if r.get("frequency") == "monthly":
                day = int(r.get("day_of_month") or 1)
                last_day = calendar.monthrange(sel_year, sel_month)[1]
                if day > last_day:
                    day = last_day
                charge_date_str = date(sel_year, sel_month, day).isoformat()
            elif r.get("frequency") == "weekly":
                weekday_py = int(r.get("weekday") if r.get("weekday") is not None else 6)
                if weekday_py < 0:
                    weekday_py = 0
                if weekday_py > 6:
                    weekday_py = 6
                charge_date_str = _first_weekday_in_month(sel_year, sel_month, weekday_py).isoformat()
            elif r.get("frequency") == "yearly":
                month_day = (8, 1)
                try:
                    if r.get("start_date"):
                        parts = str(r["start_date"]).split("-")
                        if len(parts) >= 3:
                            mm = max(1, min(12, int(parts[1])))
                            dd = int(parts[2])
                            last_day = calendar.monthrange(sel_year, mm)[1]
                            dd = max(1, min(last_day, dd))
                            month_day = (mm, dd)
                except Exception:
                    pass
                charge_date_str = date(sel_year, month_day[0], month_day[1]).isoformat()
        except Exception:
            charge_date_str = date(sel_year, sel_month, 1).isoformat()

        r["charge_date"] = charge_date_str
        computed_recurrences.append(r)

    categories = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת', 'קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users ORDER BY name").fetchall()

    sidebar = await get_finance_stats(db_conn)

    return templates.TemplateResponse("finances/recurrences.html", {
        "request": request,
        "show_sidebar": True,
        "recurrences": computed_recurrences,
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
        **sidebar
    })

@router.get("/finances/statistics", response_class=HTMLResponse)
async def finances_statistics_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    # Minimal but compatible data for the template's summary cards
    try:
        current_month_expenses = db_conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            """
        ).fetchone()
    except Exception:
        current_month_expenses = {"total": 0}

    try:
        previous_month_expenses = db_conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now', '-1 month')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            """
        ).fetchone()
    except Exception:
        previous_month_expenses = {"total": 0}

    try:
        current_month_income = db_conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name IN ('משכורת', 'קליניקה')
            """
        ).fetchone()
    except Exception:
        current_month_income = {"total": 0}

    try:
        total_transactions_month = db_conn.execute(
            """
            SELECT COUNT(*) as total
            FROM transactions
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            """
        ).fetchone()
    except Exception:
        total_transactions_month = {"total": 0}

    try:
        total_recurring_month = db_conn.execute(
            """
            SELECT COUNT(*) as total
            FROM transactions
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND recurrence_id IS NOT NULL
            """
        ).fetchone()
    except Exception:
        total_recurring_month = {"total": 0}

    try:
        total_regular_month = db_conn.execute(
            """
            SELECT COUNT(*) as total
            FROM transactions
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND recurrence_id IS NULL
            """
        ).fetchone()
    except Exception:
        total_regular_month = {"total": 0}

    try:
        total_expenses_6months = db_conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now', '-6 months')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            """
        ).fetchone()
    except Exception:
        total_expenses_6months = {"total": 0}

    # Change percentages
    try:
        expenses_change = 0
        if (previous_month_expenses["total"] or 0) > 0:
            expenses_change = ((current_month_expenses["total"] - previous_month_expenses["total"]) / previous_month_expenses["total"]) * 100
        income_change = 0
        # Simplified: compare to previous month income too
        previous_month_income = db_conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now', '-1 month')
            AND c.name IN ('משכורת', 'קליניקה')
            """
        ).fetchone()
        if (previous_month_income["total"] or 0) > 0:
            income_change = ((current_month_income["total"] - previous_month_income["total"]) / previous_month_income["total"]) * 100
        balance_month = (current_month_income["total"] or 0) - (current_month_expenses["total"] or 0)
        balance_change = 0
    except Exception:
        expenses_change = 0
        income_change = 0
        balance_month = 0
        balance_change = 0

    # Minimal lists for charts (can be empty and charts will handle)
    monthly_expenses: List[Dict[str, Any]] = []
    category_expenses: List[Dict[str, Any]] = []
    user_expenses: List[Dict[str, Any]] = []
    recurring_monthly: List[Dict[str, Any]] = []
    cash_vs_credit: List[Dict[str, Any]] = []
    top_expenses: List[Dict[str, Any]] = []

    sidebar = await get_finance_stats(db_conn)

    template_data = {
        "request": request,
        "show_sidebar": True,
        "monthly_expenses": monthly_expenses,
        "user_expenses": user_expenses,
        "recurring_user_expenses": recurring_monthly,
        "category_expenses": category_expenses,
        "category_totals": category_expenses,
        "cash_vs_credit": cash_vs_credit,
        "top_expenses": top_expenses,
        "total_expenses_month": current_month_expenses["total"],
        "total_income_month": current_month_income["total"],
        "balance_month": balance_month,
        "categories_count": 0,
        "expenses_change": expenses_change,
        "income_change": income_change,
        "balance_change": balance_change,
        "total_transactions_month": total_transactions_month["total"],
        "total_recurring_month": total_recurring_month["total"],
        "total_regular_month": total_regular_month["total"],
        "total_expenses_6months": total_expenses_6months["total"],
        **sidebar,
    }

    # Pick existing template file (finances or legacy pages directory)
    target_tpl = "finances/statistics.html"
    if not (TEMPLATES_DIR / "finances" / "statistics.html").exists() and (TEMPLATES_DIR / "pages" / "statistics.html").exists():
        target_tpl = "pages/statistics.html"

    return templates.TemplateResponse(target_tpl, template_data)

@router.get("/finances/backup", response_class=HTMLResponse)
async def finances_backup_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)) -> HTMLResponse:
    return templates.TemplateResponse("finances/backup.html", {"request": request})
