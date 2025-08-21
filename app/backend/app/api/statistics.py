# app/backend/app/api/statistics.py
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from ..db import get_db_conn
from ..services.cache_service import cache_service
from starlette.templating import Jinja2Templates
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

templates = Jinja2Templates(directory="app/frontend/templates")

router = APIRouter(prefix="/statistics", tags=["statistics"])

def get_last_6_months():
    today = datetime.today().replace(day=1)
    months = []
    for i in range(5, -1, -1):
        month = (today - relativedelta(months=i)).strftime('%Y-%m')
        months.append(month)
    return months

@router.get("", response_class=HTMLResponse)
def statistics(request: Request, db_conn=Depends(get_db_conn)):
    cur = db_conn.cursor()

    # Get last 6 months as strings
    last_6_months = get_last_6_months()
    print("last_6_months:", last_6_months)

    # Get all categories
    categories_rows = cur.execute("SELECT name FROM categories").fetchall()
    all_categories = [row["name"] for row in categories_rows]
    print("all_categories:", all_categories)

    # Get monthly sums per category
    monthly_raw = cur.execute("""
        SELECT strftime('%Y-%m', t.date) AS ym, ABS(SUM(t.amount)) AS expenses, c.name AS category
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        GROUP BY ym, c.name
        ORDER BY ym, c.name
    """).fetchall()
    print("monthly_raw:", [dict(row) for row in monthly_raw])

    # Build a lookup {(ym, category): expenses}
    lookup = {(row["ym"], row["category"]): row["expenses"] for row in monthly_raw}

    # Build full monthly list for each category (including zeros)
    monthly = []
    for ym in last_6_months:
        for cat in all_categories:
            monthly.append({
                "ym": ym,
                "expenses": lookup.get((ym, cat), 0),
                "category": cat
            })
        # total for all categories
        total = sum(lookup.get((ym, cat), 0) for cat in all_categories)
        monthly.append({"ym": ym, "expenses": total, "category": "total"})
    print("monthly_expenses to frontend:", monthly)

    # 5 ההוצאות הכי גדולות ב-3 חודשים האחרונים (עם cache)
    cache_key = "top_expenses_3months"
    top_expenses = cache_service.get(cache_key)
    
    if top_expenses is None:
        # Cache miss - fetch from database
        top_expenses = cur.execute("""
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
            ORDER BY ABS(t.amount) DESC
            LIMIT 5
        """).fetchall()
        
        # Cache for 5 minutes (300 seconds)
        cache_service.set(cache_key, [dict(row) for row in top_expenses], ttl_seconds=300)
    else:
        # Cache hit - convert back to list of dicts if needed
        if isinstance(top_expenses, list) and top_expenses and isinstance(top_expenses[0], dict):
            pass  # Already in correct format
        else:
            top_expenses = [dict(row) for row in top_expenses]

    # הוצאות לפי קטגוריה
    categories = cur.execute("""
        SELECT c.name AS category, ABS(SUM(t.amount)) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        GROUP BY c.name
    """).fetchall()

    print("category_expenses to frontend:", [dict(row) for row in categories])

    # דוגמה להדפסת כל התנועות
    transactions = cur.execute("SELECT * FROM transactions").fetchall()
    print("All transactions:", [dict(row) for row in transactions])

    # דוגמה להדפסת כל הקטגוריות
    categories_rows = cur.execute("SELECT * FROM categories").fetchall()
    print("All categories:", [dict(row) for row in categories_rows])

    # דוגמה להדפסת כל המשתמשים
    users_rows = cur.execute("SELECT * FROM users").fetchall()
    print("All users:", [dict(row) for row in users_rows])

    return templates.TemplateResponse("statistics.html", {
        "request": request,
        "monthly_expenses": monthly,
        "top_expenses": [dict(row) for row in top_expenses],
        "category_expenses": [dict(row) for row in categories],
    })

@router.post("/clear-cache")
def clear_statistics_cache():
    """Clear statistics cache when new data is added."""
    cache_service.invalidate("top_expenses_3months")
    return JSONResponse({"message": "Cache cleared successfully"})

@router.get("/cache-stats")
def get_cache_stats():
    """Get cache statistics for debugging."""
    return JSONResponse(cache_service.get_stats())

@router.get("/monthly")
def monthly_expenses_api(category: str = Query("total"), db_conn=Depends(get_db_conn)):
    cur = db_conn.cursor()
    last_6_months = get_last_6_months()

    if category == "total":
        # סכום כולל לכל חודש
        rows = cur.execute("""
            SELECT strftime('%Y-%m', t.date) AS ym, ABS(SUM(t.amount)) AS expenses
            FROM transactions t
            WHERE t.date >= date('now', '-6 months')
            GROUP BY ym
            ORDER BY ym
        """).fetchall()
        lookup = {row["ym"]: row["expenses"] for row in rows}
        result = [
            {"ym": ym, "expenses": lookup.get(ym, 0)}
            for ym in last_6_months
        ]
    else:
        # סכום לפי קטגוריה לכל חודש
        rows = cur.execute("""
            SELECT strftime('%Y-%m', t.date) AS ym, ABS(SUM(t.amount)) AS expenses
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now', '-6 months') AND c.name = ?
            GROUP BY ym
            ORDER BY ym
        """, (category,)).fetchall()
        lookup = {row["ym"]: row["expenses"] for row in rows}
        result = [
            {"ym": ym, "expenses": lookup.get(ym, 0)}
            for ym in last_6_months
        ]
    return JSONResponse(result)
