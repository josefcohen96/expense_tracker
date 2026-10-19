"""Finances module pages (dashboard, transactions, income, recurrences, statistics, backup)."""
from __future__ import annotations

import calendar
import logging
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db as _db
from ..db import get_db_conn
from ..services import hebrew_dates as hd
from ..services.people import default_account_id, find_person, household
from ..templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])


def _first_weekday_in_month(year: int, month: int, weekday_py: int) -> date:
    """
    Get the date of the first occurrence of a specific weekday in a month.
    weekday_py: 0=Monday, 6=Sunday
    """
    mf = date(year, month, 1)
    off = (weekday_py - mf.weekday()) % 7
    return mf + timedelta(days=off)


def _get_main_user_ids(db_conn: sqlite3.Connection) -> str:
    """
    Get the user IDs for the main users (English canonical names: Yosef, Karina).
    Returns a string of comma-separated IDs for use in SQL IN clauses.
    """
    # Prefer English-only canonical names
    result = db_conn.execute(
        "SELECT id FROM users WHERE name IN ('Yosef','Karina')"
    ).fetchall()

    if result:
        return ",".join(str(row["id"]) for row in result)

    # Fallback: if English names missing, pick the first two users consistently
    all_users = db_conn.execute("SELECT id FROM users ORDER BY id ASC").fetchall()
    return ",".join(str(row["id"]) for row in all_users[:2]) if all_users else "1,2"


@router.get("/finances", response_class=HTMLResponse)
async def finances_dashboard(
    request: Request,
    month: str | None = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    logger.debug("FINANCES dashboard request", extra={
        "path": request.url.path,
        "method": request.method,
        "month": month,
    })
    # Ensure schema exists in deployments where startup init may have been skipped
    try:
        _db.initialise_database()
    except Exception:
        pass
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

    # Get main user IDs (works with both Hebrew and English names)
    user_ids = _get_main_user_ids(db_conn)

    # KPIs for selected month
    kpi_row = db_conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN t.amount < 0 AND c.name NOT IN ('משכורת', 'קליניקה') AND COALESCE(c.is_saving, 0) = 0
                     THEN ABS(t.amount) ELSE 0 END) as total_expenses,
            SUM(CASE WHEN t.amount < 0 AND COALESCE(c.is_saving, 0) = 1
                     THEN ABS(t.amount) ELSE 0 END) as total_savings,
            SUM(CASE WHEN t.amount > 0 AND c.name IN ('משכורת', 'קליניקה')
                     THEN t.amount ELSE 0 END) as total_income,
            COUNT(*) as total_transactions
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = ?
          AND t.user_id IN ({user_ids})
        """,
        (selected_ym,),
    ).fetchone() or {"total_expenses": 0, "total_savings": 0, "total_income": 0, "total_transactions": 0}

    cur_expenses = float(kpi_row["total_expenses"] or 0)
    cur_savings = float(kpi_row["total_savings"] or 0)
    cur_income = float(kpi_row["total_income"] or 0)
    tx_count = int(kpi_row["total_transactions"] or 0)

    # Previous month (relative to selected) for deltas
    prev_year = sel_year if sel_month > 1 else sel_year - 1
    prev_month_num = sel_month - 1 if sel_month > 1 else 12
    prev_ym = f"{prev_year:04d}-{prev_month_num:02d}"
    prev = db_conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN t.amount < 0 AND c.name NOT IN ('משכורת', 'קליניקה') AND COALESCE(c.is_saving, 0) = 0
                     THEN ABS(t.amount) ELSE 0 END) as total_expenses,
            SUM(CASE WHEN t.amount > 0 AND c.name IN ('משכורת', 'קליניקה')
                     THEN t.amount ELSE 0 END) as total_income,
            SUM(CASE WHEN t.amount < 0 AND COALESCE(c.is_saving, 0) = 1
                     THEN ABS(t.amount) ELSE 0 END) as total_savings
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = ?
          AND t.user_id IN ({user_ids})
        """,
        (prev_ym,),
    ).fetchone() or {"total_expenses": 0, "total_income": 0, "total_savings": 0}

    def pct_change(cur_val: float, prev_val: float) -> float:
        if not prev_val:
            return 0.0
        return ((cur_val - prev_val) / prev_val) * 100.0

    expenses_change = pct_change(cur_expenses, float(prev["total_expenses"] or 0))
    income_change = pct_change(cur_income, float(prev["total_income"] or 0))
    balance = cur_income - cur_expenses

    # Recent transactions (latest 5) in selected month
    recent = db_conn.execute(
        f"""
        SELECT t.id, t.date, t.amount, c.name as category, u.name as user, a.name as account, t.notes,
               t.user_id
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE strftime('%Y-%m', t.date) = ?
          AND t.user_id IN ({user_ids})
        ORDER BY t.date DESC, t.id DESC
        LIMIT 5
        """,
        (selected_ym,),
    ).fetchall()

    # Active recurrences count
    rec_count_row = db_conn.execute(f"SELECT COUNT(*) AS cnt FROM recurrences WHERE active = 1 AND user_id IN ({user_ids})").fetchone()
    recurrences_count = int(rec_count_row["cnt"] if rec_count_row else 0)

    # Top expense categories (selected month)
    top_categories = db_conn.execute(
        f"""
        SELECT c.name AS category, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = ? AND t.amount < 0
          AND t.user_id IN ({user_ids})
        GROUP BY c.name
        ORDER BY total DESC
        LIMIT 5
        """,
        (selected_ym,),
    ).fetchall()

    # Upcoming recurrences for selected month

    recs = db_conn.execute(
        f"""
        SELECT r.id, r.name, r.amount, r.frequency, r.day_of_month, r.weekday,
               r.next_charge_date, c.name AS category, u.name AS user
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.active = 1
          AND r.user_id IN ({user_ids})
        """
    ).fetchall()

    upcoming: list[dict[str, Any]] = []
    for r in recs:
        charge: date | None = None
        try:
            if r["frequency"] == "monthly":
                day = int(r["day_of_month"] or 1)
                last_day = calendar.monthrange(sel_year, sel_month)[1]
                day = max(1, min(last_day, day))
                charge = date(sel_year, sel_month, day)
            elif r["frequency"] == "weekly":
                wd = int(r["weekday"] if r["weekday"] is not None else 6)
                wd = max(0, min(6, wd))
                charge = _first_weekday_in_month(sel_year, sel_month, wd)
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

    # --- Mobile סקירה (< lg): month chips, balance card, top categories, recent rows ---
    def month_delta(cur_val: float, prev_val: float, up_color: str, down_color: str) -> dict[str, str] | None:
        """'▲ 4.2%' vs the previous month; None when there is nothing to compare with."""
        if not prev_val:
            return None
        change = (cur_val - prev_val) / prev_val * 100.0
        if abs(change) < 0.05:
            return {"text": "קבוע", "color": "#9ca3af"}
        arrow = "▲" if change > 0 else "▼"
        return {"text": f"{arrow} {abs(change):.1f}%", "color": up_color if change > 0 else down_color}

    chip_months = []
    chip_y, chip_m = today.year, today.month
    for _ in range(3):
        chip_months.append((chip_y, chip_m))
        chip_y, chip_m = (chip_y, chip_m - 1) if chip_m > 1 else (chip_y - 1, 12)
    if (sel_year, sel_month) not in chip_months:
        chip_months.append((sel_year, sel_month))
        chip_months.sort(reverse=True)
    month_chips = [
        {
            "label": hd.HEBREW_MONTHS[chip_m - 1] + ("" if chip_y == today.year else f" {chip_y}"),
            "href": f"/finances?month={chip_y:04d}-{chip_m:02d}",
            "active": (chip_y, chip_m) == (sel_year, sel_month),
        }
        for chip_y, chip_m in chip_months
    ]

    balance_bar = None
    if cur_income > 0:
        expenses_pct = min(100.0, cur_expenses / cur_income * 100.0)
        savings_pct = min(100.0 - expenses_pct, cur_savings / cur_income * 100.0)
        balance_bar = {"expenses": round(expenses_pct, 1), "savings": round(savings_pct, 1)}

    where_rows = db_conn.execute(
        f"""
        SELECT c.name AS category, SUM(ABS(t.amount)) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = ? AND t.amount < 0
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND COALESCE(c.is_saving, 0) = 0
          AND t.user_id IN ({user_ids})
        GROUP BY c.name
        ORDER BY total DESC
        LIMIT 3
        """,
        (selected_ym,),
    ).fetchall()
    rank_colors = ("#2563eb", "#7c3aed", "#d97706")
    where_money_went = []
    for row in where_rows:
        cat_total = float(row["total"] or 0)
        if row["category"] == "חתונה":
            color = "#e11d48"
        else:
            color = rank_colors[sum(1 for w in where_money_went if w["name"] != "חתונה")]
        where_money_went.append({
            "name": row["category"],
            "total": cat_total,
            "share": round(min(100.0, cat_total / cur_expenses * 100.0), 1) if cur_expenses else 0.0,
            "color": color,
        })

    display_by_id = {p["id"]: p["display"] for p in household(db_conn)}
    recent_rows = []
    for t in recent:
        amount = float(t["amount"] or 0)
        when = hd.parse_iso(t["date"])
        meta = [t["category"], display_by_id.get(t["user_id"]), hd.relative_day(when, today) if when else None]
        recent_rows.append({
            "name": (t["notes"] or "").strip() or t["category"] or "",
            "meta": " · ".join(part for part in meta if part),
            "amount": abs(amount),
            "is_income": amount > 0,
        })

    mobile = {
        "month_chips": month_chips,
        "balance_bar": balance_bar,
        "deltas": {
            "expenses": month_delta(cur_expenses, float(prev["total_expenses"] or 0), "#dc2626", "#16a34a"),
            "income": month_delta(cur_income, float(prev["total_income"] or 0), "#16a34a", "#dc2626"),
            "savings": month_delta(cur_savings, float(prev["total_savings"] or 0), "#0d9488", "#0d9488"),
        },
        "where_money_went": where_money_went,
        "recent": recent_rows,
    }

    return templates.TemplateResponse(
        request,
        "finances/index.html",
        {
            "request": request,
            "show_sidebar": True,
            "selected_month": selected_ym,
            "total_expenses": cur_expenses,
            "total_savings": cur_savings,
            "total_income": cur_income,
            "transactions_count": tx_count,
            "recurrences_count": recurrences_count,
            "balance": balance,
            "expenses_change": expenses_change,
            "income_change": income_change,
            "top_categories": top_categories,
            "upcoming_recurrences": upcoming,
            "recent_transactions": recent,
            "mobile": mobile,
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

    # Get main user IDs (works with both Hebrew and English names)
    user_ids = _get_main_user_ids(db_conn)

    # Optional filters
    qp = request.query_params
    category_id_raw = qp.get("category_id")
    user_id_raw = qp.get("user_id")
    date_from = qp.get("date_from")
    date_to = qp.get("date_to")
    amount_min = qp.get("amount_min")
    amount_max = qp.get("amount_max")
    account_id_raw = qp.get("account_id")
    tags = qp.get("tags")
    sort_param = qp.get("sort", "date_desc")

    where_clauses = ["t.recurrence_id IS NULL"]
    params: list[Any] = []

    if date_from:
        where_clauses.append("t.date >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("t.date <= ?")
        params.append(date_to)
    if category_id_raw:
        try:
            category_id = int(category_id_raw)
            where_clauses.append("t.category_id = ?")
            params.append(category_id)
        except Exception:
            pass
    if user_id_raw:
        try:
            user_id_val = int(user_id_raw)
            where_clauses.append("t.user_id = ?")
            params.append(user_id_val)
        except Exception:
            pass
    if account_id_raw:
        try:
            account_id_val = int(account_id_raw)
            where_clauses.append("t.account_id = ?")
            params.append(account_id_val)
        except Exception:
            pass
    if amount_min not in (None, ""):
        try:
            where_clauses.append("ABS(t.amount) >= ?")
            params.append(abs(float(amount_min)))
        except Exception:
            pass
    if amount_max not in (None, ""):
        try:
            where_clauses.append("ABS(t.amount) <= ?")
            params.append(abs(float(amount_max)))
        except Exception:
            pass
    if tags and tags.strip():
        tag_list = [tg.strip() for tg in tags.split(',') if tg.strip()]
        if tag_list:
            where_clauses.append("(" + " OR ".join(["t.tags LIKE ?"] * len(tag_list)) + ")")
            params.extend([f"%{tg}%" for tg in tag_list])

    # Restrict users to main users
    where_clauses.append(f"t.user_id IN ({user_ids})")

    where_sql = " WHERE " + " AND ".join(where_clauses)

    # Determine ORDER BY clause based on sort parameter
    order_by_map = {
        "date_desc": "t.date DESC, t.id DESC",
        "date_asc": "t.date ASC, t.id ASC",
        "amount_desc": "ABS(t.amount) DESC, t.date DESC",
        "amount_asc": "ABS(t.amount) ASC, t.date DESC",
        "category_asc": "c.name ASC, t.date DESC",
        "category_desc": "c.name DESC, t.date DESC",
        "user_asc": "u.name ASC, t.date DESC",
        "user_desc": "u.name DESC, t.date DESC",
        "account_asc": "a.name ASC, t.date DESC",
        "account_desc": "a.name DESC, t.date DESC",
    }
    order_by = order_by_map.get(sort_param, "t.date DESC, t.id DESC")

    total = db_conn.execute(f"SELECT COUNT(*) FROM transactions t{where_sql}", params).fetchone()[0]
    
    # Calculate total sum of filtered expenses (negative amounts only)
    total_sum = db_conn.execute(
        f"""
        SELECT COALESCE(SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END), 0)
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        {where_sql}
        """,
        params
    ).fetchone()[0]
    rows = db_conn.execute(
        f"""
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
        {where_sql}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        (*params, per_page, offset),
    ).fetchall()

    # For expenses page: exclude income categories from the dropdown
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute(f"SELECT id, name FROM users WHERE id IN ({user_ids}) ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()

    # The add-expense modal starts on the logged-in person and their usual account.
    session_user = getattr(request.state, "user", None) or request.session.get("user")
    me = find_person(household(db_conn), session_user)
    default_user_id = me["id"] if me else None
    default_account = default_account_id(db_conn, session_user)

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
        request,
        "finances/transactions.html",
        {
            "request": request,
            "transactions": rows,
            "categories": categories,
            "users": users,
            "accounts": accounts,
            "default_user_id": default_user_id,
            "default_account_id": default_account,
            "pagination": pagination,
            "total_sum": float(total_sum),
            "current_sort": sort_param,
            "show_sidebar": True,
        },
    )


# -----------------------------
# Finances: Card statement import (Max xlsx)
# -----------------------------
@router.get("/finances/transactions/import", response_class=HTMLResponse)
async def finances_transactions_import(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    # Same category list as the transactions page: expenses only.
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse(
        request,
        "finances/transactions_import.html",
        {
            "request": request,
            "categories": [dict(c) for c in categories],
            "users": household(db_conn),
            "accounts": [dict(a) for a in accounts],
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

    # Get main user IDs (works with both Hebrew and English names)
    user_ids = _get_main_user_ids(db_conn)

    total = db_conn.execute(
        f"""
        SELECT COUNT(*) FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.amount > 0 AND t.recurrence_id IS NULL
          AND t.user_id IN ({user_ids})
          AND c.name IN ('משכורת', 'קליניקה')
        """
    ).fetchone()[0]
    rows = db_conn.execute(
        f"""
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
          AND t.user_id IN ({user_ids})
          AND c.name IN ('משכורת', 'קליניקה')
        ORDER BY t.date DESC, t.id DESC
        LIMIT ? OFFSET ?
        """,
        (per_page, offset),
    ).fetchall()

    # For income page: show only income categories
    categories = db_conn.execute("SELECT id, name FROM categories WHERE name IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute(f"SELECT id, name FROM users WHERE id IN ({user_ids}) ORDER BY id").fetchall()
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
        request,
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


@router.post("/income", response_class=HTMLResponse)
async def create_income_form(
    request: Request,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    """Handle create income form submission and redirect back to income page.

    The income page exposes only income categories; we still force a positive sign.
    """
    form = await request.form()
    try:
        date_val = form.get("date")
        amount_raw = form.get("amount")
        category_raw = form.get("category_id")
        user_raw = form.get("user_id")
        notes_val = form.get("notes") or None
        tags_val = form.get("tags") or None

        amount_val = abs(float(amount_raw)) if amount_raw not in (None, "") else 0.0
        category_id = int(category_raw) if category_raw not in (None, "") else None
        user_id = int(user_raw) if user_raw not in (None, "") else None
        account_id = None  # income form does not supply account; store as NULL

        db_conn.execute(
            """
            INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (date_val, amount_val, category_id, user_id, account_id, notes_val, tags_val),
        )
        db_conn.commit()
    except Exception:
        # On failure, still navigate back to the income page; errors will be visible in logs
        logger.exception("Failed to create income via form")
    # Redirect back to the income listing
    return RedirectResponse(url="/finances/income", status_code=303)

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

    # Get main user IDs (works with both Hebrew and English names)
    user_ids = _get_main_user_ids(db_conn)

    base_sql = (
        """
        SELECT r.id, r.name, r.amount, r.frequency, r.next_charge_date, r.active,
               r.day_of_month, r.weekday,
               c.name AS category_name,
               u.name AS user_name,
               a.name AS account_name
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN accounts a ON r.account_id = a.id
        """
    )

    # Optional filters: month(for schedule), category_id, only_active; always restrict to main users
    where_clauses: list[str] = []
    params: list[Any] = []

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

    # Always scope to the main users
    where_clauses.append(f"r.user_id IN ({user_ids})")

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Fetch all rows (we will compute scheduled date and then apply month filter and paginate in Python)
    recs_all = db_conn.execute(base_sql + where_sql + " ORDER BY r.id DESC", (*params,)).fetchall()

    # Compute scheduled execution date for current month based on frequency/day_of_month/weekday
    import calendar as _calendar
    from datetime import date as _date

    # Resolve selected month (YYYY-MM). If provided, use it; otherwise default to current month
    month_str = request.query_params.get("month")
    today = _date.today()
    sel_year, sel_month = today.year, today.month
    if month_str:
        try:
            dt_obj = datetime.strptime(month_str, "%Y-%m")
            sel_year, sel_month = dt_obj.year, dt_obj.month
        except Exception:
            # ignore invalid value; keep today
            pass


    recs_enriched: list[dict[str, Any]] = []
    for r in recs_all or []:
        r_dict = dict(r)
        sched: _date | None = None
        try:
            freq = (r_dict.get("frequency") or "").lower()
            if freq == "monthly":
                d = int(r_dict.get("day_of_month") or 1)
                last = _calendar.monthrange(sel_year, sel_month)[1]
                d = max(1, min(last, d))
                sched = _date(sel_year, sel_month, d)
            elif freq == "weekly":
                wd = int(r_dict.get("weekday") if r_dict.get("weekday") is not None else 6)
                wd = max(0, min(6, wd))
                sched = _first_weekday_in_month(sel_year, sel_month, wd)
            elif freq == "yearly":
                # Use month/day from next_charge_date if present; fallback to Aug 1st
                mm, dd = 8, 1
                ncd = r_dict.get("next_charge_date")
                if ncd:
                    parts = str(ncd).split("-")
                    if len(parts) >= 3:
                        mm = max(1, min(12, int(parts[1])))
                        dd = max(1, min(_calendar.monthrange(sel_year, mm)[1], int(parts[2])))
                sched = _date(sel_year, mm, dd)
        except Exception:
            sched = None
        r_dict["scheduled_date"] = sched.isoformat() if sched else None
        recs_enriched.append(r_dict)

    # If month filter provided, keep only recurrences scheduled in that month
    if month_str:
        recs_enriched = [r for r in recs_enriched if r.get("scheduled_date") and r["scheduled_date"].startswith(f"{sel_year:04d}-{sel_month:02d}-")]

    # Pagination over the (possibly) filtered list
    total = len(recs_enriched)
    start = offset
    end = offset + per_page
    recs_enriched_page = recs_enriched[start:end]

    # Recurrences are expenses: exclude income categories
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute(f"SELECT id, name FROM users WHERE id IN ({user_ids}) ORDER BY id").fetchall()
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
        request,
        "pages/recurrences.html",
        {
            "request": request,
            "recurrences": recs_enriched_page,
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

    # Get main user IDs (works with both Hebrew and English names)
    user_ids = _get_main_user_ids(db_conn)

    base_sql = (
        """
        SELECT r.id, r.name, r.amount, r.frequency, r.next_charge_date, r.active,
               c.name AS category_name,
               u.name AS user_name,
               a.name AS account_name
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN accounts a ON r.account_id = a.id
        """
    )

    where_clauses: list[str] = ["r.active = 1"]
    params: list[Any] = []

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
    user_filter_sql = f" AND r.user_id IN ({user_ids})"
    recs = db_conn.execute(base_sql + where_sql + user_filter_sql + " ORDER BY r.id DESC LIMIT ? OFFSET ?", (*params, per_page, offset)).fetchall()

    # Active recurrences are expenses: exclude income categories
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute(f"SELECT id, name FROM users WHERE id IN ({user_ids}) ORDER BY id").fetchall()
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
        request,
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
    from datetime import date as _date
    from datetime import timedelta as _timedelta

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
    db_conn.execute(
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

    # Redirect back to the source page (active/all) using Referer when possible
    try:
        ref = request.headers.get("referer", "") or ""
        target = "/finances/recurrences/active" if "/finances/recurrences/active" in ref else "/finances/recurrences"
    except Exception:
        target = "/finances/recurrences"
    return RedirectResponse(url=target, status_code=303)


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
               r.category_id, r.user_id, r.account_id,
               c.name AS category_name, u.name AS user_name, a.name AS account_name
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        LEFT JOIN accounts a ON r.account_id = a.id
        WHERE r.id = ?
        """,
        (rec_id,),
    ).fetchone()
    return templates.TemplateResponse(
        request,
        "partials/recurrences/row.html",
        {"request": request, "r": row},
    )


@router.get("/recurrences/{rec_id}/edit-inline", response_class=HTMLResponse)
async def edit_recurrence_inline(
    request: Request,
    rec_id: int,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
):
    # Get main user IDs (works with both Hebrew and English names)
    user_ids = _get_main_user_ids(db_conn)

    row = db_conn.execute("SELECT * FROM recurrences WHERE id = ?", (rec_id,)).fetchone()
    # Edit recurrence: restrict to expense categories
    categories = db_conn.execute("SELECT id, name FROM categories WHERE TRIM(name) NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()
    users = db_conn.execute(f"SELECT id, name FROM users WHERE id IN ({user_ids}) ORDER BY id").fetchall()
    accounts = db_conn.execute("SELECT id, name FROM accounts ORDER BY name").fetchall()
    return templates.TemplateResponse(
        request,
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
    fields: dict[str, Any] = {}
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
    month: str | None = None,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    # Get main user IDs (works with both Hebrew and English names)
    user_ids = _get_main_user_ids(db_conn)

    # Resolve selected month (YYYY-MM), default to current
    today = date.today()
    default_ym = today.strftime("%Y-%m")
    selected_ym = default_ym
    if month:
        try:
            dt_obj = datetime.strptime(month, "%Y-%m")
            selected_ym = dt_obj.strftime("%Y-%m")
        except Exception:
            selected_ym = default_ym

    month_totals = db_conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN t.amount < 0 AND c.name NOT IN ('משכורת', 'קליניקה') AND COALESCE(c.is_saving, 0) = 0
                     THEN ABS(t.amount) ELSE 0 END) as total_expenses,
            SUM(CASE WHEN t.amount < 0 AND COALESCE(c.is_saving, 0) = 1
                     THEN ABS(t.amount) ELSE 0 END) as total_savings,
            SUM(CASE WHEN t.amount > 0 AND c.name IN ('משכורת', 'קליניקה')
                     THEN t.amount ELSE 0 END) as total_income,
            COUNT(*) as total_transactions
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = ?
          AND t.user_id IN ({user_ids})
        """,
        (selected_ym,)
    ).fetchone() or {"total_expenses": 0, "total_savings": 0, "total_income": 0, "total_transactions": 0}

    total_recurring_month = db_conn.execute(
        f"""
        SELECT COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) as total
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = ? AND t.recurrence_id IS NOT NULL
          AND t.user_id IN ({user_ids})
          AND COALESCE(c.is_saving, 0) = 0
        """,
        (selected_ym,)
    ).fetchone()[0]

    categories = db_conn.execute("SELECT id, name FROM categories WHERE name NOT IN ('משכורת','קליניקה') ORDER BY name").fetchall()

    # Monthly totals (6 months) for the bar chart are fetched via /api/statistics/monthly
    monthly_data = []

    # Category by month data for donut (last 6 months window, excluding income and savings)
    category_data_rows = db_conn.execute(
        f"""
        SELECT strftime('%Y-%m', t.date) AS month,
               c.name AS category,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS amount
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND COALESCE(c.is_saving, 0) = 0
          AND t.user_id IN ({user_ids})
        GROUP BY month, c.name
        ORDER BY month ASC, amount DESC
        """
    ).fetchall()
    category_data = [dict(row) for row in (category_data_rows or [])]

    # Top 5 regular (non-recurring) expenses for the last 6 months (largest absolute amounts)
    top_regular_expenses_rows = db_conn.execute(
        f"""
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
          AND COALESCE(c.is_saving, 0) = 0
          AND t.user_id IN ({user_ids})
        ORDER BY ABS(t.amount) DESC, t.date DESC
        LIMIT 5
        """
    ).fetchall()
    top_regular_expenses = [dict(row) for row in (top_regular_expenses_rows or [])]

    # Cash vs Credit per user for the last 6 months, plus total per user
    cash_credit_rows = db_conn.execute(
        f"""
        SELECT u.name AS user_name,
               COALESCE(a.name, 'לא מוגדר') AS account_name,
               SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS total
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND COALESCE(c.is_saving, 0) = 0
          AND t.user_id IN ({user_ids})
        GROUP BY u.name, a.name
        ORDER BY u.name ASC
        """
    ).fetchall()

    # Normalize cash/credit per user to a compact structure for the template table
    cash_credit_user_totals: list[dict[str, Any]] = []
    user_map: dict[str, dict[str, float]] = {}
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
        f"""
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
        WHERE strftime('%Y-%m', t.date) = ?
          AND t.amount < 0
          AND t.recurrence_id IS NOT NULL
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND COALESCE(c.is_saving, 0) = 0
          AND t.user_id IN ({user_ids})
        ORDER BY ABS(t.amount) DESC, t.date DESC
        LIMIT 10
        """,
        (selected_ym,)
    ).fetchall()
    recurring_expenses = [dict(row) for row in (recurring_expenses_rows or [])]

    # Active recurring definitions with frequency
    active_recurrences_rows = db_conn.execute(
        f"""
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
          AND r.user_id IN ({user_ids})
        ORDER BY r.name ASC
        """
    ).fetchall()
    active_recurrences = [dict(row) for row in (active_recurrences_rows or [])]

    # -----------------------------
    # Savings analytics
    # Savings are transactions in categories flagged is_saving (e.g. "חסכונות").
    # They behave like a fixed monthly deduction (~1-2 charges/month), so we show
    # a 6-month trend, headline KPIs and the actual deductions for the month.
    # -----------------------------
    # Build the trailing-6-months window (consistent with the rest of the page).
    _base = today.replace(day=1)
    last_6_months: list[str] = []
    for _i in range(5, -1, -1):
        _y, _m = _base.year, _base.month - _i
        while _m <= 0:
            _m += 12
            _y -= 1
        last_6_months.append(f"{_y:04d}-{_m:02d}")

    savings_trend_rows = db_conn.execute(
        f"""
        SELECT strftime('%Y-%m', t.date) AS month,
               COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', 'start of month', '-5 months')
          AND COALESCE(c.is_saving, 0) = 1
          AND t.user_id IN ({user_ids})
        GROUP BY month
        """
    ).fetchall()
    _savings_lookup = {row["month"]: float(row["total"] or 0) for row in (savings_trend_rows or [])}
    _heb_months = ["ינו", "פבר", "מרץ", "אפר", "מאי", "יונ", "יול", "אוג", "ספט", "אוק", "נוב", "דצמ"]
    savings_trend = [
        {"month": ym, "label": _heb_months[int(ym[5:7]) - 1], "total": _savings_lookup.get(ym, 0.0)}
        for ym in last_6_months
    ]
    savings_trend_max = max((item["total"] for item in savings_trend), default=0.0)
    savings_total_6m = sum(item["total"] for item in savings_trend)
    savings_avg_6m = savings_total_6m / 6 if savings_trend else 0.0

    # Savings deductions for the selected month (the actual fixed charges)
    savings_deductions_rows = db_conn.execute(
        f"""
        SELECT t.date,
               ABS(t.amount) AS amount,
               c.name AS category,
               u.name AS user,
               t.notes,
               r.name AS recurrence_name
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN recurrences r ON t.recurrence_id = r.id
        WHERE strftime('%Y-%m', t.date) = ?
          AND t.amount < 0
          AND COALESCE(c.is_saving, 0) = 1
          AND t.user_id IN ({user_ids})
        ORDER BY ABS(t.amount) DESC, t.date DESC
        """,
        (selected_ym,)
    ).fetchall()
    savings_deductions = [dict(row) for row in (savings_deductions_rows or [])]

    _savings_month = float(month_totals["total_savings"] or 0)
    _income_month = float(month_totals["total_income"] or 0)
    savings_rate = (_savings_month / _income_month * 100) if _income_month > 0 else 0.0
    # Change vs previous month within the trend window (penultimate vs last)
    savings_change = 0.0
    if len(savings_trend) >= 2 and savings_trend[-2]["total"] > 0:
        savings_change = ((savings_trend[-1]["total"] - savings_trend[-2]["total"]) / savings_trend[-2]["total"]) * 100

    # --- Mobile מגמות (< lg): 6 months ending at the selected month ---
    sel_y, sel_m = map(int, selected_ym.split("-"))
    trend_months: list[str] = []
    ty, tm = sel_y, sel_m
    for _ in range(6):
        trend_months.append(f"{ty:04d}-{tm:02d}")
        ty, tm = (ty, tm - 1) if tm > 1 else (ty - 1, 12)
    trend_months.reverse()
    window_end = date(sel_y + (1 if sel_m == 12 else 0), 1 if sel_m == 12 else sel_m + 1, 1)
    trend_rows = db_conn.execute(
        f"""
        SELECT strftime('%Y-%m', t.date) AS month,
               SUM(CASE WHEN t.amount < 0 AND c.name NOT IN ('משכורת', 'קליניקה') AND COALESCE(c.is_saving, 0) = 0
                        THEN ABS(t.amount) ELSE 0 END) AS total
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.date >= ? AND t.date < ?
          AND t.user_id IN ({user_ids})
        GROUP BY month
        """,
        (f"{trend_months[0]}-01", window_end.isoformat()),
    ).fetchall()
    trend_lookup = {row["month"]: float(row["total"] or 0) for row in trend_rows}
    trend_values = [trend_lookup.get(ym, 0.0) for ym in trend_months]
    trend_peak = max(trend_values)
    peak_index = trend_values.index(trend_peak) if trend_peak > 0 else None
    months_with_data = [v for v in trend_values if v > 0]
    # Months with nothing recorded (before the app was in use) would drag the average down.
    trend_average = sum(months_with_data) / len(months_with_data) if months_with_data else 0.0
    selected_total = trend_values[-1]

    average_delta = None
    if trend_average > 0:
        vs_average = (selected_total - trend_average) / trend_average * 100.0
        if abs(vs_average) >= 0.05:
            average_delta = {
                "text": f"{'▲' if vs_average > 0 else '▼'} {abs(vs_average):.1f}%",
                "color": "#dc2626" if vs_average > 0 else "#16a34a",
            }

    trend_bars = []
    for idx, ym in enumerate(trend_months):
        value = trend_values[idx]
        is_selected = idx == len(trend_months) - 1
        trend_bars.append({
            "month": ym,
            "label": hd.HEBREW_MONTHS_SHORT[int(ym[5:7]) - 1],
            "total": value,
            "height": round(value / trend_peak * 100.0, 1) if trend_peak > 0 else 0.0,
            "selected": is_selected,
            "color": "#2563eb" if is_selected else ("#93c5fd" if idx == peak_index else "#dbeafe"),
            "href": f"/finances/statistics?month={ym}",
        })

    prev_trend_ym = trend_months[-2]
    biggest_rows = db_conn.execute(
        f"""
        SELECT c.name AS category,
               SUM(CASE WHEN strftime('%Y-%m', t.date) = ? THEN ABS(t.amount) ELSE 0 END) AS total,
               SUM(CASE WHEN strftime('%Y-%m', t.date) = ? THEN 1 ELSE 0 END) AS tx_count,
               SUM(CASE WHEN strftime('%Y-%m', t.date) = ? THEN ABS(t.amount) ELSE 0 END) AS prev_total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.amount < 0
          AND c.name NOT IN ('משכורת', 'קליניקה')
          AND COALESCE(c.is_saving, 0) = 0
          AND t.user_id IN ({user_ids})
          AND strftime('%Y-%m', t.date) IN (?, ?)
        GROUP BY c.name
        HAVING total > 0
        ORDER BY total DESC
        LIMIT 3
        """,
        (selected_ym, selected_ym, prev_trend_ym, selected_ym, prev_trend_ym),
    ).fetchall()
    category_emoji = {
        "סופר": "🛒", "חתונה": "💍", "רכב": "🚗", "אוכל בחוץ": "🍽️", "הוצאות בית": "🏠",
        "בריאות": "🩺", "פנאי": "🎉", "תחבורה": "🚌", "שיפוץ": "🏡",
    }
    tile_colors = ("#dbeafe", "#ffe4e6", "#ede9fe")
    biggest_categories = []
    for rank, row in enumerate(biggest_rows):
        cat_total = float(row["total"] or 0)
        prev_total = float(row["prev_total"] or 0)
        tx_count = int(row["tx_count"] or 0)
        delta = None
        if prev_total > 0:
            change = (cat_total - prev_total) / prev_total * 100.0
            if round(abs(change)) == 0:
                delta = {"text": "קבוע", "color": "#9ca3af"}
            else:
                delta = {
                    "text": f"{'▲' if change > 0 else '▼'} {abs(change):.0f}%",
                    "color": "#dc2626" if change > 0 else "#16a34a",
                }
        biggest_categories.append({
            "name": row["category"],
            "emoji": category_emoji.get(row["category"], "💳"),
            "tile": tile_colors[rank],
            "total": cat_total,
            "count_label": "עסקה אחת" if tx_count == 1 else f"{tx_count} עסקאות",
            "delta": delta,
        })

    mobile = {
        "month_label": f"{hd.HEBREW_MONTHS[sel_m - 1]} {sel_y}",
        "average": trend_average,
        "average_delta": average_delta,
        "bars": trend_bars,
        "biggest": biggest_categories,
    }

    return templates.TemplateResponse(
        request,
        "finances/statistics.html",
        {
            "request": request,
            "selected_month": selected_ym,
            "total_expenses_month": float(month_totals["total_expenses"] or 0),
            "total_savings_month": float(month_totals["total_savings"] or 0),
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
            "savings_trend": savings_trend,
            "savings_trend_max": savings_trend_max,
            "savings_total_6m": savings_total_6m,
            "savings_avg_6m": savings_avg_6m,
            "savings_rate": savings_rate,
            "savings_change": savings_change,
            "savings_deductions": savings_deductions,
            "show_sidebar": True,
            "mobile": mobile,
        },
    )


# -----------------------------
# Finances: Statistics Drilldown
# -----------------------------
@router.get("/finances/statistics/drilldown", response_class=HTMLResponse)
async def finances_statistics_drilldown(
    request: Request,
    metric: str | None = None,
    category: str | None = None,
    month: str | None = None,
    partial: bool = False,
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> HTMLResponse:
    """Temporary drilldown table for KPIs on the statistics page.

    Supported metric values:
    - income: all income transactions in selected month
    - expenses: all expenses (regular + recurring) in selected month
    - transactions: all transactions in selected month
    - recurring: only recurring expenses in selected month
    
    Supported category:
    - category name (string) to filter by category (implies date range check)
    """
    # Resolve selected month
    today = date.today()
    default_ym = today.strftime("%Y-%m")
    selected_ym = default_ym
    if month:
        try:
            dt_obj = datetime.strptime(month, "%Y-%m")
            selected_ym = dt_obj.strftime("%Y-%m")
        except Exception:
            selected_ym = default_ym

    # Restrict to the two main users
    user_ids = _get_main_user_ids(db_conn)

    base_sql = (
        """
        SELECT 
            t.id,
            t.date,
            t.amount,
            c.name AS category,
            u.name AS user,
            COALESCE(a.name, 'לא מוגדר') AS account,
            t.notes,
            COALESCE(r.name, t.tags) AS tags,
            r.name AS recurrence_name,
            COALESCE(r.name, t.tags) AS display_tags
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN recurrences r ON t.recurrence_id = r.id
        WHERE strftime('%Y-%m', t.date) = ?
          AND t.user_id IN (
        """
        + user_ids
        + ")"
    )

    metric_key = (metric or "").strip().lower()
    title = "עסקאות החודש"
    where_extra = ""
    params = [selected_ym]

    if category:
        title = f"הוצאות - {category}"
        # Filter by category name
        # Note: category name comes from the chart, which comes from c.name
        where_extra += " AND c.name = ?"
        params.append(category)
        # Usually implies expenses, but we let the DB decide based on amount if needed?
        # Typically charts show absolute amounts for expenses.
        # But let's assume if we drill down by category we just want transactions for that category.
        
    elif metric_key == "income":
        title = "הכנסות החודש"
        where_extra = " AND t.amount > 0 AND c.name IN ('משכורת', 'קליניקה')"
    elif metric_key == "expenses":
        title = "הוצאות החודש"
        where_extra = " AND t.amount < 0 AND c.name NOT IN ('משכורת', 'קליניקה') AND COALESCE(c.is_saving, 0) = 0"
    elif metric_key == "savings":
        title = "חסכון החודש"
        where_extra = " AND t.amount < 0 AND COALESCE(c.is_saving, 0) = 1"
    elif metric_key == "recurring":
        title = "הוצאות קבועות החודש"
        where_extra = " AND t.amount < 0 AND t.recurrence_id IS NOT NULL"

    query = base_sql + where_extra + " ORDER BY t.date DESC, t.id DESC"
    rows = db_conn.execute(query, tuple(params)).fetchall()
    rows_dict = [dict(r) for r in (rows or [])]

    template_name = "partials/stats/drilldown_table.html" if partial else "finances/statistics_drilldown.html"

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "request": request,
            "show_sidebar": not partial,
            "selected_month": selected_ym,
            "metric": metric_key,
            "title": title,
            "rows": rows_dict,
        },
    )


# -----------------------------
# Finances: Backup page
# -----------------------------
@router.get("/finances/backup", response_class=HTMLResponse)
async def finances_backup(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "finances/backup.html",
        {
            "request": request,
            "show_sidebar": True,
        },
    )
