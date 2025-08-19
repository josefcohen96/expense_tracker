"""Logic for applying recurring transactions.

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
from typing import List, Tuple, Optional

from .db import get_connection, fetchone, execute


def parse_date(ds: str) -> date:
    """Parse an ISO date (YYYY-MM-DD) into a `datetime.date` object."""
    return datetime.strptime(ds, "%Y-%m-%d").date()


def format_date(d: date) -> str:
    """Format a `datetime.date` object as an ISO string."""
    return d.isoformat()


def month_periods(start: date, end: date) -> List[Tuple[int, int]]:
    """Return a list of (year, month) tuples covering the range [start, end]."""
    periods: List[Tuple[int, int]] = []
    y, m = start.year, start.month
    while (y < end.year) or (y == end.year and m <= end.month):
        periods.append((y, m))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return periods


def week_periods(start: date, end: date) -> List[Tuple[int, int]]:
    """Return a list of (iso_year, iso_week) tuples covering the range [start, end].

    Weeks follow ISO 8601 numbering where weeks start on Monday.
    """
    periods: List[Tuple[int, int]] = []
    # Align to the Monday of the starting week
    current = start - timedelta(days=start.weekday())
    # Loop until we've passed the end date
    while current <= end:
        iso_year, iso_week, _ = current.isocalendar()
        periods.append((iso_year, iso_week))
        current += timedelta(days=7)
    return periods


def year_periods(start: date, end: date) -> List[int]:
    """Return a list of years covering the range [start, end]."""
    return list(range(start.year, end.year + 1))


def get_meta(conn, key: str) -> Optional[str]:
    row = fetchone(conn, "SELECT value FROM meta WHERE key = ?", (key,))
    return row[0] if row else None


def set_meta(conn, key: str, value: str) -> None:
    # Use INSERT OR REPLACE to upsert the meta value
    execute(
        conn,
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def period_key_for(recurrence: dict, period: Tuple) -> Tuple[str, str]:
    """Compute the period_key and due_date for a given recurrence and period.

    Parameters
    ----------
    recurrence: dict
        A dictionary representing a row from the `recurrences` table.
    period: Tuple
        For monthly: (year, month); weekly: (iso_year, iso_week);
        yearly: (year,)

    Returns
    -------
    (period_key, due_date_iso)
        A tuple containing a unique key and a due date string.
    """
    freq = recurrence["frequency"]
    start_dt = parse_date(recurrence["start_date"])
    # Determine due date based on recurrence frequency
    if freq == "monthly":
        year, month = period
        # Determine the day: use explicit day_of_month if provided; else start_dt.day
        day = recurrence["day_of_month"] or start_dt.day
        last_day = calendar.monthrange(year, month)[1]
        if day > last_day:
            day = last_day
        due_dt = date(year, month, day)
        key = f"{year:04d}-{month:02d}"
        return key, format_date(due_dt)
    elif freq == "weekly":
        iso_year, iso_week = period
        # Monday of the ISO week
        # python3.8+ allows fromisocalendar
        try:
            monday = date.fromisocalendar(iso_year, iso_week, 1)
        except ValueError:
            # If iso_week exceeds number of weeks in year, skip
            # This should rarely happen but handle gracefully
            return "", ""
        weekday = recurrence["weekday"] or start_dt.weekday()
        # ISO Monday is 0 in weekday() but fromisocalendar expects 1..7; we already have monday
        due_dt = monday + timedelta(days=weekday)
        key = f"{iso_year:04d}-W{iso_week:02d}"
        return key, format_date(due_dt)
    elif freq == "yearly":
        year = period
        # Preserve month and day from start_date
        month = start_dt.month
        day = start_dt.day
        # Adjust for February 29th or similar by clamping to last day of month
        last_day = calendar.monthrange(year, month)[1]
        if day > last_day:
            day = last_day
        due_dt = date(year, month, day)
        key = f"{year:04d}"
        return key, format_date(due_dt)
    else:
        # Custom cron or unknown; skip
        return "", ""


def apply_recurring(today: Optional[date] = None) -> int:
    """Generate missing recurring transactions.

    The function inspects the `recurrences` table for active rules and
    retroactively creates `transactions` for any missing periods
    between the last application and the current date. It returns
    the number of transactions inserted.

    Parameters
    ----------
    today : datetime.date, optional
        The date considered as "today". If not provided, uses the
        current date. Supplying a date is useful for testing.

    Returns
    -------
    int
        The count of newly inserted transactions.
    """
    if today is None:
        today = date.today()
    count_inserted = 0
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        # Determine the last time recurring transactions were applied
        last_opened_str = get_meta(conn, "last_opened_at")
        if last_opened_str:
            last_opened = parse_date(last_opened_str)
        else:
            # Default to the earliest possible date: use one day before today
            last_opened = today

        # Ensure we process at least the current period
        if last_opened > today:
            last_opened = today

        # Fetch all active recurrences
        recurrences = conn.execute(
            "SELECT * FROM recurrences WHERE active = 1"
        ).fetchall()

        for rec in recurrences:
            # Convert row to dict-like for easy access
            rec_dict = dict(rec)
            rec_start = parse_date(rec_dict["start_date"])
            rec_end = None
            if rec_dict["end_date"]:
                rec_end = parse_date(rec_dict["end_date"])

            # Determine the first period to consider: use last_opened or recurrence start, whichever is later
            start_date_for_periods = last_opened
            if rec_start > start_date_for_periods:
                start_date_for_periods = rec_start

            # Determine the end date for periods: today (current date)
            end_date_for_periods = today
            if rec_end and rec_end < end_date_for_periods:
                end_date_for_periods = rec_end

            if start_date_for_periods > end_date_for_periods:
                # Nothing to generate
                continue

            freq = rec_dict["frequency"]
            if freq == "monthly":
                periods = month_periods(start_date_for_periods, end_date_for_periods)
            elif freq == "weekly":
                periods = week_periods(start_date_for_periods, end_date_for_periods)
            elif freq == "yearly":
                periods = year_periods(start_date_for_periods, end_date_for_periods)
            else:
                # Skip unsupported frequencies or custom cron
                continue

            for period in periods:
                # Compute period_key and due_date
                key, due_date_str = period_key_for(rec_dict, period)
                if not key:
                    # Skip invalid
                    continue
                # Check if transaction already exists
                exists = conn.execute(
                    "SELECT 1 FROM transactions WHERE recurrence_id = ? AND period_key = ? LIMIT 1",
                    (rec_dict["id"], key),
                ).fetchone()
                if exists:
                    continue
                # Insert transaction
                conn.execute(
                    "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        due_date_str,
                        rec_dict["amount"],
                        rec_dict["category_id"],
                        rec_dict["user_id"],
                        rec_dict["account_id"],
                        f"Recurring: {rec_dict['name']}",
                        "recurring",
                        rec_dict["id"],
                        key,
                    ),
                )
                count_inserted += 1
        # Commit after all inserts
        conn.commit()
        # Update meta with current date
        set_meta(conn, "last_opened_at", format_date(today))
    return count_inserted