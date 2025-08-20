# app/backend/app/api/statistics.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from ..db import get_db_conn
from starlette.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/frontend/templates")

router = APIRouter(prefix="/statistics", tags=["statistics"])

@router.get("", response_class=HTMLResponse)
def statistics(request: Request, db_conn=Depends(get_db_conn)):
    cur = db_conn.cursor()

    # הוצאות לפי חודש (6 חודשים אחרונים)
    monthly = cur.execute("""
        SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
        FROM transactions
        WHERE date >= date('now', '-6 months')
        GROUP BY strftime('%Y-%m', date)
        ORDER BY month
    """).fetchall()

    # הוצאות לפי משתמש
    users = cur.execute("""
        SELECT u.name AS user, SUM(t.amount) AS total
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        WHERE t.date >= date('now', '-6 months')
        GROUP BY u.name
    """).fetchall()

    # הוצאות לפי קטגוריה
    categories = cur.execute("""
        SELECT c.name AS category, SUM(t.amount) AS total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        GROUP BY c.name
    """).fetchall()

    return templates.TemplateResponse("statistics.html", {
        "request": request,
        "monthly_expenses": [dict(row) for row in monthly],
        "user_expenses": [dict(row) for row in users],
        "category_expenses": [dict(row) for row in categories],
    })
