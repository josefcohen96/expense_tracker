# app/backend/app/api/statistics.py
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from ..db import get_db_conn
from ..services.cache_service import cache_service
from starlette.templating import Jinja2Templates
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, Any
import sqlite3
import logging

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="../frontend/templates")

router = APIRouter(prefix="/api/statistics", tags=["statistics"])

def get_last_6_months():
    today = datetime.today().replace(day=1)
    months = []
    for i in range(5, -1, -1):
        month = (today - relativedelta(months=i)).strftime('%Y-%m')
        months.append(month)
    return months

@router.get("/page", response_class=HTMLResponse)
def statistics_page(request: Request, db_conn=Depends(get_db_conn)):
    return statistics(request, db_conn)

@router.get("", response_class=HTMLResponse)
def statistics(request: Request, db_conn=Depends(get_db_conn)):
    cur = db_conn.cursor()
    
    # Get last 6 months as strings
    last_6_months = get_last_6_months()

    # Get all categories
    categories_rows = cur.execute("SELECT name FROM categories").fetchall()
    all_categories = [row["name"] for row in categories_rows]

    # Get monthly sums per category
    monthly_raw = cur.execute("""
        SELECT strftime('%Y-%m', t.date) AS ym, ABS(SUM(t.amount)) AS expenses, c.name AS category
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NULL
        GROUP BY ym, c.name
        ORDER BY ym, c.name
    """).fetchall()

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

    # 5 ההוצאות הכי גדולות ב-3 חודשים האחרונים (עם cache)
    cache_key = "top_expenses_3months"
    top_expenses = cache_service.get(cache_key)
    
    if top_expenses is None:
        # Cache miss - fetch from database
        
        # Now let's check the actual top expenses query
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
            AND t.recurrence_id IS NULL
            ORDER BY ABS(t.amount) DESC
            LIMIT 5
        """).fetchall()
        
        # Cache for 5 minutes (300 seconds)
        top_expenses_dict = [dict(row) for row in top_expenses]
        cache_service.set(cache_key, top_expenses_dict, ttl_seconds=300)
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
        AND t.recurrence_id IS NULL
        GROUP BY c.name
    """).fetchall()

    # הוצאות לפי משתמש
    users = cur.execute("""
        SELECT u.name AS user_name, ABS(SUM(t.amount)) AS total
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NULL
        GROUP BY u.name
        ORDER BY total DESC
    """).fetchall()

    # הוצאות קבועות לפי משתמש (6 חודשים אחרונים)
    recurring_users = cur.execute("""
        SELECT u.name AS user_name, ABS(SUM(t.amount)) AS total
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NOT NULL
        GROUP BY u.name
        ORDER BY total DESC
    """).fetchall()
    

    template_data = {
        "request": request,
        "monthly_expenses": monthly,
        "top_expenses": [dict(row) for row in top_expenses],
        "category_expenses": [dict(row) for row in categories],
        "user_expenses": [dict(row) for row in users],
        "recurring_user_expenses": [dict(row) for row in recurring_users],
    }
    
    logger.info("=== STATISTICS PAGE REQUEST END ===")
    
    return templates.TemplateResponse("pages/statistics.html", template_data)

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
            AND t.recurrence_id IS NULL
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
            AND t.recurrence_id IS NULL
            GROUP BY ym
            ORDER BY ym
        """, (category,)).fetchall()
        lookup = {row["ym"]: row["expenses"] for row in rows}
        result = [
            {"ym": ym, "expenses": lookup.get(ym, 0)}
            for ym in last_6_months
        ]
    return JSONResponse(result)

@router.get("/debug")
def debug_statistics(db_conn=Depends(get_db_conn)):
    """Debug endpoint to check database data directly."""
    cur = db_conn.cursor()
    
    # Check current date and 3 months ago
    from datetime import datetime, timedelta
    from dateutil.relativedelta import relativedelta
    
    now = datetime.now()
    three_months_ago = now - relativedelta(months=3)
    three_months_ago_sql = three_months_ago.strftime('%Y-%m-%d')
    
    # Check total transactions
    total_tx = cur.execute("SELECT COUNT(*) FROM transactions WHERE recurrence_id IS NULL").fetchone()[0]
    
    # Check transactions in last 3 months
    last_3_months = cur.execute("""
        SELECT COUNT(*) as count,
               COUNT(CASE WHEN amount < 0 THEN 1 END) as negative_count,
               COUNT(CASE WHEN amount > 0 THEN 1 END) as positive_count,
               MIN(date) as min_date,
               MAX(date) as max_date,
               SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as total_negative,
               SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_positive
        FROM transactions 
        WHERE date >= date('now', '-3 months')
        AND recurrence_id IS NULL
    """).fetchone()
    
    # Check some sample transactions to see their dates
    sample_tx = cur.execute("""
        SELECT id, date, amount, notes 
        FROM transactions 
        WHERE recurrence_id IS NULL
        ORDER BY date DESC 
        LIMIT 10
    """).fetchall()
    
    # Check the exact query that's used for top expenses
    top_expenses_debug = cur.execute("""
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
    
    # Check cache status
    cache_key = "top_expenses_3months"
    cached_data = cache_service.get(cache_key)
    
    return JSONResponse({
        "current_date": now.strftime('%Y-%m-%d'),
        "three_months_ago": three_months_ago_sql,
        "sql_three_months_ago": cur.execute('SELECT date(\'now\', \'-3 months\')').fetchone()[0],
        "total_transactions": total_tx,
        "last_3_months": dict(last_3_months),
        "sample_transactions": [dict(row) for row in sample_tx],
        "top_expenses_debug": [dict(row) for row in top_expenses_debug],
        "cache_status": "HIT" if cached_data is not None else "MISS",
        "cache_data_length": len(cached_data) if cached_data is not None else 0
    })


@router.get("/api/stats/recurring-user-expenses")
async def api_recurring_user_expenses(
    db_conn: sqlite3.Connection = Depends(get_db_conn),
) -> Dict[str, Any]:
    """API endpoint להוצאות קבועות לפי חודש ב-6 חודשים האחרונים"""
    cur = db_conn.cursor()
    
    # הוצאות קבועות לפי חודש
    recurring_monthly = cur.execute("""
        SELECT strftime('%Y-%m', t.date) AS month,
               ABS(SUM(t.amount)) AS total
        FROM transactions t
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NOT NULL
        GROUP BY strftime('%Y-%m', t.date)
        ORDER BY month ASC
    """).fetchall()
    
    result = {
        "recurring_user_expenses": [dict(row) for row in recurring_monthly],
    }
    
    return result
