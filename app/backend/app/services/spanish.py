"""
Spanish between sets — the spacing engine.

The deck is a static file (`static/spanish/deck.json`); the only thing stored is one
`spanish_reviews` row per graded card. Everything else — an item's stage, when it is due,
"words in your pocket", the review-day streak, per-theme progress — is replayed from those
rows at read time, the same way the workouts game derives XP and conquered stations.

Stage ladder (days until the item is due again): 0, 1, 3, 7, 14, 30, 60, 120.
- intro (first meeting): stage 0, due now.
- recall grade 0 (שוב): stage 0, due now.   1 (קשה): stage kept (at least 1).
- recall grade 2 (טוב): stage + 1.          3 (קל): stage + 2.   Capped at stage 7.
Due dates are day-granular: an item is due when `today >= due_on`.

All functions are pure over dicts/rows except `fetch_reviews` / `record_review`.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parents[3]
DECK_PATH = ROOT_DIR / "frontend" / "static" / "spanish" / "deck.json"

INTERVALS = [0, 1, 3, 7, 14, 30, 60, 120]
MAX_STAGE = len(INTERVALS) - 1
POCKET_STAGE = 3      # interval >= 7 days: the word survived a week
MASTERED_STAGE = 6
DEFAULT_NEW_CAP = 8
STUDY_NEW_CAP = 15

GRADES = {0: "שוב", 1: "קשה", 2: "טוב", 3: "קל"}
MODES = ("intro", "recall")
CONTEXTS = ("rest", "study")

_deck_cache: Dict[str, Any] = {"stamp": None, "deck": None}


# ---------------------------------------------------------------- deck

def load_deck(path: Optional[Path] = None) -> Dict[str, Any]:
    """The deck, cached by file mtime, with lookups added (`by_id`, `order`, `theme_titles`)."""
    path = path or DECK_PATH
    stat = path.stat()
    stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    if _deck_cache["stamp"] != stamp:
        raw = json.loads(path.read_text(encoding="utf-8"))
        themes = sorted(raw["themes"], key=lambda t: t["order"])
        items = raw["items"]
        _deck_cache["deck"] = {
            "version": raw.get("version", 1),
            "themes": themes,
            "items": items,
            "by_id": {it["id"]: it for it in items},
            "order": {it["id"]: n for n, it in enumerate(items)},
            "theme_titles": {t["key"]: t["title"] for t in themes},
        }
        _deck_cache["stamp"] = stamp
    return _deck_cache["deck"]


def item_exists(item_id: str) -> bool:
    return item_id in load_deck()["by_id"]


# ---------------------------------------------------------------- replay

def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _day(value: Any) -> date_cls:
    return _parse_dt(value).date()


def apply_review(state: Optional[Dict[str, Any]], grade: int, mode: str, reviewed_at: Any) -> Dict[str, Any]:
    """One review applied to an item's state (None = never seen). Returns the new state."""
    when = _parse_dt(reviewed_at)
    stage = state["stage"] if state else 0
    if mode == "intro" or grade <= 0:
        stage = 0
    elif grade == 1:
        stage = max(stage, 1)
    elif grade == 2:
        stage = min(stage + 1, MAX_STAGE)
    else:
        stage = min(stage + 2, MAX_STAGE)
    return {
        "stage": stage,
        "due_on": when.date() + timedelta(days=INTERVALS[stage]),
        "last_reviewed": when,
        "reviews": (state["reviews"] if state else 0) + 1,
        "lapses": (state["lapses"] if state else 0) + (1 if mode == "recall" and grade <= 0 else 0),
    }


def _sorted_reviews(reviews: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(reviews, key=lambda r: (_parse_dt(r["reviewed_at"]), r.get("id") or 0))


def item_states(reviews: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Replay every review in `reviewed_at` order → {item_id: state}. Unseen items are absent."""
    states: Dict[str, Dict[str, Any]] = {}
    for r in _sorted_reviews(reviews):
        states[r["item_id"]] = apply_review(states.get(r["item_id"]), int(r["grade"]), r["mode"], r["reviewed_at"])
    return states


def intros_on(reviews: Iterable[Dict[str, Any]], day: date_cls) -> int:
    return sum(1 for r in reviews if r["mode"] == "intro" and _day(r["reviewed_at"]) == day)


def review_days_streak(review_days: Set[date_cls], today: date_cls) -> int:
    """Consecutive days with at least one review, ending today — or yesterday, so a streak
    is not lost in the morning before today's first card."""
    if today in review_days:
        day = today
    elif today - timedelta(days=1) in review_days:
        day = today - timedelta(days=1)
    else:
        return 0
    count = 0
    while day in review_days:
        count += 1
        day -= timedelta(days=1)
    return count


# ---------------------------------------------------------------- queue + stats

def _card(item: Dict[str, Any], deck: Dict[str, Any], mode: str, stage: int) -> Dict[str, Any]:
    return {
        "id": item["id"],
        "theme": item["theme"],
        "theme_title": deck["theme_titles"].get(item["theme"], ""),
        "es": item["es"],
        "he": item["he"],
        "target_es": item["target_es"],
        "target_he": item["target_he"],
        "note": item.get("note", ""),
        "mode": mode,
        "stage": stage,
    }


def build_queue(
    deck: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    today: date_cls,
    limit: int = 15,
    new_cap: int = DEFAULT_NEW_CAP,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Due recall items first (oldest due first), then new items in deck order, the new ones
    capped at `new_cap` minus the intros already recorded today."""
    states = item_states(reviews) if states is None else states
    order = deck["order"]
    due = sorted(
        (iid for iid, st in states.items() if iid in deck["by_id"] and st["due_on"] <= today),
        key=lambda iid: (states[iid]["due_on"], states[iid]["last_reviewed"], order[iid]),
    )
    cards = [_card(deck["by_id"][iid], deck, "recall", states[iid]["stage"]) for iid in due]

    new_left = max(0, new_cap - intros_on(reviews, today))
    for item in deck["items"]:
        if new_left <= 0 or len(cards) >= limit:
            break
        if item["id"] not in states:
            cards.append(_card(item, deck, "intro", 0))
            new_left -= 1
    return cards[:max(0, limit)]


def stats(
    deck: Dict[str, Any],
    reviews: List[Dict[str, Any]],
    today: date_cls,
    new_cap: int = DEFAULT_NEW_CAP,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Everything the stats row, the profile card and the theme list show."""
    states = item_states(reviews) if states is None else states
    known = {iid: st for iid, st in states.items() if iid in deck["by_id"]}
    unseen = len(deck["items"]) - len(known)
    per_theme = {t["key"]: {"total": 0, "in_pocket": 0} for t in deck["themes"]}
    for item in deck["items"]:
        bucket = per_theme.setdefault(item["theme"], {"total": 0, "in_pocket": 0})
        bucket["total"] += 1
        st = known.get(item["id"])
        if st and st["stage"] >= POCKET_STAGE:
            bucket["in_pocket"] += 1
    reviews_today = [r for r in reviews if _day(r["reviewed_at"]) == today]
    return {
        "total": len(deck["items"]),
        "seen": len(known),
        "in_pocket": sum(1 for st in known.values() if st["stage"] >= POCKET_STAGE),
        "learning": sum(1 for st in known.values() if 1 <= st["stage"] <= 2),
        "mastered": sum(1 for st in known.values() if st["stage"] >= MASTERED_STAGE),
        "due_today": sum(1 for st in known.values() if st["due_on"] <= today),
        "new_today_left": min(unseen, max(0, new_cap - intros_on(reviews, today))),
        "reviews_today": len(reviews_today),
        "review_days_streak": review_days_streak({_day(r["reviewed_at"]) for r in reviews}, today),
        "per_theme": per_theme,
    }


def theme_progress(deck: Dict[str, Any], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Themes in deck order with their `in_pocket / total`, for the #spanish view."""
    rows = []
    for t in deck["themes"]:
        counts = summary["per_theme"].get(t["key"], {"total": 0, "in_pocket": 0})
        total = counts["total"]
        rows.append({
            "key": t["key"],
            "title": t["title"],
            "total": total,
            "in_pocket": counts["in_pocket"],
            "pct": round(100 * counts["in_pocket"] / total) if total else 0,
        })
    return rows


# ---------------------------------------------------------------- the two DB touch points

def fetch_reviews(db_conn: sqlite3.Connection, user_id: int) -> List[Dict[str, Any]]:
    rows = db_conn.execute(
        "SELECT id, item_id, reviewed_at, grade, mode, context FROM spanish_reviews "
        "WHERE user_id = ? ORDER BY reviewed_at, id",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def record_review(
    db_conn: sqlite3.Connection,
    user_id: int,
    item_id: str,
    grade: int,
    mode: str,
    context: str = "rest",
    reviewed_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    when = (reviewed_at or datetime.now()).replace(microsecond=0)
    cur = db_conn.execute(
        "INSERT INTO spanish_reviews (user_id, item_id, reviewed_at, grade, mode, context) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, item_id, when.isoformat(), grade, mode, context),
    )
    db_conn.commit()
    return {"id": cur.lastrowid, "item_id": item_id, "reviewed_at": when.isoformat(),
            "grade": grade, "mode": mode, "context": context}


def snapshot(
    db_conn: sqlite3.Connection,
    user_id: int,
    today: Optional[date_cls] = None,
    limit: int = 15,
    new_cap: int = DEFAULT_NEW_CAP,
) -> Dict[str, Any]:
    """Queue + stats for one user in one read (what the page and the queue endpoint ship)."""
    today = today or date_cls.today()
    deck = load_deck()
    reviews = fetch_reviews(db_conn, user_id)
    states = item_states(reviews)
    return {
        "items": build_queue(deck, reviews, today, limit=limit, new_cap=new_cap, states=states),
        "stats": stats(deck, reviews, today, new_cap=new_cap, states=states),
    }
