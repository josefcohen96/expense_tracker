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

def month_periods(start: date, end: date) -> List[Tuple[int, int]]:
    periods: List[Tuple[int, int]] = []
    y, m = start.year, start.month
    while (y < end.year) or (y == end.year and m <= end.month):
        periods.append((y, m))
        m = 1 if m == 12 else m + 1
        if m == 1:
            y += 1
    return periods

def week_periods(start: date, end: date) -> List[Tuple[int, int]]:
    periods: List[Tuple[int, int]] = []
    current = start - timedelta(days=start.weekday())  # Monday
    while current <= end:
        iso_year, iso_week, _ = current.isocalendar()
        periods.append((iso_year, iso_week))
        current += timedelta(days=7)
    return periods

def year_periods(start: date, end: date) -> List[int]:
    return list(range(start.year, end.year + 1))

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

def period_key_for(recurrence: dict, period: Tuple) -> Tuple[str, str]:
    freq = recurrence["frequency"]
    start_dt = parse_date(recurrence["start_date"]) if recurrence.get("start_date") else date(2000, 1, 1)

    if freq == "monthly":
        year, month = period
        # Use configured day_of_month if provided; default to 1
        configured_day = recurrence.get("day_of_month")
        try:
            day = int(configured_day) if configured_day is not None else 1
        except Exception:
            day = 1
        last_day = calendar.monthrange(year, month)[1]
        if day > last_day:
            day = last_day
        due_dt = date(year, month, day)
        return f"{year:04d}-{month:02d}", format_date(due_dt)

    if freq == "weekly":
        iso_year, iso_week = period
        try:
            monday = date.fromisocalendar(iso_year, iso_week, 1)
        except ValueError:
            return "", ""
        # Use configured weekday (Python: Monday=0..Sunday=6). Default to Sunday (6)
        configured_weekday = recurrence.get("weekday")
        try:
            weekday = int(configured_weekday) if configured_weekday is not None else 6
        except Exception:
            weekday = 6
        if weekday < 0:
            weekday = 0
        if weekday > 6:
            weekday = 6
        due_dt = monday + timedelta(days=weekday)
        return f"{iso_year:04d}-W{iso_week:02d}", format_date(due_dt)

    if freq == "yearly":
        year = period
        # Charge on 1st of August
        month = 8
        day = 1
        last_day = calendar.monthrange(year, month)[1]
        if day > last_day:
            day = last_day
        due_dt = date(year, month, day)
        return f"{year:04d}", format_date(due_dt)

    # unsupported/custom
    return "", ""

def apply_recurring(today: Optional[date] = None) -> int:
    """
    Generate missing recurring transactions and return count inserted.
    """
    if today is None:
        today = date.today()

    count_inserted = 0
    conn = db.get_connection()
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        last_run_str = get_meta(conn, "last_recurring_run")
        last_run = parse_date(last_run_str) if last_run_str else date(1900, 1, 1)
        if last_run > today:
            last_run = today

        recurrences = conn.execute(
            "SELECT * FROM recurrences WHERE active = 1"
        ).fetchall()

        for rec in recurrences:
            rec_dict = dict(rec)
            rec_start = parse_date(rec_dict["start_date"])
            rec_end = parse_date(rec_dict["end_date"]) if rec_dict["end_date"] else None

            start_date_for_periods = max(last_run, rec_start)
            end_date_for_periods = min(today, rec_end) if rec_end else today
            if start_date_for_periods > end_date_for_periods:
                continue

            freq = rec_dict["frequency"]
            if freq == "monthly":
                periods = month_periods(start_date_for_periods, end_date_for_periods)
            elif freq == "weekly":
                periods = week_periods(start_date_for_periods, end_date_for_periods)
            elif freq == "yearly":
                periods = year_periods(start_date_for_periods, end_date_for_periods)
            else:
                continue

            for period in periods:
                key, due_date_str = period_key_for(rec_dict, period)
                if not key:
                    continue

                exists = conn.execute(
                    "SELECT 1 FROM transactions WHERE recurrence_id = ? AND period_key = ? LIMIT 1",
                    (rec_dict["id"], key),
                ).fetchone()
                if exists:
                    continue

                conn.execute(
                    "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        due_date_str,
                        -abs(rec_dict["amount"]),  # Ensure amount is negative for expenses
                        rec_dict["category_id"],
                        rec_dict["user_id"],
                        rec_dict.get("account_id"),
                        None,
                        None,
                        rec_dict["id"],
                        key,
                    ),
                )
                count_inserted += 1

        set_meta(conn, "last_recurring_run", format_date(today))
        conn.commit()
        return count_inserted
    finally:
        conn.close()
