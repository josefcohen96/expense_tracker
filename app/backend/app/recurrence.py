# app/backend/app/recurrence.py
"""
Logic for applying recurring transactions.

This module encapsulates the algorithm that generates transactions
from recurrence rules when the application is started or when
explicitly triggered. Recurring transactions are not inserted
continuously in real time; instead, missing periods are
retrospectively filled when the application is opened. The
algorithm ensures idempotency using the `(recurrence_id,
period_key)` unique constraint on the `transactions` table.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import List, Tuple, Optional, Any

import sqlite3
from . import db  # ניגש ישירות ל-db הקיים שלך (ללא services)

# --------- Helpers: dates ---------

def parse_date(ds: str) -> date:
    return datetime.strptime(ds, "%Y-%m-%d").date()

def format_date(d: date) -> str:
    return d.isoformat()

def _clamp_day(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    if day < 1:
        day = 1
    if day > last_day:
        day = last_day
    return date(year, month, day)

def _add_months_keep_dom(current: date, months: int, desired_day: Optional[int]) -> date:
    total_months = current.year * 12 + current.month - 1 + months
    y = total_months // 12
    m = total_months % 12 + 1
    day = int(desired_day) if desired_day is not None else current.day
    return _clamp_day(y, m, day)

# --------- Helpers: meta ---------

def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None

def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
        (key, value),
    )

# --------- Core ---------

def _compute_next_charge_date(current_due: date, freq: str, day_of_month: Optional[int], weekday: Optional[int]) -> date:
    if freq == "monthly":
        return _add_months_keep_dom(current_due, 1, day_of_month)
    if freq == "weekly":
        return current_due + timedelta(days=7)
    if freq == "yearly":
        try:
            return current_due.replace(year=current_due.year + 1)
        except ValueError:
            # Feb 29th case => move to Feb 28th next year
            return current_due.replace(month=2, day=28, year=current_due.year + 1)
    # default: push one day
    return current_due + timedelta(days=1)

def apply_recurring(today: Optional[date] = None) -> int:
    """
    Materialize due recurring transactions using `next_charge_date`.
    For each active recurrence, if its `next_charge_date` is in the past or today,
    insert a transaction for that date (idempotent via (recurrence_id, period_key)),
    and advance `next_charge_date` by one interval. Repeat until next_charge_date > today.
    """
    if today is None:
        today = date.today()

    count_inserted = 0
    conn = db.get_connection()
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        rows = conn.execute(
            "SELECT * FROM recurrences WHERE active = 1 AND next_charge_date IS NOT NULL"
        ).fetchall()

        for row in rows:
            rec = dict(row)
            try:
                due = parse_date(rec["next_charge_date"]) if rec.get("next_charge_date") else None
            except Exception:
                due = None
            if not due:
                continue

            # Loop while overdue (catch up if app was down)
            while due <= today:
                period_key = due.isoformat()

                # Skip if explicitly marked as skipped
                skipped = conn.execute(
                    "SELECT 1 FROM recurrence_skips WHERE recurrence_id = ? AND period_key = ? LIMIT 1",
                    (rec["id"], period_key),
                ).fetchone()
                if not skipped:
                    # Idempotency: check if already exists
                    exists = conn.execute(
                        "SELECT 1 FROM transactions WHERE recurrence_id = ? AND period_key = ? LIMIT 1",
                        (rec["id"], period_key),
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                due.isoformat(),
                                -abs(rec["amount"]),
                                rec["category_id"],
                                rec["user_id"],
                                rec.get("account_id"),
                                None,
                                None,
                                rec["id"],
                                period_key,
                            ),
                        )
                        count_inserted += 1

                # Advance next charge date by one interval
                next_due = _compute_next_charge_date(due, rec.get("frequency"), rec.get("day_of_month"), rec.get("weekday"))
                conn.execute(
                    "UPDATE recurrences SET next_charge_date = ? WHERE id = ?",
                    (next_due.isoformat(), rec["id"]),
                )
                due = next_due

        conn.commit()
        return count_inserted
    finally:
        conn.close()
