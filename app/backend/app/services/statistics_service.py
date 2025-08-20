import sqlite3
from datetime import datetime
from typing import Dict, List, Any

def _last_six_months_start() -> str:
    today = datetime.today()
    start_year = today.year
    start_month = today.month - 5
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    return f"{start_year:04d}-{start_month:02d}-01"

def get_monthly_expenses(db_conn: sqlite3.Connection, category_id: int = None, user_id: int = None) -> List[Dict[str, Any]]:
    start_date_str = _last_six_months_start()
    query = """
        SELECT strftime('%Y-%m', date) AS ym,
               SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS expenses
        FROM transactions
        WHERE date >= ?
    """
    params: List[Any] = [start_date_str]
    if category_id is not None:
        query += " AND category_id = ?"
        params.append(category_id)
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " GROUP BY ym"
    rows = db_conn.execute(query, params).fetchall()
    results = {r["ym"]: float(r["expenses"] or 0.0) for r in rows}

    # יצירת רצף 6 חודשים גם אם אין נתונים
    output: List[Dict[str, Any]] = []
    y, m = map(int, start_date_str.split("-")[:2])
    for _ in range(6):
        key = f"{y:04d}-{m:02d}"
        output.append({"month": key, "expenses": results.get(key, 0.0)})
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return output
