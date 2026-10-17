"""הזמנות מחו״ל: samples ordered from abroad before the big order.

Everything here is derived from the item rows and the wedding date — the lanes,
how long ago a sample was ordered, the rough cost of the big order and the date
by which it has to leave. Nothing derived is stored.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any, Optional

from . import hebrew_dates as hd
from . import wedding_plan

STAGES = ("to_order", "ordered", "arrived", "approved", "rejected")
STAGE_LABELS = {
    "to_order": "לבדוק",
    "ordered": "בדרך",
    "arrived": "הגיע — מה דעתכם?",
    "approved": "להזמנה הגדולה",
    "rejected": "נפסל",
}
STORES = ("AliExpress", "Temu", "Shein", "Amazon")

LEAD_DAYS_KEY = "overseas_lead_days"
DEFAULT_LEAD_DAYS = 42
MIN_LEAD_DAYS = 7
MAX_LEAD_DAYS = 140


def lead_days(conn: sqlite3.Connection) -> int:
    """Days between the big order leaving and the wedding (a wedding setting)."""
    raw = (wedding_plan.get_setting(conn, LEAD_DAYS_KEY) or "").strip()
    if raw.isdigit() and MIN_LEAD_DAYS <= int(raw) <= MAX_LEAD_DAYS:
        return int(raw)
    return DEFAULT_LEAD_DAYS


def deadline(conn: sqlite3.Connection, today: Optional[date] = None) -> Optional[dict]:
    """When the big order has to leave; None without a wedding date."""
    today = today or date.today()
    wedding = wedding_plan.get_wedding_date(conn)
    if not wedding:
        return None
    lead = lead_days(conn)
    due = wedding - timedelta(days=lead)
    days_left = (due - today).days
    return {
        "date": due.isoformat(),
        "label": hd.long_date(due),
        "days_left": days_left,
        "days_label": hd.in_days_label(days_left) if days_left >= 0 else hd.overdue_label(-days_left),
        "lead_days": lead,
        "lead_weeks": lead // 7,
        "overdue": days_left < 0,
        "wedding_ahead": wedding >= today,
    }


def estimate(item: dict) -> Optional[float]:
    """Rough cost of the big order from the sample price; None unless both are set."""
    price = item.get("sample_price")
    qty = item.get("quantity_needed")
    if price is None or qty is None:
        return None
    if price <= 0 or qty <= 0:
        return None
    return float(price) * int(qty)


def money_label(amount: float) -> str:
    """'₪1,200'"""
    return f"₪{amount:,.0f}"


def decorate(item: dict, today: Optional[date] = None) -> dict:
    """The item row plus the labels the page shows."""
    today = today or date.today()
    out = dict(item)
    ordered = hd.parse_iso(out.get("ordered_at"))
    arrived = hd.parse_iso(out.get("arrived_at"))
    out["ordered_ago"] = hd.ago_label(ordered, today) if ordered else None
    out["arrived_ago"] = hd.ago_label(arrived, today) if arrived else None
    est = estimate(out)
    out["estimate"] = est
    out["estimate_label"] = money_label(est) if est is not None else None
    if "comments" in out:
        out["comment_count"] = len(out["comments"])
    else:
        out["comment_count"] = int(out.get("comment_count") or 0)
    out["stage_label"] = STAGE_LABELS.get(out.get("stage"), STAGE_LABELS["to_order"])
    return out


def lanes(items: list[dict]) -> list[dict]:
    """Items grouped by stage, in STAGES order, with the lane's estimate total."""
    result = []
    for key in STAGES:
        lane_items = [i for i in items if (i.get("stage") or "to_order") == key]
        estimates = [i["estimate"] for i in lane_items if i.get("estimate") is not None]
        total = sum(estimates) if estimates else None
        result.append({
            "key": key,
            "label": STAGE_LABELS[key],
            "items": lane_items,
            "estimate_total": total,
            "estimate_total_label": money_label(total) if total is not None else None,
        })
    return result


def stage_transition(existing: Any, new_stage: str, today: Optional[date] = None) -> dict:
    """The columns to write when an item moves to `new_stage`."""
    today_iso = (today or date.today()).isoformat()
    ordered_at = existing["ordered_at"]
    arrived_at = existing["arrived_at"]
    cols: dict = {"stage": new_stage}
    if new_stage == "to_order":
        cols["ordered_at"] = None
        cols["arrived_at"] = None
    elif new_stage == "ordered":
        cols["ordered_at"] = ordered_at or today_iso
        cols["arrived_at"] = None
    elif new_stage == "arrived":
        cols["ordered_at"] = ordered_at or today_iso
        cols["arrived_at"] = arrived_at or today_iso
    return cols


def comment_view(row: Any, today: Optional[date] = None) -> dict:
    today = today or date.today()
    out = dict(row)
    created = hd.parse_iso(out.get("created_at"))
    out["when"] = hd.relative_day(created, today) if created else ""
    return out


def load_item(conn: sqlite3.Connection, item_id: int, today: Optional[date] = None) -> Optional[dict]:
    row = conn.execute("SELECT * FROM wedding_overseas_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["comments"] = [
        comment_view(c, today) for c in conn.execute(
            "SELECT * FROM wedding_overseas_comments WHERE item_id=? ORDER BY created_at, id", (item_id,)
        ).fetchall()
    ]
    return decorate(item, today)


def load_items(conn: sqlite3.Connection, today: Optional[date] = None) -> list[dict]:
    """Every item, decorated, each with its comments oldest first."""
    comments: dict[int, list] = {}
    for c in conn.execute("SELECT * FROM wedding_overseas_comments ORDER BY created_at, id").fetchall():
        comments.setdefault(c["item_id"], []).append(comment_view(c, today))
    items = []
    for row in conn.execute("SELECT * FROM wedding_overseas_items ORDER BY created_at, id").fetchall():
        item = dict(row)
        item["comments"] = comments.get(item["id"], [])
        items.append(decorate(item, today))
    return items
