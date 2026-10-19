"""Wedding module pages and the public RSVP invite pages."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..auth import public
from ..db import get_db_conn
from ..services import hebrew_dates as hd
from ..services import wedding_plan
from ..services.people import household
from ..templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])


@router.get("/wedding/lodging", response_class=HTMLResponse)
async def wedding_lodging_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    rooms = [dict(r) for r in db_conn.execute(
        "SELECT * FROM wedding_rooms ORDER BY id"
    ).fetchall()]

    # Filter out declined guests from assignments — they should never count
    # toward room occupancy even if they were assigned earlier and later changed status.
    assignments = [dict(r) for r in db_conn.execute(
        """SELECT ra.room_id, ra.guest_id, g.name AS guest_name,
                  g.plus_one, g.plus_one_name, g.children_count, g.group_name
           FROM wedding_room_assignments ra
           JOIN wedding_guests g ON g.id = ra.guest_id
           WHERE g.status != 'declined'"""
    ).fetchall()]

    assigned_ids = {a["guest_id"] for a in assignments}
    for room in rooms:
        room["assigned"] = [a for a in assignments if a["room_id"] == room["id"]]
        room["occupancy"] = sum(
            1 + (1 if a["plus_one"] else 0) + (a["children_count"] or 0)
            for a in room["assigned"]
        )

    # Only consider guests who actually plan to attend AND want overnight stay
    all_guests = [dict(g) for g in db_conn.execute(
        "SELECT id, name, group_name, plus_one, plus_one_name, children_count, staying_overnight FROM wedding_guests WHERE status != 'declined' ORDER BY group_name, name"
    ).fetchall()]

    overnight_guests = [g for g in all_guests if g["staying_overnight"]]
    unassigned_overnight = [g for g in overnight_guests if g["id"] not in assigned_ids]
    all_unassigned = [g for g in overnight_guests if g["id"] not in assigned_ids]

    total_capacity = sum(r["max_capacity"] for r in rooms)
    total_assigned = len(assigned_ids)

    return templates.TemplateResponse(
        request,
        "wedding/lodging.html",
        {
            "request": request,
            "rooms": rooms,
            "unassigned_overnight": unassigned_overnight,
            "all_unassigned": all_unassigned,
            "total_capacity": total_capacity,
            "total_assigned": total_assigned,
            "total_overnight": len(overnight_guests),
        }
    )


# ==============================
# Wedding Module
# ==============================

def _wedding_total_budget(db_conn: sqlite3.Connection) -> tuple[float, float, float, float]:
    """Total budget = guest count × avg per guest + our addition.

    Falls back to the legacy manually-entered 'total_budget' setting when
    none of the formula fields have been set yet.
    Returns (total, guest_count, avg_per_guest, our_addition).
    """
    rows = db_conn.execute(
        "SELECT key, value FROM wedding_settings WHERE key IN "
        "('budget_guest_count','budget_avg_per_guest','budget_our_addition','total_budget')"
    ).fetchall()
    settings = {r["key"]: r["value"] for r in rows}

    def _num(key: str) -> float:
        try:
            return float(settings.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    guest_count = _num("budget_guest_count")
    avg_per_guest = _num("budget_avg_per_guest")
    our_addition = _num("budget_our_addition")

    if guest_count or avg_per_guest or our_addition:
        total = guest_count * avg_per_guest + our_addition
    else:
        total = _num("total_budget")
    return total, guest_count, avg_per_guest, our_addition


@router.get("/wedding", response_class=HTMLResponse)
async def wedding_dashboard(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    # Total expected attendance excludes declined guests so the cards sum back to total.
    try:
        total_guests = db_conn.execute(
            "SELECT COALESCE(SUM(1 + CASE WHEN plus_one=1 THEN 1 ELSE 0 END + COALESCE(children_count,0)), 0) FROM wedding_guests WHERE status != 'declined'"
        ).fetchone()[0]
    except Exception:
        total_guests = db_conn.execute("SELECT COUNT(*) FROM wedding_guests WHERE status != 'declined'").fetchone()[0]
    confirmed    = db_conn.execute("SELECT COALESCE(SUM(1 + CASE WHEN plus_one=1 THEN 1 ELSE 0 END + COALESCE(children_count,0)), 0) FROM wedding_guests WHERE status='confirmed'").fetchone()[0]
    declined     = db_conn.execute("SELECT COALESCE(SUM(1 + CASE WHEN plus_one=1 THEN 1 ELSE 0 END + COALESCE(children_count,0)), 0) FROM wedding_guests WHERE status='declined'").fetchone()[0]
    maybe        = db_conn.execute("SELECT COALESCE(SUM(1 + CASE WHEN plus_one=1 THEN 1 ELSE 0 END + COALESCE(children_count,0)), 0) FROM wedding_guests WHERE status='maybe'").fetchone()[0]
    pending      = db_conn.execute("SELECT COALESCE(SUM(1 + CASE WHEN plus_one=1 THEN 1 ELSE 0 END + COALESCE(children_count,0)), 0) FROM wedding_guests WHERE status='pending'").fetchone()[0]

    total_vendors      = db_conn.execute("SELECT COUNT(*) FROM wedding_vendors").fetchone()[0]
    contracted_vendors = db_conn.execute(
        "SELECT COUNT(*) FROM wedding_vendors WHERE status IN ('contract_signed','deposit_paid','fully_paid')"
    ).fetchone()[0]

    open_tasks   = db_conn.execute("SELECT COUNT(*) FROM wedding_tasks WHERE completed=0").fetchone()[0]
    urgent_tasks = db_conn.execute("SELECT COUNT(*) FROM wedding_tasks WHERE completed=0 AND priority='high'").fetchone()[0]

    # Total budget derived from guests × avg per guest + our addition
    total_budget, _, _, _ = _wedding_total_budget(db_conn)

    # Committed = only closed-deal vendors + manual actuals
    closed_vendors_total = db_conn.execute(
        "SELECT COALESCE(SUM(price_quoted),0) FROM wedding_vendors WHERE status IN ('deal_closed','deposit_paid','fully_paid')"
    ).fetchone()[0]
    manual_actual = db_conn.execute("SELECT COALESCE(SUM(actual_amount),0) FROM wedding_budget_items").fetchone()[0]
    grand_committed = (closed_vendors_total or 0) + (manual_actual or 0)

    wedding_date_row = db_conn.execute("SELECT value FROM wedding_settings WHERE key='wedding_date'").fetchone()
    wedding_date = wedding_date_row[0] if wedding_date_row else None

    recent_tasks = [dict(t) for t in db_conn.execute(
        "SELECT * FROM wedding_tasks WHERE completed=0 ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date ASC LIMIT 5"
    ).fetchall()]

    return templates.TemplateResponse(request, "wedding/index.html", {
        "request": request,
        "total_guests": total_guests,
        "confirmed": confirmed,
        "declined": declined,
        "maybe": maybe,
        "pending": pending,
        "total_vendors": total_vendors,
        "contracted_vendors": contracted_vendors,
        "open_tasks": open_tasks,
        "urgent_tasks": urgent_tasks,
        "total_budget": total_budget,
        "grand_committed": grand_committed,
        "wedding_date": wedding_date,
        "recent_tasks": recent_tasks,
        **_wedding_hero(db_conn),
    })


def _wedding_hero(db_conn: sqlite3.Connection) -> dict:
    """Countdown hero, next milestone and a four-row timeline for the mobile overview."""
    view = wedding_plan.list_milestones(db_conn)
    milestones = view["milestones"]
    # One finished milestone for context, then what's coming.
    done = [m for m in milestones if m["status"] == "done"]
    ahead = [m for m in milestones if m["status"] != "done"]
    timeline = (done[-1:] + ahead)[:4]
    next_m = view["next"]
    return {
        "countdown": wedding_plan.countdown(db_conn),
        "vendor_progress": wedding_plan.vendor_progress(db_conn),
        "next_milestone": next_m,
        "next_milestone_offset": wedding_plan.milestone_weeks_before(next_m) if next_m else "",
        "mini_timeline": timeline,
    }


@router.get("/wedding/vendors", response_class=HTMLResponse)
async def wedding_vendors_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    vendors = [dict(v) for v in db_conn.execute(
        "SELECT * FROM wedding_vendors ORDER BY category, name"
    ).fetchall()]
    return templates.TemplateResponse(request, "wedding/vendors.html", {
        "request": request,
        "vendors": vendors,
    })


@router.get("/wedding/vendors/{vendor_id}", response_class=HTMLResponse)
async def wedding_vendor_detail_page(vendor_id: int, request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    vendor = db_conn.execute("SELECT * FROM wedding_vendors WHERE id=?", (vendor_id,)).fetchone()
    if not vendor:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Vendor not found")
    quote_items = [dict(r) for r in db_conn.execute(
        "SELECT * FROM vendor_quote_items WHERE vendor_id=? ORDER BY sort_order, id",
        (vendor_id,)
    ).fetchall()]
    vendor_files = [dict(r) for r in db_conn.execute(
        "SELECT * FROM vendor_files WHERE vendor_id=? ORDER BY uploaded_at DESC",
        (vendor_id,)
    ).fetchall()]
    return templates.TemplateResponse(request, "wedding/vendor_detail.html", {
        "request": request,
        "vendor": dict(vendor),
        "quote_items": quote_items,
        "vendor_files": vendor_files,
    })


def _guest_count_engine(db_conn: sqlite3.Connection, pending_invitations: int) -> dict:
    """What the confirmed headcount drives: cost per guest, seats, catering portions.

    Each card is None when its inputs are missing or there is no gap to show.
    """
    people = wedding_plan.headcount(db_conn)
    confirmed = people["confirmed"]
    engine = {
        "people": people,
        "cost": None,
        "seats": None,
        "catering": None,
        "pending_invitations": pending_invitations,
        "pending_with_phone": 0,
    }

    committed = wedding_plan.committed_total(db_conn)
    if committed > 0 and confirmed > 0:
        engine["cost"] = {
            "committed": committed,
            "per_guest": committed / confirmed,
            "per_guest_if_maybe": committed / (confirmed + people["maybe"]) if people["maybe"] else None,
        }

    capacity = None
    raw_capacity = (wedding_plan.get_setting(db_conn, "venue_capacity") or "").strip()
    if raw_capacity.isdigit():
        capacity = int(raw_capacity)
    else:
        tables, seats = db_conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(capacity), 0) FROM wedding_seating_tables"
        ).fetchone()
        if tables:
            capacity = int(seats or 0)
    if capacity and confirmed > 0 and confirmed != capacity:
        engine["seats"] = {
            "capacity": capacity,
            "free": capacity - confirmed,
            "pct": min(confirmed * 100 / capacity, 100),
        }

    placeholders = ",".join("?" for _ in wedding_plan.CHOSEN_VENDOR_STATUSES)
    vendor = db_conn.execute(
        f"SELECT id, portions_ordered FROM wedding_vendors WHERE category='catering' "
        f"AND status IN ({placeholders}) ORDER BY COALESCE(price_quoted, 0) DESC, id LIMIT 1",
        wedding_plan.CHOSEN_VENDOR_STATUSES,
    ).fetchone()
    if vendor and vendor["portions_ordered"] is not None and confirmed > 0 \
            and vendor["portions_ordered"] != confirmed:
        deadline = next(
            (m["date_label"] for m in wedding_plan.list_milestones(db_conn)["milestones"]
             if m["kind"] == "headcount" and not m["completed"]),
            "",
        )
        engine["catering"] = {
            "vendor_id": vendor["id"],
            "portions": vendor["portions_ordered"],
            "diff": confirmed - vendor["portions_ordered"],
            "deadline": deadline,
        }

    if pending_invitations:
        engine["pending_with_phone"] = db_conn.execute(
            "SELECT COUNT(*) FROM wedding_guests WHERE status='pending' "
            "AND phone IS NOT NULL AND TRIM(phone) != ''"
        ).fetchone()[0]
    return engine


@router.get("/wedding/guests", response_class=HTMLResponse)
async def wedding_guests_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    group_filter  = request.query_params.get("group", "")
    status_filter = request.query_params.get("status", "")
    phone_filter  = request.query_params.get("phone", "")  # "has" or "none"

    query  = "SELECT * FROM wedding_guests WHERE 1=1"
    params: list = []
    if group_filter:
        query += " AND group_name=?"
        params.append(group_filter)
    if status_filter:
        query += " AND status=?"
        params.append(status_filter)
    if phone_filter == "has":
        query += " AND phone IS NOT NULL AND phone != ''"
    elif phone_filter == "none":
        query += " AND (phone IS NULL OR phone = '')"
    query += " ORDER BY group_name, name"

    guests = [dict(g) for g in db_conn.execute(query, params).fetchall()]

    total_invitations = db_conn.execute("SELECT COUNT(*) FROM wedding_guests").fetchone()[0]
    try:
        # Expected attendance — excludes declined guests so cards sum back to this total.
        total_people = db_conn.execute(
            "SELECT COALESCE(SUM(1 + CASE WHEN plus_one=1 THEN 1 ELSE 0 END + COALESCE(children_count,0)), 0) FROM wedding_guests WHERE status != 'declined'"
        ).fetchone()[0]
    except Exception:
        total_people = total_invitations
    confirmed    = db_conn.execute("SELECT COUNT(*) FROM wedding_guests WHERE status='confirmed'").fetchone()[0]
    declined     = db_conn.execute("SELECT COUNT(*) FROM wedding_guests WHERE status='declined'").fetchone()[0]
    maybe_count  = db_conn.execute("SELECT COUNT(*) FROM wedding_guests WHERE status='maybe'").fetchone()[0]
    pending      = db_conn.execute("SELECT COUNT(*) FROM wedding_guests WHERE status='pending'").fetchone()[0]
    needs_transport = db_conn.execute("SELECT COUNT(*) FROM wedding_guests WHERE needs_transport=1").fetchone()[0]
    plus_ones    = db_conn.execute(
        "SELECT COUNT(*) FROM wedding_guests WHERE plus_one=1"
    ).fetchone()[0]
    try:
        children_total = db_conn.execute(
            "SELECT COALESCE(SUM(children_count), 0) FROM wedding_guests"
        ).fetchone()[0]
    except Exception:
        children_total = 0

    groups = [r[0] for r in db_conn.execute(
        "SELECT DISTINCT group_name FROM wedding_guests WHERE group_name IS NOT NULL AND group_name!='' ORDER BY group_name"
    ).fetchall()]

    engine = _guest_count_engine(db_conn, pending)

    return templates.TemplateResponse(request, "wedding/guests.html", {
        "request": request,
        "engine": engine,
        "guests": guests,
        "group_filter": group_filter,
        "status_filter": status_filter,
        "phone_filter": phone_filter,
        "total": total_invitations,
        "confirmed": confirmed,
        "declined": declined,
        "maybe_count": maybe_count,
        "pending": pending,
        "needs_transport": needs_transport,
        "plus_ones": plus_ones,
        "children_total": children_total,
        "total_invitations": total_invitations,
        "total_people": total_people,
        "groups": groups,
    })


@router.get("/wedding/tasks", response_class=HTMLResponse)
async def wedding_tasks_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    category_filter = request.query_params.get("category", "")
    show_completed  = request.query_params.get("show_completed", "0")

    query  = "SELECT * FROM wedding_tasks WHERE 1=1"
    params: list = []
    if category_filter:
        query += " AND category=?"
        params.append(category_filter)
    if show_completed != "1":
        query += " AND completed=0"
    query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date ASC, created_at ASC"

    tasks = [dict(t) for t in db_conn.execute(query, params).fetchall()]

    total_open = db_conn.execute("SELECT COUNT(*) FROM wedding_tasks WHERE completed=0").fetchone()[0]
    total_done = db_conn.execute("SELECT COUNT(*) FROM wedding_tasks WHERE completed=1").fetchone()[0]

    return templates.TemplateResponse(request, "wedding/tasks.html", {
        "request": request,
        "tasks": tasks,
        "category_filter": category_filter,
        "show_completed": show_completed,
        "total_open": total_open,
        "total_done": total_done,
        **_mobile_task_board(request, db_conn),
    })


# Mobile task list sections, in display order: (key, heading, heading color).
_TASK_GROUPS = (
    ("overdue", "באיחור", "#b91c1c"),
    ("week", "השבוע", "#6b7280"),
    ("later", "בהמשך", "#6b7280"),
    ("nodate", "ללא תאריך", "#6b7280"),
    ("done", "הושלמו", "#9ca3af"),
)
_TASK_CATEGORY_LABELS = {
    "venue": "מקום", "vendors": "ספקים", "guests": "מוזמנים",
    "logistics": "לוגיסטיקה", "attire": "לבוש", "general": "כללי",
}


def _mobile_task_board(request: Request, db_conn: sqlite3.Connection) -> dict:
    """Every wedding task grouped by urgency, with owners, for the mobile list."""
    from ..services.people import find_person
    from ..services.today import task_group, urgency

    today = date.today()
    people = household(db_conn)
    me = find_person(people, getattr(request.state, "user", None) or request.session.get("user"))
    by_name = {p["name"]: p for p in people}

    rows = [dict(t) for t in db_conn.execute(
        "SELECT * FROM wedding_tasks ORDER BY completed, "
        "COALESCE(NULLIF(due_date, ''), '9999-12-31'), "
        "CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id"
    ).fetchall()]
    groups = {key: [] for key, _, _ in _TASK_GROUPS}
    for t in rows:
        due = hd.parse_iso(t.get("due_date"))
        t["open_group"] = task_group({**t, "completed": 0}, today)
        t["urgency"] = urgency(due, today)
        t["due_label"] = hd.due_label(due, today) if due else ""
        t["category_label"] = _TASK_CATEGORY_LABELS.get(t.get("category"), t.get("category") or "")
        t["person"] = by_name.get(t.get("owner"))
        groups[task_group(t, today)].append(t)
    # Most recently finished first; completed rows carry no timestamp, so newest id first.
    groups["done"].sort(key=lambda t: t["id"], reverse=True)

    open_tasks = [t for t in rows if not t["completed"]]
    owner_counts = {p["name"]: sum(1 for t in open_tasks if t.get("owner") == p["name"]) for p in people}
    return {
        "people": people,
        "me": me,
        "task_groups": [
            {"key": key, "label": label, "color": color, "tasks": groups[key]}
            for key, label, color in _TASK_GROUPS
        ],
        "owner_counts": owner_counts,
        "open_count": len(open_tasks),
        "unassigned_count": sum(1 for t in open_tasks if not t["person"]),
    }


@router.get("/wedding/budget", response_class=HTMLResponse)
async def wedding_budget_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    # Load user-defined total budget (guests × avg per guest + our addition)
    total_budget, budget_guest_count, budget_avg_per_guest, budget_our_addition = \
        _wedding_total_budget(db_conn)

    # Vendor-derived rows — only vendors with a closed deal enter the budget
    vendor_rows = db_conn.execute(
        """
        SELECT category,
               COUNT(*) AS cnt,
               COALESCE(SUM(price_quoted), 0) AS budgeted,
               COALESCE(SUM(CASE WHEN status='fully_paid' THEN price_quoted
                                 WHEN status='deposit_paid' THEN deposit_amount
                                 ELSE 0 END), 0) AS paid
        FROM wedding_vendors
        WHERE status IN ('deal_closed', 'deposit_paid', 'fully_paid')
        GROUP BY category
        ORDER BY category
        """
    ).fetchall()
    vendor_rows = [dict(r) for r in vendor_rows]

    # Manual budget items
    manual_items = [dict(r) for r in db_conn.execute(
        "SELECT * FROM wedding_budget_items ORDER BY category, name"
    ).fetchall()]

    # Totals
    total_vendors_budgeted = sum(r["budgeted"] for r in vendor_rows)
    total_vendors_paid     = sum(r["paid"] for r in vendor_rows)
    total_manual_budgeted  = sum(i["budgeted_amount"] for i in manual_items)
    total_manual_actual    = sum(i["actual_amount"] for i in manual_items)

    # grand_committed = what's been committed from the total budget
    # (closed-deal vendor prices + manual actuals)
    grand_committed = total_vendors_budgeted + total_manual_actual
    grand_paid      = total_vendors_paid + total_manual_actual
    grand_left      = total_budget - grand_committed

    return templates.TemplateResponse(request, "wedding/budget.html", {
        "request": request,
        "total_budget": total_budget,
        "vendor_rows": vendor_rows,
        "manual_items": manual_items,
        "total_vendors_budgeted": total_vendors_budgeted,
        "total_vendors_paid": total_vendors_paid,
        "total_manual_budgeted": total_manual_budgeted,
        "total_manual_actual": total_manual_actual,
        "grand_committed": grand_committed,
        "grand_paid": grand_paid,
        "grand_left": grand_left,
        "budget_guest_count": budget_guest_count,
        "budget_avg_per_guest": budget_avg_per_guest,
        "budget_our_addition": budget_our_addition,
    })


@router.get("/wedding/notes", response_class=HTMLResponse)
async def wedding_notes_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    notes = [dict(r) for r in db_conn.execute(
        "SELECT * FROM wedding_notes ORDER BY pinned DESC, updated_at DESC"
    ).fetchall()]
    return templates.TemplateResponse(request, "wedding/notes.html", {"request": request, "notes": notes})


@router.get("/wedding/ideas", response_class=HTMLResponse)
async def wedding_ideas_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    category_filter = request.query_params.get("category", "")
    status_filter   = request.query_params.get("status", "")
    query  = "SELECT * FROM wedding_ideas WHERE 1=1"
    params: list = []
    if category_filter:
        query += " AND category=?"
        params.append(category_filter)
    if status_filter:
        query += " AND status=?"
        params.append(status_filter)
    query += " ORDER BY CASE status WHEN 'approved' THEN 1 WHEN 'new' THEN 2 WHEN 'considering' THEN 3 ELSE 4 END, created_at DESC"
    ideas = [dict(r) for r in db_conn.execute(query, params).fetchall()]
    all_categories = [r[0] for r in db_conn.execute(
        "SELECT DISTINCT category FROM wedding_ideas ORDER BY category"
    ).fetchall()]
    return templates.TemplateResponse(request, "wedding/ideas.html", {
        "request": request,
        "ideas": ideas,
        "category_filter": category_filter,
        "status_filter": status_filter,
        "all_categories": all_categories,
    })


@router.get("/wedding/overseas", response_class=HTMLResponse)
async def wedding_overseas_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    from ..services import overseas
    from ..services.people import find_person
    people = household(db_conn)
    me = find_person(people, getattr(request.state, "user", None) or request.session.get("user"))
    by_name = {p["name"]: p for p in people}
    items = overseas.load_items(db_conn)
    for item in items:
        for c in item["comments"]:
            c["person"] = by_name.get(c["author"])
    return templates.TemplateResponse(request, "wedding/overseas.html", {
        "request": request,
        "deadline": overseas.deadline(db_conn),
        "lanes": overseas.lanes(items),
        "item_count": len(items),
        "people": people,
        "me": me,
        "headcount": wedding_plan.headcount(db_conn),
        "stages": overseas.STAGE_LABELS,
        "stores": overseas.STORES,
    })


@router.get("/wedding/seating", response_class=HTMLResponse)
async def wedding_seating_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    tables = [dict(r) for r in db_conn.execute(
        "SELECT * FROM wedding_seating_tables ORDER BY created_at"
    ).fetchall()]
    all_guests = [dict(r) for r in db_conn.execute(
        "SELECT id, name, group_name, status, plus_one, plus_one_name, children_count FROM wedding_guests WHERE status != 'declined' ORDER BY group_name, name"
    ).fetchall()]
    assignments = [dict(r) for r in db_conn.execute(
        "SELECT table_id, seat_number, guest_id FROM wedding_seating_assignments"
    ).fetchall()]
    seated_ids = {a["guest_id"] for a in assignments}
    total_guests = sum(1 + (g["plus_one"] or 0) + (g["children_count"] or 0) for g in all_guests)
    seated_count = sum(1 + (g["plus_one"] or 0) + (g["children_count"] or 0) for g in all_guests if g["id"] in seated_ids)
    total_seats = sum(t["capacity"] for t in tables)
    return templates.TemplateResponse(request, "wedding/seating.html", {
        "request": request,
        "tables": tables,
        "all_guests": all_guests,
        "assignments": assignments,
        "seated_count": seated_count,
        "total_guests": total_guests,
        "total_seats": total_seats,
    })


@router.get("/invite/{token}", response_class=HTMLResponse)
@public
async def invite_rsvp_page(token: str, request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    guest = db_conn.execute(
        "SELECT * FROM wedding_guests WHERE invite_token=?", (token,)
    ).fetchone()
    if not guest:
        return templates.TemplateResponse(
            request,
            "wedding/invite_invalid.html",
            {"request": request},
            status_code=404,
        )
    wedding_date_row = db_conn.execute("SELECT value FROM wedding_settings WHERE key='wedding_date'").fetchone()
    wedding_date = wedding_date_row[0] if wedding_date_row else None
    return templates.TemplateResponse(
        request,
        "wedding/invite.html",
        {
            "request": request,
            "guest": dict(guest),
            "token": token,
            "wedding_date": wedding_date,
        },
    )


@router.post("/invite/{token}/rsvp", response_class=HTMLResponse)
@public
async def invite_rsvp_submit(token: str, request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    guest = db_conn.execute(
        "SELECT * FROM wedding_guests WHERE invite_token=?", (token,)
    ).fetchone()
    if not guest:
        return templates.TemplateResponse(
            request,
            "wedding/invite_invalid.html",
            {"request": request},
            status_code=404,
        )

    form = await request.form()
    attending = form.get("attending", "no")
    status = "confirmed" if attending == "yes" else "declined"

    plus_one = 0
    children_count = 0
    food_preference = None
    food_allergies = None
    needs_transport = 0
    staying_overnight = 0
    notes = None

    meal_type_update = None

    if attending == "yes":
        total_adults_raw = form.get("total_adults", "1")
        try:
            total_adults = max(1, int(total_adults_raw))
        except Exception:
            total_adults = 1
        plus_one = 1 if total_adults >= 2 else 0
        children_count_raw = form.get("children_count", "0")
        try:
            children_count = max(0, int(children_count_raw))
        except Exception:
            children_count = 0
        food_preference = form.get("food_preference") or None
        food_allergies = (form.get("food_allergies") or "").strip() or None
        needs_transport = 1 if form.get("needs_transport") == "yes" else 0
        staying_overnight = 1 if form.get("staying_overnight") == "yes" else 0
        notes = (form.get("notes") or "").strip() or None

        # Map RSVP food_preference to admin meal_type so it appears in the guest list
        _pref_map = {"meat": "regular", "vegan": "vegan", "gluten_free": "gluten_free"}
        meal_type_update = _pref_map.get(food_preference) if food_preference else None

    from datetime import datetime as _dt
    submitted_at = _dt.now().strftime("%Y-%m-%d %H:%M:%S")

    db_conn.execute(
        """UPDATE wedding_guests
           SET status=?, plus_one=?, children_count=?, food_preference=?,
               food_allergies=?, needs_transport=?, staying_overnight=?,
               notes=?, rsvp_submitted_at=?,
               meal_type=CASE WHEN ? IS NOT NULL THEN ? ELSE meal_type END,
               food_notes=CASE WHEN ? IS NOT NULL THEN ? ELSE food_notes END
           WHERE invite_token=?""",
        (status, plus_one, children_count, food_preference,
         food_allergies, needs_transport, staying_overnight,
         notes, submitted_at,
         meal_type_update, meal_type_update,
         food_allergies, food_allergies,
         token),
    )
    db_conn.commit()

    return templates.TemplateResponse(
        request,
        "wedding/invite_success.html",
        {
            "request": request,
            "guest": dict(guest),
            "attending": attending,
            "status": status,
        },
    )


@router.get("/wedding/timeline", response_class=HTMLResponse)
async def wedding_timeline_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    events = db_conn.execute(
        "SELECT * FROM wedding_timeline_events ORDER BY day, start_time"
    ).fetchall()
    return templates.TemplateResponse(request, "wedding/timeline.html", {
        "request": request,
        "events": [dict(e) for e in events],
    })


@router.get("/wedding/milestones", response_class=HTMLResponse)
async def wedding_milestones_page(request: Request, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    view = wedding_plan.list_milestones(db_conn)
    for m in view["milestones"]:
        # How the row reads when not completed, so un-ticking a done row can
        # render immediately; the page re-fetch then settles which one is next.
        late = m["days_until"] is not None and m["days_until"] < 0
        if m["status"] != "done":
            m["open_status"] = m["status"]
        else:
            m["open_status"] = "overdue" if late else "future"
        m["late_label"] = hd.overdue_label(-m["days_until"]) if late else ""
    return templates.TemplateResponse(request, "wedding/milestones.html", {
        "request": request,
        "view": view,
    })