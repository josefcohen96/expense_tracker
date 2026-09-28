"""
קריאה לזירה — Web Push notifications from the workouts arena.

Two daily pushes per trainee, both derived at send time from the same inputs as the
workouts page (history → gamification → paths → plan_today):
- morning (08:40): today's mission card, or the rest-day note after a long run;
- evening (21:00): only on a day without a workout, naming the streak that ends at midnight.

Only the browser subscription (endpoint + keys) is stored (`push_subscriptions`); a
`system_settings` key `push_sent:<kind>:<YYYY-MM-DD>` makes a scheduled run send once a day.
The feature is off (no jobs, `enabled: false`) unless both VAPID env vars are set.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TIMEZONE = "Asia/Jerusalem"
MORNING_TIME = (8, 40)
EVENING_TIME = (21, 0)
DEFAULT_SUBJECT = "mailto:admin@example.com"
ICON = "/static/icons/icon-192.png"
PUSH_TTL_SECONDS = 4 * 3600   # a call that arrives hours late is no longer a call
DEAD_STATUSES = (404, 410)    # the push service says the subscription is gone


# ---------------------------------------------------------------- config

def vapid_config() -> Optional[Dict[str, str]]:
    """The VAPID keys from env, or None when the feature is off."""
    public_key = (os.environ.get("VAPID_PUBLIC_KEY") or "").strip()
    private_key = (os.environ.get("VAPID_PRIVATE_KEY") or "").strip()
    if not public_key or not private_key:
        return None
    subject = (os.environ.get("VAPID_SUBJECT") or "").strip() or DEFAULT_SUBJECT
    return {"public_key": public_key, "private_key": private_key, "subject": subject}


def is_enabled() -> bool:
    return vapid_config() is not None


# ---------------------------------------------------------------- subscriptions

def save_subscription(conn: sqlite3.Connection, user_id: int, endpoint: str, p256dh: str, auth: str) -> None:
    """Upsert on endpoint: a shared phone follows whoever subscribed last."""
    conn.execute(
        """
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET
            user_id = excluded.user_id,
            p256dh = excluded.p256dh,
            auth = excluded.auth
        """,
        (user_id, endpoint, p256dh, auth),
    )
    conn.commit()


def delete_subscription(conn: sqlite3.Connection, user_id: int, endpoint: str) -> int:
    """Remove the caller's own row for this endpoint; returns how many were removed."""
    cur = conn.execute(
        "DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint)
    )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------- sending

def payload(title: str, body: str, url: str, tag: str) -> Dict[str, Any]:
    return {"title": title, "body": body, "url": url, "tag": tag,
            "icon": ICON, "lang": "he", "dir": "rtl"}


def _webpush_send(subscription_info: Dict[str, Any], data: str, config: Dict[str, str]) -> None:
    """The one network call. Imported lazily so the app runs without pywebpush installed."""
    from pywebpush import webpush

    webpush(
        subscription_info=subscription_info,
        data=data,
        vapid_private_key=config["private_key"],
        vapid_claims={"sub": config["subject"]},
        ttl=PUSH_TTL_SECONDS,
    )


def _status_of(exc: Exception) -> Optional[int]:
    """HTTP status of a failed send: requests' `.status_code` or aiohttp's `.status`."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    return getattr(response, "status_code", None) or getattr(response, "status", None)


def send_to_user(conn: sqlite3.Connection, user_id: int, message: Dict[str, Any]) -> int:
    """Push `message` to every device of `user_id`; returns how many accepted it.

    A 404/410 from the push service means the browser dropped the subscription, so the row goes.
    """
    config = vapid_config()
    if config is None:
        return 0
    rows = conn.execute(
        "SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?", (user_id,)
    ).fetchall()
    data = json.dumps(message, ensure_ascii=False)
    sent = 0
    for row in rows:
        info = {"endpoint": row["endpoint"], "keys": {"p256dh": row["p256dh"], "auth": row["auth"]}}
        try:
            _webpush_send(info, data, config)
            sent += 1
        except Exception as exc:  # pywebpush.WebPushException, network errors, a missing package
            status = _status_of(exc)
            if status in DEAD_STATUSES:
                conn.execute("DELETE FROM push_subscriptions WHERE id = ?", (row["id"],))
                conn.commit()
                logger.info("push: removed dead subscription %s (HTTP %s)", row["id"], status)
            else:
                logger.warning("push: send to subscription %s failed: %s", row["id"], exc)
    return sent


# ---------------------------------------------------------------- the texts

def _arena_state(conn: sqlite3.Connection, user_id: int, today: date_cls):
    """History, game state and paths exactly as the workouts page derives them."""
    from ..routes import workouts as wk  # lazy: routes import services

    history = wk._fetch_history(conn, user_id)
    game = wk.compute_gamification(history, today)
    paths = wk.compute_paths(history, game["level"], wk._load_legacy_progress(conn, user_id), today)
    return history, game, paths


def _days_word(n: int) -> str:
    return "יום אחד" if n == 1 else f"{n} ימים"


def morning_message(conn: sqlite3.Connection, user_id: int, today: date_cls) -> Optional[Dict[str, Any]]:
    """Today's mission card, or the rest day `plan_today` recommends after a long run."""
    from ..routes import workouts as wk

    history, game, paths = _arena_state(conn, user_id, today)
    default_path, _note = wk.plan_today(paths, history, today)

    # The same run plan_today measures for its recovery note: days in a row ending yesterday.
    days = wk._workout_days(s["date"] for s in history)
    yesterday = today - timedelta(days=1)
    run = wk._current_streak(days, yesterday) if days and max(days) == yesterday else 0
    if run >= wk.RECOVERY_STREAK_DAYS:
        return payload("☀️ בוקר טוב — יום מנוחה", f"{run} ימים ברצף. היום נחים, והכוח נבנה.",
                       "/workouts#home", "arena-morning")

    path = next((p for p in paths if p["key"] == default_path), paths[0])
    body = f"{path['icon']} {path['name']}"
    if path["current"]:
        body += f" · {path['current']['hebrew']}"
    if game["streak_at_risk"]:
        body += f" · הרצף ({game['current_streak']}) מחכה לך"
    return payload("☀️ המשימה של היום", body, "/workouts#home", "arena-morning")


def evening_message(conn: sqlite3.Connection, user_id: int, today: date_cls) -> Optional[Dict[str, Any]]:
    """None on a day already trained (silence is the reward); otherwise what is at stake."""
    from ..routes import workouts as wk

    history = wk._fetch_history(conn, user_id)
    days = wk._workout_days(s["date"] for s in history)
    if today in days:
        return None
    current = wk._current_streak(days, today)  # alive only thanks to yesterday
    if current > 0:
        return payload("🔥 הרצף בסכנה",
                       f"הרצף של {_days_word(current)} נגמר בחצות. אימון אחד קצר שומר עליו.",
                       "/workouts#home", "arena-evening")
    return payload("🏠 עוד לא מאוחר", "15 דקות בסלון מספיקות להיום.", "/workouts#home", "arena-evening")


def test_message() -> Dict[str, Any]:
    return payload("🔔 קריאה לזירה", "ההתראות עובדות. נתראה בזירה.", "/workouts#profile", "arena-test")


test_message.__test__ = False  # not a pytest test, despite the name


# ---------------------------------------------------------------- the daily run

MESSAGE_BUILDERS = {"morning": morning_message, "evening": evening_message}


def _sent_key(kind: str, today: date_cls) -> str:
    return f"push_sent:{kind}:{today.isoformat()}"


def run_daily(kind: str, today: Optional[date_cls] = None, conn: Optional[sqlite3.Connection] = None) -> int:
    """Send the `kind` push to every subscribed user once per day; returns pushes accepted."""
    if kind not in MESSAGE_BUILDERS:
        raise ValueError(f"unknown push kind: {kind}")
    if not is_enabled():
        return 0
    today = today or datetime.now(ZoneInfo(TIMEZONE)).date()
    own_conn = conn is None
    if own_conn:
        from ..db import get_connection
        conn = get_connection()
    try:
        key = _sent_key(kind, today)
        if conn.execute("SELECT 1 FROM system_settings WHERE key = ?", (key,)).fetchone():
            return 0
        build = MESSAGE_BUILDERS[kind]
        sent = 0
        user_ids = [r["user_id"] for r in conn.execute(
            "SELECT DISTINCT user_id FROM push_subscriptions ORDER BY user_id"
        ).fetchall()]
        for user_id in user_ids:
            try:
                message = build(conn, user_id, today)
            except Exception:
                logger.exception("push: building %s message for user %s failed", kind, user_id)
                continue
            if message is not None:
                sent += send_to_user(conn, user_id, message)
        conn.execute(
            "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, str(sent)),
        )
        conn.commit()
        return sent
    finally:
        if own_conn:
            conn.close()
