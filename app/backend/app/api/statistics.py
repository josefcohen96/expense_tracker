"""
Statistics API endpoints for expense tracking and reporting.
"""

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from ..db import get_db_conn
from ..services.cache_service import cache_service
from starlette.templating import Jinja2Templates
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, Any, List
import sqlite3
import logging

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="../frontend/templates")

router = APIRouter(prefix="/api/statistics", tags=["statistics"])

def get_last_6_months() -> List[str]:
    """Get the last 6 months as YYYY-MM format strings."""
    today = datetime.today().replace(day=1)
    months = []
    for i in range(5, -1, -1):
        month = (today - relativedelta(months=i)).strftime('%Y-%m')
        months.append(month)
    return months

@router.get("/page", response_class=HTMLResponse)
def statistics_page(request: Request, db_conn=Depends(get_db_conn)):
    """Statistics page endpoint."""
    return statistics(request, db_conn)

@router.get("", response_class=HTMLResponse)
def statistics(request: Request, db_conn=Depends(get_db_conn)):
    """Main statistics endpoint - returns HTML with all statistics data."""
    cur = db_conn.cursor()
    
    # Get last 6 months as strings
    last_6_months = get_last_6_months()

    # Get all categories
    categories_rows = cur.execute("SELECT name FROM categories").fetchall()
    all_categories = [row["name"] for row in categories_rows]

    # Get monthly sums per category (only regular expenses, excluding recurring expenses and income categories)
    monthly_raw = cur.execute("""
        SELECT strftime('%Y-%m', t.date) AS ym, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS expenses, c.name AS category
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NULL
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY ym, c.name
        ORDER BY ym, c.name
    """).fetchall()

    # Build a lookup {(ym, category): expenses}
    lookup = {(row["ym"], row["category"]): row["expenses"] for row in monthly_raw}

    # Build full monthly list for each category (including zeros, excluding income categories)
    monthly = []
    expense_categories = [cat for cat in all_categories if cat not in ['משכורת', 'קליניקה']]
    
    for ym in last_6_months:
        for cat in expense_categories:
            monthly.append({
                "ym": ym,
                "expenses": lookup.get((ym, cat), 0),
                "category": cat
            })
        # total for all expense categories only
        total = sum(lookup.get((ym, cat), 0) for cat in expense_categories)
        monthly.append({"ym": ym, "expenses": total, "category": "total"})

    # Top 5 expenses in last 3 months (with cache)
    top_expenses = _get_top_expenses(cur)

    # Expenses by category (including both regular and recurring expenses, excluding income categories)
    categories = cur.execute("""
        SELECT c.name AS category, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY c.name
    """).fetchall()

    # Expenses by user (including both regular and recurring expenses, excluding income categories)
    users = cur.execute("""
        SELECT u.name AS user_name, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY u.name
        ORDER BY total DESC
    """).fetchall()

    # Recurring expenses by user (last 6 months, excluding income categories)
    recurring_users = cur.execute("""
        SELECT u.name AS user_name, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NOT NULL
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY u.name
        ORDER BY total DESC
    """).fetchall()
    
    # Recurring expenses by month (last 6 months)
    recurring_monthly = _get_recurring_monthly_expenses(cur, last_6_months)

    # Get cash vs credit breakdown for last 6 months (only regular expenses, excluding recurring expenses and income categories)
    cash_vs_credit = _get_cash_vs_credit_data(cur)

    # Calculate summary statistics for the current month (including both regular and recurring expenses)
    try:
        current_month_expenses = cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        current_month_expenses = {'total': 0}
    
    try:
        previous_month_expenses = cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now', '-1 month')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        previous_month_expenses = {'total': 0}
    
    # Get total expenses for last 6 months (including both regular and recurring expenses)
    try:
        total_expenses_6months = cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now', '-6 months')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        total_expenses_6months = {'total': 0}
    
    try:
        current_month_income = cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        current_month_income = {'total': 0}
    
    try:
        previous_month_income = cur.execute("""
            SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now', '-1 month')
            AND c.name IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        previous_month_income = {'total': 0}
    
    # Get transaction count for current month (including both regular and recurring transactions)
    try:
        current_month_transactions = cur.execute("""
            SELECT COUNT(*) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        current_month_transactions = {'total': 0}
    
    # Get regular transactions count for current month (excluding recurring transactions)
    try:
        current_month_regular = cur.execute("""
            SELECT COUNT(*) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            AND t.recurrence_id IS NULL
        """).fetchone()
    except Exception as e:
        current_month_regular = {'total': 0}
    
    # Get recurring transactions count for current month
    try:
        current_month_recurring = cur.execute("""
            SELECT COUNT(*) as total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            AND t.recurrence_id IS NOT NULL
        """).fetchone()
    except Exception as e:
        current_month_recurring = {'total': 0}
    
    # Count active categories this month
    try:
        categories_count = cur.execute("""
            SELECT COUNT(DISTINCT c.id) as count
            FROM categories c
            JOIN transactions t ON c.id = t.category_id
            WHERE strftime('%Y-%m', t.date) = strftime('%Y-%m', 'now')
            AND c.name NOT IN ('משכורת', 'קליניקה')
        """).fetchone()
    except Exception as e:
        categories_count = {'count': 0}
    
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

    template_data = {
        "request": request,
        "show_sidebar": True,
        "monthly_expenses": monthly,
        "top_expenses": [dict(row) for row in top_expenses],
        "category_expenses": [dict(row) for row in categories],
        "user_expenses": [dict(row) for row in users],
        "recurring_user_expenses": [dict(row) for row in recurring_users],
        "recurring_monthly": recurring_monthly,
        "cash_vs_credit": cash_vs_credit,
        "total_expenses_month": current_month_expenses['total'],
        "total_income_month": current_month_income['total'],
        "balance_month": balance_month,
        "expenses_change": expenses_change,
        "income_change": income_change,
        "balance_change": balance_change,
        "total_transactions_month": current_month_transactions['total'],
        "total_recurring_month": current_month_recurring['total'],
        "total_regular_month": current_month_regular['total'],
        "total_expenses_6months": total_expenses_6months['total'],
        "categories_count": categories_count['count'],
    }
    
    logger.info("=== STATISTICS PAGE REQUEST END ===")
    logger.info(f"Total expenses month: {template_data.get('total_expenses_month', 0)}")
    logger.info(f"Total income month: {template_data.get('total_income_month', 0)}")
    logger.info(f"Total transactions month: {template_data.get('total_transactions_month', 0)}")
    logger.info(f"Total recurring month: {template_data.get('total_recurring_month', 0)}")
    logger.info(f"Total regular month: {template_data.get('total_regular_month', 0)}")
    
    return templates.TemplateResponse("finances/statistics.html", template_data)

def _get_top_expenses(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    """Get top 5 expenses from last 3 months with caching."""
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
            AND t.amount < 0  -- Only expenses (negative amounts)
            AND c.name NOT IN ('משכורת', 'קליניקה')
            ORDER BY ABS(t.amount) DESC
            LIMIT 5
        """).fetchall()
        
        # Cache for 5 minutes (300 seconds)
        top_expenses_dict = [dict(row) for row in top_expenses]
        cache_service.set(cache_key, top_expenses_dict, ttl_seconds=300)
        return top_expenses_dict
    else:
        # Cache hit - convert back to list of dicts if needed
        if isinstance(top_expenses, list) and top_expenses and isinstance(top_expenses[0], dict):
            return top_expenses
        else:
            return [dict(row) for row in top_expenses]

def _get_recurring_monthly_expenses(cur: sqlite3.Cursor, last_6_months: List[str]) -> List[Dict[str, Any]]:
    """Get recurring expenses by month for the last 6 months (excluding income categories)."""
    recurring_monthly = cur.execute("""
        SELECT strftime('%Y-%m', t.date) AS month, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NOT NULL
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY strftime('%Y-%m', t.date)
        ORDER BY month
    """).fetchall()
    
    # Build full monthly list for recurrences (including zeros)
    recurring_lookup = {row["month"]: row["total"] for row in recurring_monthly}
    recurring_monthly_full = []
    for ym in last_6_months:
        recurring_monthly_full.append({
            "month": ym,
            "total": recurring_lookup.get(ym, 0)
        })
    
    return recurring_monthly_full

def _get_cash_vs_credit_data(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    """Get cash vs credit breakdown for last 6 months (including both regular and recurring expenses, excluding income categories)."""
    # First get by user and account
    try:
        cash_vs_credit_by_user = cur.execute("""
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
        cash_vs_credit_totals = cur.execute("""
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
    
    return cash_vs_credit

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
    """API endpoint for monthly expenses data."""
    cur = db_conn.cursor()
    last_6_months = get_last_6_months()

    if category == "total":
        # Total expenses for each month (including both regular and recurring expenses, excluding income categories)
        rows = cur.execute("""
            SELECT strftime('%Y-%m', t.date) AS ym, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS expenses
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now', '-6 months')
            AND c.name NOT IN ('משכורת', 'קליניקה')
            GROUP BY ym
            ORDER BY ym
        """).fetchall()
        lookup = {row["ym"]: row["expenses"] for row in rows}
        result = [
            {"ym": ym, "expenses": lookup.get(ym, 0)}
            for ym in last_6_months
        ]
    else:
        # Specific category (including both regular and recurring expenses)
        rows = cur.execute("""
            SELECT strftime('%Y-%m', t.date) AS ym, COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) AS expenses
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.date >= date('now', '-6 months')
            AND c.name = ?
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
    
    # Check total transactions (including both regular and recurring expenses)
    total_tx = cur.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    
    # Check transactions in last 3 months (including both regular and recurring expenses)
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
    """).fetchone()
    
    # Check some sample transactions to see their dates (including both regular and recurring expenses)
    sample_tx = cur.execute("""
        SELECT id, date, amount, notes 
        FROM transactions 
        ORDER BY date DESC 
        LIMIT 10
    """).fetchall()
    
    # Check the exact query that's used for top expenses (including both regular and recurring expenses)
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


@router.get("/recurrences")
def recurrences_monthly_api(db_conn=Depends(get_db_conn)):
    """API endpoint for recurring expenses by month for last 6 months"""
    cur = db_conn.cursor()
    last_6_months = get_last_6_months()

    # Get recurring expenses by month
    rows = cur.execute("""
        SELECT strftime('%Y-%m', t.date) AS month, ABS(SUM(t.amount)) AS total
        FROM transactions t
        WHERE t.date >= date('now', '-6 months')
        AND t.recurrence_id IS NOT NULL
        GROUP BY strftime('%Y-%m', t.date)
        ORDER BY month
    """).fetchall()
    
    lookup = {row["month"]: row["total"] for row in rows}
    result = [
        {"month": ym, "total": lookup.get(ym, 0)}
        for ym in last_6_months
    ]
    return JSONResponse(result)
