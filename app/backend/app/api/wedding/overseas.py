from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ...db import get_db_conn
from ...schemas.wedding import (
    OverseasCommentCreate,
    OverseasItemCreate,
    OverseasItemUpdate,
)
from ...services import overseas
from ...services.people import find_person, household, valid_owner

router = APIRouter(prefix="/api/wedding", tags=["wedding"])


# ─── Overseas orders (הזמנות מחו״ל) ────────────────────────────────────────────

def _session_person_name(request: Request, db_conn: sqlite3.Connection) -> str | None:
    user = getattr(request.state, "user", None) or request.session.get("user")
    person = find_person(household(db_conn), user)
    return person["name"] if person else None


def _household_name(db_conn: sqlite3.Connection, value: str | None) -> str | None:
    try:
        return valid_owner(db_conn, value)
    except ValueError:
        raise HTTPException(status_code=422, detail="משתמש לא מוכר")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _clean_url(value: str | None) -> str | None:
    """A store link the page may render as an href: http(s) only."""
    value = _clean_text(value)
    if value is not None and not value.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="קישור לא תקין")
    return value


@router.get("/overseas")
async def list_overseas(db_conn: sqlite3.Connection = Depends(get_db_conn)):
    items = overseas.load_items(db_conn)
    return {"deadline": overseas.deadline(db_conn), "lanes": overseas.lanes(items)}


@router.post("/overseas", status_code=201)
async def create_overseas_item(body: OverseasItemCreate, request: Request,
                               db_conn: sqlite3.Connection = Depends(get_db_conn)):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="יש להזין שם פריט")
    if body.created_by is not None:
        created_by = _household_name(db_conn, body.created_by)
    else:
        created_by = _session_person_name(request, db_conn)
    cur = db_conn.execute(
        "INSERT INTO wedding_overseas_items (title, url, store, sample_price, quantity_needed, created_by) "
        "VALUES (?,?,?,?,?,?)",
        (title, _clean_url(body.url), _clean_text(body.store), body.sample_price,
         body.quantity_needed, created_by),
    )
    db_conn.commit()
    return overseas.load_item(db_conn, cur.lastrowid)


@router.put("/overseas/{item_id}")
async def update_overseas_item(item_id: int, body: OverseasItemUpdate,
                               db_conn: sqlite3.Connection = Depends(get_db_conn)):
    existing = db_conn.execute("SELECT * FROM wedding_overseas_items WHERE id=?", (item_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    updates = body.model_dump(exclude_unset=True)
    if "title" in updates:
        title = (updates["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail="יש להזין שם פריט")
        updates["title"] = title
    if "url" in updates:
        updates["url"] = _clean_url(updates["url"])
    if "store" in updates:
        updates["store"] = _clean_text(updates["store"])
    if "stage" in updates:
        if updates["stage"] not in overseas.STAGES:
            raise HTTPException(status_code=422, detail="שלב לא מוכר")
        updates.update(overseas.stage_transition(existing, updates["stage"]))
    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates) + ", updated_at=CURRENT_TIMESTAMP"
        db_conn.execute(
            f"UPDATE wedding_overseas_items SET {set_clause} WHERE id=?",
            (*updates.values(), item_id),
        )
        db_conn.commit()
    return overseas.load_item(db_conn, item_id)


@router.delete("/overseas/{item_id}", status_code=204)
async def delete_overseas_item(item_id: int, db_conn: sqlite3.Connection = Depends(get_db_conn)):
    db_conn.execute("DELETE FROM wedding_overseas_items WHERE id=?", (item_id,))
    db_conn.commit()


@router.post("/overseas/{item_id}/comments", status_code=201)
async def create_overseas_comment(item_id: int, body: OverseasCommentCreate, request: Request,
                                  db_conn: sqlite3.Connection = Depends(get_db_conn)):
    if not db_conn.execute("SELECT 1 FROM wedding_overseas_items WHERE id=?", (item_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Item not found")
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="ההערה ריקה")
    if body.author is not None:
        author = _household_name(db_conn, body.author)
    else:
        author = _session_person_name(request, db_conn)
    # Local time, so "היום / אתמול" on the thread follows the household's day, not UTC.
    cur = db_conn.execute(
        "INSERT INTO wedding_overseas_comments (item_id, author, body, created_at) "
        "VALUES (?,?,?, datetime('now','localtime'))",
        (item_id, author, text),
    )
    db_conn.commit()
    row = db_conn.execute(
        "SELECT id, item_id, author, body, created_at FROM wedding_overseas_comments WHERE id=?",
        (cur.lastrowid,),
    ).fetchone()
    return dict(row)
