"""The היום screen: what needs doing now across the wedding, the renovation and money."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any, Optional

from ..api.transactions import INCOME_CATEGORIES
from . import hebrew_dates as hd
from . import wedding_plan
from .access import can_access_renovation
from .people import find_person, household

# How far ahead the queue looks, and how close counts as "soon".
WEEK_AHEAD_DAYS = 6
SOON_DAYS = 1


def urgency(due: Optional[date], today: date) -> str:
    """overdue / soon / normal — drives the row's start border color."""
    if due is None:
        return "normal"
    delta = (due - today).days
    if delta < 0:
        return "overdue"
    if delta <= SOON_DAYS:
        return "soon"
    return "normal"


def task_group(task: dict, today: date) -> str:
    """Section of the grouped task list a wedding task belongs to."""
    if task.get("completed"):
        return "done"
    due = hd.parse_iso(task.get("due_date"))
    if due is None:
        return "nodate"
    delta = (due - today).days
    if delta < 0:
        return "overdue"
    if delta <= WEEK_AHEAD_DAYS:
        return "week"
    return "later"


def _queue_row(module: str, row: sqlite3.Row, today: date) -> dict:
    due = hd.parse_iso(row["due_date"])
    return {
        "module": module,
        "id": row["id"],
        "title": row["title"],
        "due_date": row["due_date"],
        "due_label": hd.due_label(due, today) if due else "",
        "urgency": urgency(due, today),
        # Renovation tasks restore this status when a completion is undone.
        "status": row["status"] if "status" in row.keys() else None,
    }


def urgent_tasks(conn: sqlite3.Connection, user: Any, today: date) -> list[dict]:
    """Open tasks that are overdue or due within the week, across modules."""
    horizon = (today + timedelta(days=WEEK_AHEAD_DAYS)).isoformat()
    rows = [
        _queue_row("wedding", r, today)
        for r in conn.execute(
            "SELECT id, title, due_date FROM wedding_tasks "
            "WHERE completed=0 AND due_date IS NOT NULL AND due_date != '' AND due_date <= ?",
            (horizon,),
        ).fetchall()
    ]
    if can_access_renovation(user):
        rows += [
            _queue_row("renovation", r, today)
            for r in conn.execute(
                "SELECT id, title, due_date, status FROM renovation_tasks "
                "WHERE status != 'done' AND due_date IS NOT NULL AND due_date != '' AND due_date <= ?",
                (horizon,),
            ).fetchall()
        ]
    rows.sort(key=lambda t: (t["due_date"], t["module"], t["id"]))
    return rows


def month_totals(conn: sqlite3.Connection, ym: str) -> dict:
    """Expenses (excluding savings) and income for a YYYY-MM, main users only."""
    ids = [p["id"] for p in household(conn)] or [0]
    marks = ",".join("?" for _ in ids)
    income = ",".join("?" for _ in INCOME_CATEGORIES)
    row = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN t.amount < 0 AND c.name NOT IN ({income}) AND COALESCE(c.is_saving, 0) = 0
                              THEN -t.amount ELSE 0 END), 0) AS expenses,
            COALESCE(SUM(CASE WHEN t.amount > 0 AND c.name IN ({income}) THEN t.amount ELSE 0 END), 0) AS income
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = ? AND t.user_id IN ({marks})
        """,
        (*INCOME_CATEGORIES, *INCOME_CATEGORIES, ym, *ids),
    ).fetchone()
    return {"expenses": float(row["expenses"]), "income": float(row["income"])}


def build_today(conn: sqlite3.Connection, user: Any, today: Optional[date] = None) -> dict:
    today = today or date.today()
    people = household(conn)
    me = find_person(people, user)
    return {
        "date": today.isoformat(),
        "date_label": hd.short_month_date(today),
        "me": me,
        "wedding": wedding_plan.countdown(conn, today),
        "tasks": urgent_tasks(conn, user, today),
        "month": {
            "ym": today.strftime("%Y-%m"),
            "label": hd.HEBREW_MONTHS[today.month - 1],
            **month_totals(conn, today.strftime("%Y-%m")),
        },
    }
