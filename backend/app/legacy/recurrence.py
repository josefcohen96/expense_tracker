from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import List, Tuple, Optional

from .db import get_connection, fetchone, execute


def parse_date(ds: str) -> date:
    return datetime.strptime(ds, "%Y-%m-%d").date()


def format_date(d: date) -> str:
    return d.isoformat()


def month_periods(start: date, end: date) -> List[Tuple[int, int]]:
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
    periods: List[Tuple[int, int]] = []
    current = start - timedelta(days=start.weekday())
    while current <= end:
        iso_year, iso_week, _ = current.isocalendar()
        periods.append((iso_year, iso_week))
        current += timedelta(days=7)
    return periods


def year_periods(start: date, end: date) -> List[int]:
    return list(range(start.year, end.year + 1))


def get_meta(conn, key: str) -> Optional[str]:
    row = fetchone(conn, "SELECT value FROM meta WHERE key = ?", (key,))
    return row[0] if row else None


def set_meta(conn, key: str, value: str) -> None:
    execute(
        conn,
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def period_key_for(recurrence: dict, period: Tuple) -> Tuple[str, str]:
    freq = recurrence["frequency"]
    start_dt = parse_date(recurrence["start_date"])
    if freq == "monthly":
        year, month = period
        day = recurrence["day_of_month"] or start_dt.day
        last_day = calendar.monthrange(year, month)[1]
        if day > last_day:
            day = last_day
        due_dt = date(year, month, day)
        key = f"{year:04d}-{month:02d}"
        return key, format_date(due_dt)
    elif freq == "weekly":
        iso_year, iso_week = period
        try:
            monday = date.fromisocalendar(iso_year, iso_week, 1)
        except ValueError:
            return "", ""
        weekday = recurrence["weekday"] or start_dt.weekday()
        due_dt = monday + timedelta(days=weekday)
        key = f"{iso_year:04d}-W{iso_week:02d}"
        return key, format_date(due_dt)
    elif freq == "yearly":
        year = period
        month = start_dt.month
        day = start_dt.day
        last_day = calendar.monthrange(year, month)[1]
        if day > last_day:
            day = last_day
        due_dt = date(year, month, day)
        key = f"{year:04d}"
        return key, format_date(due_dt)
    else:
        return "", ""


def apply_recurring(today: Optional[date] = None) -> int:
    if today is None:
        today = date.today()
    count_inserted = 0
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        last_opened_str = get_meta(conn, "last_opened_at")
        if last_opened_str:
            last_opened = parse_date(last_opened_str)
        else:
            last_opened = today
        if last_opened > today:
            last_opened = today
        recurrences = conn.execute("SELECT * FROM recurrences WHERE active = 1").fetchall()
        for rec in recurrences:
            rec_dict = dict(rec)
            rec_start = parse_date(rec_dict["start_date"])
            rec_end = None
            if rec_dict["end_date"]:
                rec_end = parse_date(rec_dict["end_date"])
            start_date_for_periods = last_opened
            if rec_start > start_date_for_periods:
                start_date_for_periods = rec_start
            end_date_for_periods = today
            if rec_end and rec_end < end_date_for_periods:
                end_date_for_periods = rec_end
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
        conn.commit()
        set_meta(conn, "last_opened_at", format_date(today))
    return count_inserted

