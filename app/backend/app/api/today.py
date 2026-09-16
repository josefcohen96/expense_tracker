"""Aggregate reads for the mobile shell: the היום queue and the quick-add sheet's options."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..db import get_db_conn
from ..services.access import can_access_renovation, can_edit_renovation
from ..services.people import find_person, household
from ..services.today import build_today
from .transactions import INCOME_CATEGORIES

router = APIRouter(prefix="/api", tags=["today"])

# How far back "the user's own frequency" looks when ordering categories.
FREQUENCY_WINDOW_DAYS = 180

CATEGORY_EMOJI = {
    "סופר": "🛒", "קניות": "🛍️", "רכב": "🚗", "דלק": "⛽", "תחבורה": "🚌",
    "אוכל בחוץ": "🍽️", "מסעדות": "🍽️", "חתונה": "💍", "שיפוץ": "🏡",
    "הוצאות בית": "🏠", "בריאות": "🩺", "פנאי": "🎉", "חסכונות": "🐷",
    "ביגוד": "👕", "חשבונות": "🧾", "מתנות": "🎁", "ביטוח": "🛡️",
    "תקשורת": "📱", "חינוך": "📚", "חיות": "🐾",
}

WEDDING_TASK_CATEGORIES = (
    ("vendors", "ספקים"), ("guests", "מוזמנים"), ("venue", "מקום"),
    ("logistics", "לוגיסטיקה"), ("attire", "לבוש"), ("general", "כללי"),
)


def _session_user(request: Request) -> Any:
    return getattr(request.state, "user", None) or request.session.get("user")


@router.get("/today")
async def today_summary(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    """Everything the היום screen shows, in one read."""
    return build_today(db_conn, _session_user(request))


@router.get("/quick-add/options")
async def quick_add_options(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    """Pickers for the quick-add sheet, ordered by what this user actually uses."""
    user = _session_user(request)
    people = household(db_conn)
    me = find_person(people, user) or (people[0] if people else None)
    my_id = me["id"] if me else 0
    since = (date.today() - timedelta(days=FREQUENCY_WINDOW_DAYS)).isoformat()
    income = ",".join("?" for _ in INCOME_CATEGORIES)

    categories = db_conn.execute(
        f"""
        SELECT c.id, c.name,
               SUM(CASE WHEN t.user_id = ? AND t.date >= ? THEN 1 ELSE 0 END) AS mine,
               COUNT(t.id) AS overall
        FROM categories c
        LEFT JOIN transactions t ON t.category_id = c.id AND t.recurrence_id IS NULL
        WHERE c.name NOT IN ({income})
        GROUP BY c.id
        ORDER BY mine DESC, overall DESC, c.name
        """,
        (my_id, since, *INCOME_CATEGORIES),
    ).fetchall()

    accounts = db_conn.execute(
        """
        SELECT a.id, a.name,
               SUM(CASE WHEN t.user_id = ? AND t.date >= ? THEN 1 ELSE 0 END) AS mine
        FROM accounts a
        LEFT JOIN transactions t ON t.account_id = a.id
        GROUP BY a.id
        ORDER BY a.id
        """,
        (my_id, since),
    ).fetchall()
    default_account = None
    if accounts:
        by_use = max(accounts, key=lambda a: a["mine"] or 0)
        credit = next((a for a in accounts if a["name"] == "כרטיס אשראי"), None)
        default_account = (by_use if by_use["mine"] else (credit or accounts[0]))["id"]

    return {
        "today": date.today().isoformat(),
        "me": me,
        "people": people,
        "categories": [
            {"id": c["id"], "name": c["name"], "emoji": CATEGORY_EMOJI.get(c["name"], "")}
            for c in categories
        ],
        "accounts": [{"id": a["id"], "name": a["name"]} for a in accounts],
        "default_account_id": default_account,
        "wedding_categories": [{"key": k, "label": v} for k, v in WEDDING_TASK_CATEGORIES],
        # Renovation tasks can be added from the sheet only by users who may edit them.
        "renovation": can_access_renovation(user) and can_edit_renovation(user),
    }
