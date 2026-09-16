"""Wedding planning numbers derived from data the module already stores.

- Countdown: days to `wedding_date` and the share of tasks done.
- Milestones: a backwards schedule stored as offsets from the wedding date, so
  moving the wedding moves every milestone. A milestone pinned to a specific
  day (`custom_date`) keeps it and is reported as adjusted.
- Headcount and money: people per RSVP status and what is committed/owed,
  the inputs for the guest-count consequence cards.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional

from . import hebrew_dates as hd

CHOSEN_VENDOR_STATUSES = ("deal_closed", "deposit_paid", "fully_paid")

# (title, offset_days, kind). `kind` lets the rail show what a milestone feeds.
DEFAULT_MILESTONES = (
    ("סגירת אולם ותאריך", -180, "general"),
    ("חתימה עם צלם", -120, "general"),
    ("חתימה עם די-ג'יי / להקה", -120, "general"),
    ("הזמנת שמלה וחליפה", -120, "general"),
    ("בחירת רב / עורך טקס", -90, "general"),
    ("שליחת הזמנות", -84, "invitations"),
    ("תפריט סופי עם הקייטרינג", -70, "catering"),
    ("טעימות באולם", -60, "general"),
    ("מספר אורחים סופי לאולם", -14, "headcount"),
    ("מדידה אחרונה ללבוש", -14, "general"),
    ("סידורי הושבה סופיים", -10, "seating"),
    ("תשלום יתרה לספקים", -7, "payment"),
)
MILESTONE_KINDS = ("general", "invitations", "catering", "headcount", "seating", "payment")
_SEEDED_FLAG = "wedding_milestones_seeded"

# People per guest row: the guest, a plus-one, and children.
_PEOPLE_SQL = "1 + CASE WHEN plus_one=1 THEN 1 ELSE 0 END + COALESCE(children_count,0)"


def get_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM wedding_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def get_wedding_date(conn: sqlite3.Connection) -> Optional[date]:
    return hd.parse_iso(get_setting(conn, "wedding_date"))


# ─── Milestones ─────────────────────────────────────────────────────────────

def seed_default_milestones(conn: sqlite3.Connection) -> bool:
    """Insert the starter milestones once, the first time a wedding date exists.

    Guarded by a system flag so deleting every milestone doesn't bring the
    defaults back. The caller commits.
    """
    if conn.execute("SELECT 1 FROM system_settings WHERE key=?", (_SEEDED_FLAG,)).fetchone():
        return False
    has_rows = conn.execute("SELECT 1 FROM wedding_milestones LIMIT 1").fetchone()
    if not has_rows:
        for idx, (title, offset, kind) in enumerate(DEFAULT_MILESTONES):
            conn.execute(
                "INSERT INTO wedding_milestones (title, offset_days, kind, sort_order) VALUES (?,?,?,?)",
                (title, offset, kind, idx),
            )
    conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, '1')", (_SEEDED_FLAG,)
    )
    return not has_rows


def vendor_balance_due(conn: sqlite3.Connection) -> float:
    """What is still owed to vendors with a closed deal."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(CASE
            WHEN status='fully_paid' THEN 0
            WHEN status='deposit_paid' THEN MAX(COALESCE(price_quoted,0) - COALESCE(deposit_amount,0), 0)
            ELSE COALESCE(price_quoted,0) END), 0)
        FROM wedding_vendors WHERE status IN ('deal_closed','deposit_paid','fully_paid')
        """
    ).fetchone()
    return float(row[0] or 0)


def list_milestones(conn: sqlite3.Connection, today: Optional[date] = None) -> dict:
    """Milestones in date order with their computed date and status.

    Status is one of done / overdue / next / future; exactly one open,
    not-yet-due milestone is `next`.
    """
    today = today or date.today()
    wedding = get_wedding_date(conn)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM wedding_milestones ORDER BY offset_days, sort_order, id"
    ).fetchall()]

    balance = None
    for m in rows:
        custom = hd.parse_iso(m.get("custom_date"))
        when = custom or (wedding + timedelta(days=m["offset_days"]) if wedding else None)
        m["adjusted"] = custom is not None
        m["date"] = when.isoformat() if when else None
        m["date_label"] = hd.dotted_date(when) if when else ""
        m["offset_label"] = hd.offset_label(m["offset_days"])
        m["offset_short"] = hd.offset_label(m["offset_days"], short=True)
        m["days_until"] = (when - today).days if when else None
        m["planned_date_label"] = ""
        if m["kind"] == "payment":
            if balance is None:
                balance = vendor_balance_due(conn)
            m["amount"] = balance
        else:
            m["amount"] = None

    rows.sort(key=lambda m: (m["date"] or "9999-12-31", m["sort_order"], m["id"]))

    next_found = False
    for m in rows:
        if m["completed"]:
            m["status"] = "done"
        elif m["days_until"] is not None and m["days_until"] < 0:
            m["status"] = "overdue"
            m["planned_date_label"] = m["date_label"]
            m["when_label"] = hd.overdue_label(-m["days_until"])
        elif not next_found:
            m["status"] = "next"
            next_found = True
        else:
            m["status"] = "future"
        if m["status"] == "done":
            m["when_label"] = m["date_label"]
        elif m["status"] != "overdue":
            m["when_label"] = hd.in_days_label(m["days_until"]) if m["days_until"] is not None else ""

    upcoming = next((m for m in rows if m["status"] == "next"), None)
    overdue = [m for m in rows if m["status"] == "overdue"]
    return {
        "wedding_date": wedding.isoformat() if wedding else None,
        "wedding_date_label": hd.dotted_date(wedding, with_year=True) if wedding else "",
        "milestones": rows,
        # The card on the overview shows what needs attention first.
        "next": overdue[0] if overdue else upcoming,
        "done_count": sum(1 for m in rows if m["completed"]),
    }


def milestone_weeks_before(m: dict) -> str:
    """'12 שבועות לפני' for the next-milestone card."""
    label = hd.offset_label(m["offset_days"])
    return label.lstrip("-+") + (" לפני" if m["offset_days"] < 0 else " אחרי")


# ─── Countdown ──────────────────────────────────────────────────────────────

def task_progress(conn: sqlite3.Connection) -> dict:
    total, done = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(completed), 0) FROM wedding_tasks"
    ).fetchone()
    total, done = int(total or 0), int(done or 0)
    return {
        "total": total,
        "done": done,
        "open": total - done,
        "pct": round(done * 100 / total) if total else 0,
    }


def countdown(conn: sqlite3.Connection, today: Optional[date] = None) -> dict:
    """Days to the wedding plus task progress; `days_left` is None without a date."""
    today = today or date.today()
    wedding = get_wedding_date(conn)
    info = {"date": None, "days_left": None, **task_progress(conn)}
    if wedding:
        days = (wedding - today).days
        info.update({
            "date": wedding.isoformat(),
            "date_label": hd.dotted_date(wedding, with_year=True),
            "weekday": hd.weekday_name(wedding),
            "days_left": days,
            "weeks_label": hd.weeks_and_days(days),
        })
    return info


def vendor_progress(conn: sqlite3.Connection) -> dict:
    total, chosen = conn.execute(
        "SELECT COUNT(DISTINCT category), "
        "COUNT(DISTINCT CASE WHEN status IN ('deal_closed','deposit_paid','fully_paid') THEN category END) "
        "FROM wedding_vendors"
    ).fetchone()
    return {"total": int(total or 0), "chosen": int(chosen or 0)}


# ─── Guests & money ─────────────────────────────────────────────────────────

def headcount(conn: sqlite3.Connection) -> dict:
    """People (not invitations) per RSVP status."""
    counts = {"confirmed": 0, "maybe": 0, "declined": 0, "pending": 0}
    for status, people in conn.execute(
        f"SELECT status, COALESCE(SUM({_PEOPLE_SQL}), 0) FROM wedding_guests GROUP BY status"
    ).fetchall():
        key = status if status in counts else "pending"
        counts[key] += int(people or 0)
    counts["total"] = sum(counts.values())
    return counts


def committed_total(conn: sqlite3.Connection) -> float:
    """Closed-deal vendor prices plus manual actuals (the budget page's grand_committed)."""
    vendors = conn.execute(
        "SELECT COALESCE(SUM(price_quoted),0) FROM wedding_vendors "
        "WHERE status IN ('deal_closed','deposit_paid','fully_paid')"
    ).fetchone()[0]
    manual = conn.execute("SELECT COALESCE(SUM(actual_amount),0) FROM wedding_budget_items").fetchone()[0]
    return float(vendors or 0) + float(manual or 0)
