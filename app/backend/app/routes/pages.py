from __future__ import annotations
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import date, timedelta, datetime
from pathlib import Path as FSPath
import calendar

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from ..auth import public

from ..db import get_db_conn
import logging
logger = logging.getLogger(__name__)

# Frontend paths
ROOT_DIR = FSPath(__file__).resolve().parents[3]
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(tags=["pages"])

# public decorator is imported from ..auth


@router.get("/login", response_class=HTMLResponse)
@public
async def login_page(request: Request) -> HTMLResponse:
    # If already authenticated, go straight to dashboard
    if request.session.get("user"):
        return RedirectResponse(url="/finances", status_code=status.HTTP_303_SEE_OTHER)
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "pages/login.html",
        {
            "request": request,
            "error": error,
            "show_sidebar": False,
        },
    )


@router.post("/login", response_class=HTMLResponse, response_model=None)
@public
async def login_post(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()
    logger.info(f"LOGIN attempt username={username}")

    # Static users per request: KARINA/KA1234, YOSEF/YO1234
    valid_users = {
        "KARINA": "KA1234",
        "YOSEF": "YO1234",
    }

    # case-insensitive username match
    user_key = username.upper()
    if user_key in valid_users and password == valid_users[user_key]:
        logger.info(f"LOGIN success username={user_key}")
        request.session["user"] = {"username": user_key}
        nxt = request.query_params.get("next") or form.get("next") or "/finances"
        # Basic safety: only allow internal paths
        if not isinstance(nxt, str) or not nxt.startswith("/"):
            nxt = "/finances"
        return RedirectResponse(url=nxt, status_code=status.HTTP_303_SEE_OTHER)

    # invalid credentials
    logger.info(f"LOGIN failed username={username}")
    return templates.TemplateResponse(
        "pages/login.html",
        {
            "request": request,
            "error": "שם משתמש או סיסמה שגויים",
            "show_sidebar": False,
        },
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    logger.info(f"LOGOUT user={request.session.get('user')}")
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


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
async def finances_dashboard(
    request: Request,
    month: Optional[str] = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    # Resolve selected month (YYYY-MM), default to current
    today = date.today()
    default_ym = today.strftime("%Y-%m")
    selected_ym = default_ym
    if month:
        try:
            # Validate format
            dt_obj = datetime.strptime(month, "%Y-%m")
            selected_ym = dt_obj.strftime("%Y-%m")
        except Exception:
            selected_ym = default_ym

    sel_year, sel_month = map(int, selected_ym.split("-"))
    month_first = date(sel_year, sel_month, 1)
    # Compute next month first day to derive month_last
    next_first = date(sel_year + (1 if sel_month == 12 else 0), 1 if sel_month == 12 else sel_month + 1, 1)
    month_last = next_first - timedelta(days=1)

    # KPIs for selected month
    kpi_row = db_conn.execute(
        """
        SELECT 
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income,
            COUNT(*) as total_transactions
        FROM transactions 
        WHERE strftime('%Y-%m', date) = ?
          AND user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        """,
        (selected_ym,),
    ).fetchone() or {"total_expenses": 0, "total_income": 0, "total_transactions": 0}

    cur_expenses = float(kpi_row["total_expenses"] or 0)
    cur_income = float(kpi_row["total_income"] or 0)
    tx_count = int(kpi_row["total_transactions"] or 0)

    # Previous month (relative to selected) for deltas
    prev_year = sel_year if sel_month > 1 else sel_year - 1
    prev_month_num = sel_month - 1 if sel_month > 1 else 12
    prev_ym = f"{prev_year:04d}-{prev_month_num:02d}"
    prev = db_conn.execute(
        """
        SELECT 
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income
        FROM transactions 
        WHERE strftime('%Y-%m', date) = ?
          AND user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        """,
        (prev_ym,),
    ).fetchone() or {"total_expenses": 0, "total_income": 0}

    def pct_change(cur_val: float, prev_val: float) -> float:
        if not prev_val:
            return 0.0
        return ((cur_val - prev_val) / prev_val) * 100.0

    expenses_change = pct_change(cur_expenses, float(prev["total_expenses"] or 0))
    income_change = pct_change(cur_income, float(prev["total_income"] or 0))
    balance = cur_income - cur_expenses

    # Recent transactions (latest 5) in selected month
    recent = db_conn.execute(
        """
        SELECT t.id, t.date, t.amount, c.name as category, u.name as user, a.name as account, t.notes
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE strftime('%Y-%m', t.date) = ?
          AND t.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        ORDER BY t.date DESC, t.id DESC
        LIMIT 5
        """,
        (selected_ym,),
    ).fetchall()

    # Active recurrences count
    rec_count_row = db_conn.execute("SELECT COUNT(*) AS cnt FROM recurrences WHERE active = 1").fetchone()
    recurrences_count = int(rec_count_row["cnt"] if rec_count_row else 0)

    # Top expense categories (selected month)
    top_categories = db_conn.execute(
        """
        SELECT c.name AS category, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = ? AND t.amount < 0
          AND t.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        GROUP BY c.name
        ORDER BY total DESC
        LIMIT 5
        """,
        (selected_ym,),
    ).fetchall()

    # Upcoming recurrences for selected month

    recs = db_conn.execute(
        """
        SELECT r.id, r.name, r.amount, r.frequency, r.day_of_month, r.weekday,
               r.next_charge_date, c.name AS category, u.name AS user
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.active = 1
          AND r.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        """
    ).fetchall()

    def first_weekday_in_month(year: int, month: int, weekday_py: int) -> date:
        mf = date(year, month, 1)
        off = (weekday_py - mf.weekday()) % 7
        return mf + timedelta(days=off)

    upcoming: List[Dict[str, Any]] = []
    for r in recs:
        charge: Optional[date] = None
        try:
            if r["frequency"] == "monthly":
                day = int(r["day_of_month"] or 1)
                last_day = calendar.monthrange(sel_year, sel_month)[1]
                day = max(1, min(last_day, day))
                charge = date(sel_year, sel_month, day)
            elif r["frequency"] == "weekly":
                wd = int(r["weekday"] if r["weekday"] is not None else 6)
                wd = max(0, min(6, wd))
                charge = first_weekday_in_month(sel_year, sel_month, wd)
            elif r["frequency"] == "yearly":
                # For yearly, use month/day from next_charge_date if present; fallback to 01-08
                mm, dd = 8, 1
                if r["next_charge_date"]:
                    parts = str(r["next_charge_date"]).split("-")
                    if len(parts) >= 3:
                        mm = max(1, min(12, int(parts[1])))
                        dd = max(1, min(calendar.monthrange(sel_year, mm)[1], int(parts[2])))
                charge = date(sel_year, mm, dd)
        except Exception:
            charge = None
        if charge and month_first <= charge <= month_last:
            upcoming.append({
                "id": r["id"],
                "name": r["name"],
                "amount": r["amount"],
                "date": charge.isoformat(),
                "category": r["category"],
                "user": r["user"],
            })
    upcoming = sorted(upcoming, key=lambda x: x["date"])[:5]

    return templates.TemplateResponse(
        "finances/index.html",
        {
            "request": request,
            "show_sidebar": True,
            "selected_month": selected_ym,
            "total_expenses": cur_expenses,
            "total_income": cur_income,
            "transactions_count": tx_count,
            "recurrences_count": recurrences_count,
            "balance": balance,
            "expenses_change": expenses_change,
            "income_change": income_change,
            "top_categories": top_categories,
            "upcoming_recurrences": upcoming,
            "recent_transactions": recent,
        },
    )


# -----------------------------
# Finances: Transactions page
# -----------------------------
@router.get("/finances/transactions", response_class=HTMLResponse)
async def finances_transactions(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    page = max(1, page)
    per_page = max(1, min(100, per_page))
    offset = (page - 1) * per_page

    total = db_conn.execute("SELECT COUNT(*) FROM transactions WHERE recurrence_id IS NULL AND amount < 0").fetchone()[0]
    rows = db_conn.execute(
        """
        SELECT t.id, t.date, t.amount,
               c.name as category,
               u.name as user,
               a.name as account,
               t.notes,
               t.tags
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.recurrence_id IS NULL AND t.amount < 0
          AND t.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        ORDER BY t.date DESC, t.id DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, offset),
    ).fetchall()

    # For expenses page: exclude income categories from the dropdown
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users WHERE name IN ('יוסף','קארינה') ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
    }

    return templates.TemplateResponse(
        "finances/transactions.html",
        {
            "request": request,
            "transactions": rows,
            "categories": categories,
            "users": users,
            "accounts": accounts,
            "pagination": pagination,
            "show_sidebar": True,
        },
    )


# -----------------------------
# Finances: Income page
# -----------------------------
@router.get("/finances/income", response_class=HTMLResponse)
async def finances_income(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    page = max(1, page)
    per_page = max(1, min(100, per_page))
    offset = (page - 1) * per_page

    total = db_conn.execute("SELECT COUNT(*) FROM transactions WHERE amount > 0").fetchone()[0]
    rows = db_conn.execute(
        """
        SELECT t.id, t.date, t.amount,
               c.id AS category_id, c.name as category,
               u.id AS user_id, u.name as user,
               a.name AS account_name,
               t.notes,
               t.tags
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.amount > 0 AND t.recurrence_id IS NULL
          AND t.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        ORDER BY t.date DESC, t.id DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, offset),
    ).fetchall()

    # For income page: show only income categories
    categories = db_conn.execute("SELECT id, name FROM categories WHERE name IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users WHERE name IN ('יוסף','קארינה') ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
    }

    from datetime import date as _date

    return templates.TemplateResponse(
        "pages/income.html",
        {
            "request": request,
            "transactions": rows,
            "categories": categories,
            "users": users,
            "accounts": accounts,
            "pagination": pagination,
            "today": _date.today().isoformat(),
            "show_sidebar": True,
        },
    )


# -----------------------------
# Finances: Recurrences page
# -----------------------------
@router.get("/finances/recurrences", response_class=HTMLResponse)
async def finances_recurrences(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    page = max(1, page)
    per_page = max(1, min(100, per_page))
    offset = (page - 1) * per_page

    base_sql = (
        """
        SELECT r.id, r.name, r.amount, r.frequency, r.next_charge_date, r.active,
               c.name AS category_name,
               u.name AS user_name,
               NULL AS account_name
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        """
    )

    # Optional filters: category_id, only_active
    where_clauses: List[str] = []
    params: List[Any] = []

    cat_id_raw = request.query_params.get("category_id")
    if cat_id_raw:
        try:
            cat_id_val = int(cat_id_raw)
            where_clauses.append("r.category_id = ?")
            params.append(cat_id_val)
        except Exception:
            pass

    only_active = request.query_params.get("only_active")
    if only_active in ("1", "true", "True", "on"):
        where_clauses.append("r.active = 1")

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total = db_conn.execute(f"SELECT COUNT(*) FROM recurrences r{where_sql}", params).fetchone()[0]
    # Force user filter to Yosef and Karina only
    user_filter_sql = " AND r.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))"
    recs = db_conn.execute(base_sql + where_sql + user_filter_sql + " ORDER BY r.id DESC LIMIT ? OFFSET ?", (*params, per_page, offset)).fetchall()

    # Recurrences are expenses: exclude income categories
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users WHERE name IN ('יוסף','קארינה') ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
    }

    return templates.TemplateResponse(
        "pages/recurrences.html",
        {
            "request": request,
            "recurrences": recs,
            "categories": categories,
            "users": users,
            "accounts": accounts,
            "pagination": pagination,
            "show_sidebar": True,
        },
    )


# -----------------------------
# Finances: Active Recurrences page
# -----------------------------
@router.get("/finances/recurrences/active", response_class=HTMLResponse)
async def finances_recurrences_active(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    page = max(1, page)
    per_page = max(1, min(100, per_page))
    offset = (page - 1) * per_page

    base_sql = (
        """
        SELECT r.id, r.name, r.amount, r.frequency, r.next_charge_date, r.active,
               c.name AS category_name,
               u.name AS user_name,
               NULL AS account_name
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        """
    )

    where_clauses: List[str] = ["r.active = 1"]
    params: List[Any] = []

    cat_id_raw = request.query_params.get("category_id")
    if cat_id_raw:
        try:
            cat_id_val = int(cat_id_raw)
            where_clauses.append("r.category_id = ?")
            params.append(cat_id_val)
        except Exception:
            pass

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total = db_conn.execute(f"SELECT COUNT(*) FROM recurrences r{where_sql}", params).fetchone()[0]
    user_filter_sql = " AND r.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))"
    recs = db_conn.execute(base_sql + where_sql + user_filter_sql + " ORDER BY r.id DESC LIMIT ? OFFSET ?", (*params, per_page, offset)).fetchall()

    # Active recurrences are expenses: exclude income categories
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users WHERE name IN ('יוסף','קארינה') ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
    }

    return templates.TemplateResponse(
        "pages/recurrences_active.html",
        {
            "request": request,
            "recurrences": recs,
            "categories": categories,
            "users": users,
            "accounts": accounts,
            "pagination": pagination,
            "show_sidebar": True,
        },
    )

# ---- Recurrences inline CRUD (HTMX) ----
@router.post("/recurrences", response_class=HTMLResponse)
async def create_recurrence_form(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    form = await request.form()
    name = form.get("name")
    amount = float(form.get("amount")) if form.get("amount") else 0.0
    category_id = int(form.get("category_id"))
    user_id = int(form.get("user_id"))
    account_id = int(form.get("account_id", "0") or 0) or None
    frequency = form.get("frequency") or "monthly"
    day_of_month = form.get("day_of_month")
    weekday = form.get("weekday")
    next_charge_date = form.get("next_charge_date")

    # Compute sensible default next_charge_date if not provided
    from datetime import date as _date, timedelta as _timedelta

    def _clamp_day(year: int, month: int, day: int) -> _date:
        import calendar as _calendar
        last = _calendar.monthrange(year, month)[1]
        if day < 1:
            day = 1
        if day > last:
            day = last
        return _date(year, month, day)

    if not next_charge_date:
        today = _date.today()
        if frequency == "monthly":
            d = int(day_of_month) if day_of_month else 1
            candidate = _clamp_day(today.year, today.month, d)
            if candidate <= today:
                # move to next month
                nm_year = today.year + (1 if today.month == 12 else 0)
                nm_month = 1 if today.month == 12 else today.month + 1
                candidate = _clamp_day(nm_year, nm_month, d)
            next_charge_date = candidate.isoformat()
        elif frequency == "weekly":
            # Python weekday: Monday=0..Sunday=6. Default to Sunday if not provided
            target = int(weekday) if weekday not in (None, "") else 6
            target = max(0, min(6, target))
            delta = (target - today.weekday()) % 7
            if delta == 0:
                delta = 7  # next week
            candidate = today + _timedelta(days=delta)
            next_charge_date = candidate.isoformat()
            # Ensure weekday saved even if user omitted it
            weekday = str(target)
        elif frequency == "yearly":
            # Default: same day next month/year heuristic -> set to one month ahead on the 1st
            nm_year = today.year + (1 if today.month == 12 else 0)
            nm_month = 1 if today.month == 12 else today.month + 1
            candidate = _clamp_day(nm_year, nm_month, 1)
            next_charge_date = candidate.isoformat()
        else:
            next_charge_date = (today + _timedelta(days=1)).isoformat()

    payload = {
        "name": name,
        "amount": amount,
        "category_id": category_id,
        "user_id": user_id,
        "account_id": account_id,
        "frequency": frequency,
        "day_of_month": int(day_of_month) if day_of_month else None,
        "weekday": int(weekday) if weekday else None,
        "next_charge_date": next_charge_date or None,
        "active": True,
    }
    # Insert into recurrences table directly
    cur = db_conn.execute(
        """
        INSERT INTO recurrences (name, amount, category_id, user_id, frequency, day_of_month, weekday, next_charge_date, active, account_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["name"], payload["amount"], payload["category_id"], payload["user_id"],
            payload["frequency"], payload["day_of_month"], payload["weekday"], payload["next_charge_date"],
            1, account_id,
        ),
    )
    db_conn.commit()

    return RedirectResponse(url="/finances/recurrences", status_code=303)


@router.post("/recurrences/{rec_id}/toggle-active", response_class=HTMLResponse)
async def toggle_recurrence_active(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    cur = db_conn.execute("SELECT active FROM recurrences WHERE id = ?", (rec_id,))
    row = cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Recurrence not found")
    new_val = 0 if int(row[0] or 0) == 1 else 1
    db_conn.execute("UPDATE recurrences SET active = ? WHERE id = ?", (new_val, rec_id))
    db_conn.commit()
    return await get_recurrence_row(request, rec_id, db_conn)


@router.get("/recurrences/{rec_id}/row", response_class=HTMLResponse)
async def get_recurrence_row(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    row = db_conn.execute(
        """
        SELECT r.id, r.name, r.amount, r.frequency, r.next_charge_date, r.active,
               r.day_of_month, r.weekday,
               r.category_id, r.user_id, NULL as account_id,
               c.name AS category_name, u.name AS user_name, NULL AS account_name
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.id = ?
        """,
        (rec_id,),
    ).fetchone()
    return templates.TemplateResponse(
        "partials/recurrences/row.html",
        {"request": request, "r": row},
    )


@router.get("/recurrences/{rec_id}/edit-inline", response_class=HTMLResponse)
async def edit_recurrence_inline(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    row = db_conn.execute("SELECT * FROM recurrences WHERE id = ?", (rec_id,)).fetchone()
    # Edit recurrence: restrict to expense categories
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute("SELECT id, name FROM users WHERE name IN ('יוסף','קארינה') ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse(
        "partials/recurrences/edit_row.html",
        {
            "request": request,
            "recurrence": row,
            "categories": categories,
            "users": users,
            "accounts": accounts,
        },
    )


@router.post("/recurrences/{rec_id}/edit-inline", response_class=HTMLResponse)
async def save_recurrence_inline(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    form = await request.form()
    fields: Dict[str, Any] = {}
    for k in ("name", "frequency", "next_charge_date"):
        if k in form and form[k] != "":
            fields[k] = form[k]
    for k in ("amount", "category_id", "user_id", "account_id", "day_of_month", "weekday", "active"):
        if k in form and form[k] != "":
            if k in ("amount",):
                fields[k] = float(form[k])
            elif k in ("active",):
                fields[k] = 1 if str(form[k]) in ("1", "true", "True") else 0
            else:
                fields[k] = int(form[k])
    if not fields:
        return await get_recurrence_row(request, rec_id, db_conn)

    set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
    params = list(fields.values()) + [rec_id]
    db_conn.execute(f"UPDATE recurrences SET {set_clause} WHERE id = ?", params)
    db_conn.commit()

    return await get_recurrence_row(request, rec_id, db_conn)


@router.post("/recurrences/{rec_id}/delete-inline", response_class=HTMLResponse)
async def delete_recurrence_inline(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    db_conn.execute("DELETE FROM recurrences WHERE id = ?", (rec_id,))
    db_conn.commit()
    # Return an empty row placeholder that HTMX will remove / leave blank
    from starlette.responses import PlainTextResponse
    return PlainTextResponse("", status_code=204)


# -----------------------------
# Finances: Statistics page
# -----------------------------
@router.get("/finances/statistics", response_class=HTMLResponse)
async def finances_statistics(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    month_totals = db_conn.execute(
        """
        SELECT 
            SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income,
            COUNT(*) as total_transactions
        FROM transactions 
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
          AND user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        """
    ).fetchone() or {"total_expenses": 0, "total_income": 0, "total_transactions": 0}

    total_recurring_month = db_conn.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
        FROM transactions 
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now') AND recurrence_id IS NOT NULL
          AND user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        """
    ).fetchone()[0]

    categories = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()

    # Monthly totals (6 months) for the bar chart are fetched via /api/statistics/monthly
    monthly_data = []

    # Category by month data for donut (last 6 months window, excluding income categories)
    category_data_rows = db_conn.execute(
        """
        SELECT strftime('%Y-%m', t.date) AS month,
               c.name AS category,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS amount
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND t.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        GROUP BY month, c.name
        ORDER BY month ASC, amount DESC
        """
    ).fetchall()
    category_data = [dict(row) for row in (category_data_rows or [])]

    # Top 5 regular (non-recurring) expenses for the last 6 months (largest absolute amounts)
    top_regular_expenses_rows = db_conn.execute(
        """
        SELECT t.id,
               t.date,
               ABS(t.amount) AS amount,
               c.name AS category,
               u.name AS user,
               COALESCE(a.name, 'לא מוגדר') AS account,
               t.notes
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.date >= date('now', '-6 months')
          AND t.amount < 0
          AND t.recurrence_id IS NULL
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND t.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        ORDER BY ABS(t.amount) DESC, t.date DESC
        LIMIT 5
        """
    ).fetchall()
    top_regular_expenses = [dict(row) for row in (top_regular_expenses_rows or [])]

    # Cash vs Credit per user for the last 6 months, plus total per user
    cash_credit_rows = db_conn.execute(
        """
        SELECT u.name AS user_name,
               COALESCE(a.name, 'לא מוגדר') AS account_name,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS total
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND t.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        GROUP BY u.name, a.name
        ORDER BY u.name ASC
        """
    ).fetchall()

    # Normalize cash/credit per user to a compact structure for the template table
    cash_credit_user_totals: List[Dict[str, Any]] = []
    user_map: Dict[str, Dict[str, float]] = {}
    for row in cash_credit_rows or []:
        user = row["user_name"]
        account = (row["account_name"] or '').strip()
        total = float(row["total"] or 0)
        m = user_map.setdefault(user, {"cash": 0.0, "credit": 0.0, "other": 0.0})

        # Normalize account names (support Hebrew and English labels)
        name_norm = account.lower()
        is_cash = (account in ("מזומן",)) or ("cash" in name_norm)
        is_credit = (account in ("כרטיס אשראי",)) or ("אשראי" in account) or ("credit" in name_norm)

        if is_cash:
            m["cash"] += total
        elif is_credit:
            m["credit"] += total
        else:
            m["other"] += total
    for user, sums in user_map.items():
        cash_credit_user_totals.append({
            "user": user,
            "cash": round(sums.get("cash", 0.0), 2),
            "credit": round(sums.get("credit", 0.0), 2),
            "other": round(sums.get("other", 0.0), 2),
            "total": round(sums.get("cash", 0.0) + sums.get("credit", 0.0) + sums.get("other", 0.0), 2),
        })
    # Sort by total desc
    cash_credit_user_totals.sort(key=lambda r: r["total"], reverse=True)

    # No longer using recurring_user_expenses chart in this page
    recurring_user_expenses = []

    # Recurring expenses (instances) in the last 6 months (separate from regular)
    recurring_expenses_rows = db_conn.execute(
        """
        SELECT t.id,
               t.date,
               ABS(t.amount) AS amount,
               c.name AS category,
               u.name AS user,
               COALESCE(a.name, 'לא מוגדר') AS account,
               t.notes,
               r.name AS recurrence_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN recurrences r ON t.recurrence_id = r.id
        WHERE t.date >= date('now', '-6 months')
          AND t.amount < 0
          AND t.recurrence_id IS NOT NULL
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND t.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        ORDER BY ABS(t.amount) DESC, t.date DESC
        LIMIT 10
        """
    ).fetchall()
    recurring_expenses = [dict(row) for row in (recurring_expenses_rows or [])]

    # Active recurring definitions with frequency
    active_recurrences_rows = db_conn.execute(
        """
        SELECT r.id,
               r.name,
               ABS(r.amount) AS amount,
               r.frequency,
               r.next_charge_date,
               r.day_of_month,
               r.weekday,
               r.active,
               c.name AS category,
               u.name AS user
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.active = 1
          AND r.user_id IN (SELECT id FROM users WHERE name IN ('יוסף','קארינה'))
        ORDER BY r.name ASC
        """
    ).fetchall()
    active_recurrences = [dict(row) for row in (active_recurrences_rows or [])]

    return templates.TemplateResponse(
        "finances/statistics.html",
        {
            "request": request,
            "total_expenses_month": float(month_totals["total_expenses"] or 0),
            "total_income_month": float(month_totals["total_income"] or 0),
            "total_transactions_month": int(month_totals["total_transactions"] or 0),
            "total_recurring_month": float(total_recurring_month or 0),
            "categories": categories,
            "monthly_data": monthly_data,
        "category_data": category_data,
        "top_regular_expenses": top_regular_expenses,
        "recurring_expenses": recurring_expenses,
        "active_recurrences": active_recurrences,
        "cash_credit_user_totals": cash_credit_user_totals,
        "recurring_user_expenses": recurring_user_expenses,
            "show_sidebar": True,
        },
    )


# -----------------------------
# Finances: Backup page
# -----------------------------
@router.get("/finances/backup", response_class=HTMLResponse)
async def finances_backup(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "finances/backup.html",
        {
            "request": request,
            "show_sidebar": True,
        },
    )