"""
תרשום — the household's WhatsApp number: expenses and wedding tasks by chat.

The phone number is the login: a message from Karina's phone is a Karina expense on her
default account, the same text from Yosef's phone lands on his. The grammar is a dozen
deterministic rules in `handle_message()` (no LLM, no menus); `בטל` reverses the sender's
last action, the chat version of the app's undo pill.

Nothing new is stored. The undo state lives in `system_settings` under
`whatsapp_undo:<USERNAME>`; bot expenses carry `transactions.tags = 'whatsapp'`; month
totals, the countdown and the task grouping come from the existing services. The provider
is the Meta WhatsApp Cloud API; every setting is an env var read at call time, so the
feature is off until they are set.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
from collections import deque
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..api.transactions import INCOME_CATEGORIES, _invalidate_stats_cache
from . import hebrew_dates as hd
from . import wedding_plan
from .access import USER_DISPLAY_NAMES, USER_KARINA, USER_YOSEF, display_name, normalise_username
from .people import default_account_id, find_person, household, valid_owner
from .today import month_totals, task_group

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = "v22.0"
SEND_TIMEOUT_SECONDS = 10
TAG = "whatsapp"
UNDO_KEY_PREFIX = "whatsapp_undo:"
# How long `בטל` can reach back. The app's undo pill lives seconds; a chat is slower, but
# a `בטל` sent the next day is not about yesterday's expense.
UNDO_WINDOW = timedelta(hours=24)
MAX_AMOUNT = 1_000_000
LIST_LIMIT = 20
AMBIGUOUS_LIMIT = 8

# Which env var holds whose phone (digits as WhatsApp sends `wa_id`).
PHONE_ENV_BY_USER = {USER_YOSEF: "WHATSAPP_PHONE_YOSEF", USER_KARINA: "WHATSAPP_PHONE_KARINA"}

# ---------------------------------------------------------------- reply texts

HELP_TEXT = (
    "תרשום 📒\n"
    "350 פרחים — הוצאה (אפשר גם: 350 פרחים אתמול)\n"
    "להתקשר לצלם עד חמישי — משימה לחתונה (אני: / יוסף: / קארינה: בהתחלה = אחראי, דחוף = עדיפות גבוהה)\n"
    "משימות / שלי — מה פתוח\n"
    "סיימתי 3 או סיימתי צלם — בוצע\n"
    "לקחתי 3 — המשימה עליי\n"
    "בטל — מבטל את הפעולה האחרונה"
)
NOT_UNDERSTOOD = "לא הבנתי."
TEXT_ONLY = "אני מבין רק טקסט בינתיים 🙂"
SOMETHING_WRONG = "משהו השתבש, נסה שוב"
UNDO_HINT = "בטל — לביטול"
NOTHING_TO_UNDO = "אין מה לבטל"
UNDO_STALE = "הפעולה האחרונה כבר השתנתה באפליקציה, לא בוטל"
NO_SUCH_TASK = "לא מצאתי משימה כזו"
WHICH_ONE = "איזו מהן?"
NO_OPEN_TASKS = "אין משימות פתוחות 🎉"
NO_TASKS_MINE = "אין משימות על שמך"
UNKNOWN_SENDER = "אני מכיר רק את יוסף ואת קארינה"

# ---------------------------------------------------------------- grammar words

UNDO_WORDS = frozenset({"בטל", "ביטול"})
HELP_WORDS = frozenset({"עזרה", "?", "help", "מה אפשר"})
LIST_ALL_WORDS = frozenset({"משימות", "רשימה", "מה יש", "מה נשאר"})
LIST_MINE_WORDS = frozenset({"שלי", "המשימות שלי"})
DONE_WORDS = frozenset({"סיימתי", "בוצע", "עשיתי", "גמרתי", "סגרתי", "✓", "✅", "v"})
TAKE_PREFIXES = ("אני על זה", "אני אעשה", "לקחתי")
YESTERDAY_WORD = "אתמול"
URGENT_WORD = "דחוף"
UNTIL_WORD = "עד"
SELF_OWNER = "אני"
CURRENCY_WORDS = ("ש\"ח", "ש״ח", "שקלים", "שקל", "שח", "₪")
FALLBACK_CATEGORY = "הוצאות בית"
FALLBACK_ACCOUNT = "כרטיס אשראי"

# Hebrew keyword → category names to try in order (a category is used only if it exists in the DB).
# Multi-word keywords come before the single words they contain.
EXPENSE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("סופר פארם", ("בריאות",)),
    ("קופת חולים", ("בריאות",)),
    ("רמי לוי", ("סופר",)),
    ("די ג'יי", ("חתונה",)),
    ("דלק", ("דלק", "רכב")),
    ("תדלוק", ("דלק", "רכב")),
    ("אוטובוס", ("תחבורה",)),
    ("רכבת", ("תחבורה",)),
    ("מונית", ("תחבורה",)),
    ("גט", ("תחבורה",)),
    ("מסעדה", ("אוכל בחוץ",)),
    ("קפה", ("אוכל בחוץ",)),
    ("פיצה", ("אוכל בחוץ",)),
    ("המבורגר", ("אוכל בחוץ",)),
    ("סושי", ("אוכל בחוץ",)),
    ("וולט", ("אוכל בחוץ",)),
    ("רופא", ("בריאות",)),
    ("תרופות", ("בריאות",)),
    ("סרט", ("פנאי",)),
    ("קולנוע", ("פנאי",)),
    ("הופעה", ("פנאי",)),
    ("סופר", ("סופר",)),
    ("שופרסל", ("סופר",)),
    ("מכולת", ("סופר",)),
    ("ויקטורי", ("סופר",)),
    ("צלם", ("חתונה",)),
    ("אולם", ("חתונה",)),
    ("דיג'יי", ("חתונה",)),
    ("שמלה", ("חתונה",)),
    ("חליפה", ("חתונה",)),
    ("הזמנות", ("חתונה",)),
    ("מגנטים", ("חתונה",)),
    ("רב", ("חתונה",)),
    ("טבעות", ("חתונה",)),
    ("קייטרינג", ("חתונה",)),
)
# One-letter Hebrew prefixes a keyword may carry ("בסופר", "לצלם", "הקפה").
_KEYWORD_PREFIXES = "בלהומש"

_AMOUNT_RE = re.compile(r"^\d+(?:[.,]\d{1,2})?$")
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?$")
_DOTTED_DATE_RE = re.compile(r"^(\d{1,2})[./](\d{1,2})(?:[./](\d{2}|\d{4}))?$")
_CURRENCY_SUFFIX_RE = re.compile(r"^(\d[\d,.]*)(?:ש\"ח|ש״ח|שקלים|שקל|שח)$")

# date.weekday(): Monday == 0
_WEEKDAYS = {
    "שני": 0, "שלישי": 1, "רביעי": 2, "חמישי": 3, "שישי": 4, "שבת": 5, "ראשון": 6,
}
_WEEKDAY_LETTERS = {"ב": 0, "ג": 1, "ד": 2, "ה": 3, "ו": 4, "ש": 5, "א": 6}


# ---------------------------------------------------------------- config

def config() -> dict[str, str] | None:
    """The Cloud API settings from env, or None when sending is off."""
    access_token = (os.environ.get("WHATSAPP_ACCESS_TOKEN") or "").strip()
    phone_number_id = (os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    if not access_token or not phone_number_id:
        return None
    api_version = (os.environ.get("WHATSAPP_API_VERSION") or "").strip() or DEFAULT_API_VERSION
    return {"access_token": access_token, "phone_number_id": phone_number_id, "api_version": api_version}


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def sender_for(wa_id: Any) -> str | None:
    """The household username whose phone sent this message, or None for a stranger."""
    sender = _digits(wa_id)
    if not sender:
        return None
    for username, env_name in PHONE_ENV_BY_USER.items():
        phone = _digits(os.environ.get(env_name))
        if phone and hmac.compare_digest(phone, sender):
            return username
    return None


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Meta's `X-Hub-Signature-256: sha256=<hex HMAC of the raw body>`."""
    if not secret or not header:
        return False
    scheme, _, supplied = header.strip().partition("=")
    if scheme.lower() != "sha256" or not supplied:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied.strip().lower().encode("utf-8"), expected.encode("utf-8"))


# ---------------------------------------------------------------- delivery

# Message ids already handled; Meta redelivers on a slow ack. One worker → one process → enough.
_seen_ids: deque[str] = deque(maxlen=256)


def already_seen(message_id: str | None) -> bool:
    """True when this wamid was handled before; otherwise remembers it."""
    if not message_id:
        return False
    if message_id in _seen_ids:
        return True
    _seen_ids.append(message_id)
    return False


def send_text(to: str, text: str, reply_to: str | None = None) -> bool:
    """Send a text reply through the Cloud API; logs and returns False on any failure."""
    cfg = config()
    if cfg is None:
        logger.warning("WhatsApp send skipped: WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID not set")
        return False
    body: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    if reply_to:
        body["context"] = {"message_id": reply_to}
    url = f"https://graph.facebook.com/{cfg['api_version']}/{cfg['phone_number_id']}/messages"
    try:
        import httpx

        response = httpx.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {cfg['access_token']}"},
            timeout=SEND_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            logger.warning("WhatsApp send failed: HTTP %s %s", response.status_code, response.text[:300])
            return False
        return True
    except Exception:
        logger.exception("WhatsApp send failed")
        return False


# ---------------------------------------------------------------- normalisation

def _strip_currency(token: str) -> str:
    """'₪350' / '350₪' / '350ש"ח' → '350'; a standalone currency word → ''."""
    if token in CURRENCY_WORDS:
        return ""
    token = token.strip("₪")
    match = _CURRENCY_SUFFIX_RE.match(token)
    if match:
        token = match.group(1)
    if _THOUSANDS_RE.match(token):
        token = token.replace(",", "")
    return token


def normalise(text: str) -> str:
    """Trim, collapse whitespace, drop a trailing '.'/'!' and currency marks, '1,200' → '1200'."""
    text = " ".join(str(text or "").split())
    text = text.rstrip(".!").strip()
    tokens = [_strip_currency(t) for t in text.split(" ")]
    return " ".join(t for t in tokens if t)


def _command(text: str) -> str:
    """Lower-cased, without a trailing ':' — how command words are compared."""
    return text.lower().rstrip(":").strip()


# ---------------------------------------------------------------- dates

def _next_weekday(weekday: int, today: date) -> date:
    """The next such day, never today."""
    delta = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=delta)


def _weekday_of(token: str) -> int | None:
    if token in _WEEKDAYS:
        return _WEEKDAYS[token]
    if len(token) == 2 and token[1] in ("'", "׳") and token[0] in _WEEKDAY_LETTERS:
        return _WEEKDAY_LETTERS[token[0]]
    return None


def _parse_when(tokens: list[str], today: date) -> date | None:
    """The date after 'עד': היום / מחר / מחרתיים / (יום) חמישי / ה' / d.m[.yy[yy]]; None otherwise."""
    if not tokens:
        return None
    if len(tokens) == 2:
        if tokens[0] != "יום":
            return None
        weekday = _weekday_of(tokens[1])
        return _next_weekday(weekday, today) if weekday is not None else None
    if len(tokens) != 1:
        return None
    word = tokens[0]
    if word == "היום":
        return today
    if word == "מחר":
        return today + timedelta(days=1)
    if word == "מחרתיים":
        return today + timedelta(days=2)
    weekday = _weekday_of(word)
    if weekday is not None:
        return _next_weekday(weekday, today)
    match = _DOTTED_DATE_RE.match(word)
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
    try:
        if year:
            return date(2000 + int(year) if len(year) == 2 else int(year), month, day)
        when = date(today.year, month, day)
        if when < today:
            when = date(today.year + 1, month, day)
        return when
    except ValueError:
        return None


def _has_until_date(tokens: list[str], today: date) -> bool:
    """True when 'עד' is followed somewhere by a date-ish token (then it is a task, not an expense)."""
    for idx, token in enumerate(tokens):
        if token != UNTIL_WORD:
            continue
        if _parse_when(tokens[idx + 1:idx + 2], today) or _parse_when(tokens[idx + 1:idx + 3], today):
            return True
    return False


def _split_due(tokens: list[str], today: date) -> tuple[list[str], date | None]:
    """Remove the first 'עד <when>' wherever it sits ('עד חמישי להתקשר לצלם' too) and return the date.

    The same scan `_has_until_date` does, so a date that kept a message out of the expense
    path is never left inside a task title.
    """
    for idx, token in enumerate(tokens):
        if token != UNTIL_WORD:
            continue
        for width in (2, 1):
            when = _parse_when(tokens[idx + 1:idx + 1 + width], today)
            if when:
                return tokens[:idx] + tokens[idx + 1 + width:], when
    return tokens, None


# ---------------------------------------------------------------- formatting

def money(amount: float) -> str:
    """'₪1,200' / '₪89.90' — decimals only when non-zero."""
    amount = abs(float(amount))
    if round(amount, 2) == int(round(amount, 2)):
        return f"₪{int(round(amount)):,}"
    return f"₪{amount:,.2f}"


def _countdown_line(conn: sqlite3.Connection, today: date) -> str | None:
    info = wedding_plan.countdown(conn, today)
    days = info.get("days_left")
    if days is None or days <= 0:
        return None
    return f"עוד {info['weeks_label']} לחתונה"


def _lines(*parts: str | None) -> str:
    return "\n".join(p for p in parts if p)


def _owner_label(owner: str | None) -> str:
    return display_name(owner) if owner else ""


# ---------------------------------------------------------------- undo state

def _undo_key(user: Any) -> str:
    return f"{UNDO_KEY_PREFIX}{normalise_username(user)}"


def _remember(conn: sqlite3.Connection, user: Any, kind: str, row_id: int,
              prev_owner: str | None = None, label: str = "") -> None:
    """Overwrite the sender's last action; the caller commits."""
    value = json.dumps(
        {"kind": kind, "id": row_id, "prev_owner": prev_owner, "label": label}, ensure_ascii=False
    )
    conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (_undo_key(user), value),
    )


def _undo_expired(updated_at: Any) -> bool:
    """True when the remembered action is older than UNDO_WINDOW (updated_at is SQLite UTC text)."""
    try:
        written = datetime.fromisoformat(str(updated_at))
    except (TypeError, ValueError):
        return True
    now = datetime.now(UTC).replace(tzinfo=None)
    return now - written > UNDO_WINDOW


def _undo(conn: sqlite3.Connection, user: Any) -> str:
    """Reverse the sender's last action, but only if the row is still as the bot left it."""
    key = _undo_key(user)
    row = conn.execute("SELECT value, updated_at FROM system_settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return NOTHING_TO_UNDO
    conn.execute("DELETE FROM system_settings WHERE key = ?", (key,))
    try:
        state = json.loads(row["value"])
        kind, row_id = state["kind"], int(state["id"])
    except (ValueError, KeyError, TypeError):
        conn.commit()
        return NOTHING_TO_UNDO
    if _undo_expired(row["updated_at"]):
        conn.commit()
        return NOTHING_TO_UNDO

    # Each statement's WHERE restates what the bot left behind, so a row the app has
    # since completed, re-assigned or re-tagged is left alone (rowcount 0 → stale).
    reply = UNDO_STALE
    if kind == "expense":
        cur = conn.execute("DELETE FROM transactions WHERE id = ? AND tags = ?", (row_id, TAG))
        if cur.rowcount:
            _invalidate_stats_cache()
            label = state.get("label")
            reply = f"↩️ ההוצאה {label} בוטלה" if label else "↩️ ההוצאה בוטלה"
    elif kind == "task":
        cur = conn.execute("DELETE FROM wedding_tasks WHERE id = ? AND completed = 0", (row_id,))
        if cur.rowcount:
            reply = f"↩️ המשימה #{row_id} נמחקה"
    elif kind == "done":
        cur = conn.execute("UPDATE wedding_tasks SET completed = 0 WHERE id = ? AND completed = 1", (row_id,))
        if cur.rowcount:
            reply = f"↩️ #{row_id} חזרה לפתוחה"
    elif kind == "take":
        prev = state.get("prev_owner")
        person = find_person(household(conn), user)
        cur = conn.execute(
            "UPDATE wedding_tasks SET owner = ? WHERE id = ? AND owner = ?",
            (prev, row_id, person["name"] if person else ""),
        )
        if cur.rowcount:
            reply = f"↩️ #{row_id} חזרה ל{display_name(prev)}" if prev else f"↩️ #{row_id} חזרה ללא אחראי"
    else:
        reply = NOTHING_TO_UNDO
    conn.commit()
    return reply


# ---------------------------------------------------------------- expense

def _phrase_re(phrase: str, prefixes: str = "") -> re.Pattern[str]:
    prefix = f"[{prefixes}]?" if prefixes else ""
    return re.compile(rf"(?<!\S){prefix}{re.escape(phrase)}(?!\S)")


def _pick_category(conn: sqlite3.Connection, text: str) -> tuple[sqlite3.Row, str]:
    """(category row, notes text) — whole-name match, then keyword, then הוצאות בית."""
    rows = conn.execute("SELECT id, name FROM categories").fetchall()
    eligible = [r for r in rows if r["name"] not in INCOME_CATEGORIES]
    by_name = {r["name"]: r for r in eligible}

    for row in sorted(eligible, key=lambda r: len(r["name"]), reverse=True):
        pattern = _phrase_re(row["name"], _KEYWORD_PREFIXES)
        if pattern.search(text):
            return row, " ".join(pattern.sub(" ", text, count=1).split())

    for keyword, names in EXPENSE_KEYWORDS:
        if _phrase_re(keyword, _KEYWORD_PREFIXES).search(text):
            hit = next((by_name[n] for n in names if n in by_name), None)
            if hit:
                return hit, text

    fallback = by_name.get(FALLBACK_CATEGORY) or (eligible[0] if eligible else None)
    if fallback is None:
        raise RuntimeError("no expense category in the database")
    return fallback, text


def _account_for(conn: sqlite3.Connection, user: Any) -> sqlite3.Row | None:
    account_id = default_account_id(conn, user)
    if account_id is not None:
        row = conn.execute("SELECT id, name FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row:
            return row
    row = conn.execute("SELECT id, name FROM accounts WHERE name = ?", (FALLBACK_ACCOUNT,)).fetchone()
    return row or conn.execute("SELECT id, name FROM accounts ORDER BY id LIMIT 1").fetchone()


def _parse_amount(token: str) -> float | None:
    if not _AMOUNT_RE.match(token):
        return None
    value = float(token.replace(",", "."))
    return value if 0 < value < MAX_AMOUNT else None


def _try_expense(conn: sqlite3.Connection, user: Any, tokens: list[str], today: date) -> str | None:
    """Record an expense when the first or last token is an amount; None when it is not one."""
    if _has_until_date(tokens, today):
        return None
    words = [t for t in tokens if t != YESTERDAY_WORD]
    if not words:
        return None
    amount, index = _parse_amount(words[0]), 0
    if amount is None:
        amount, index = _parse_amount(words[-1]), len(words) - 1
    if amount is None:
        return None

    when = today - timedelta(days=1) if YESTERDAY_WORD in tokens else today
    rest = " ".join(words[:index] + words[index + 1:])
    category, notes = _pick_category(conn, rest)
    notes = notes.strip() or None
    person = find_person(household(conn), user)
    account = _account_for(conn, user)

    cur = conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, account_id, notes, tags, recurrence_id, period_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
        (
            when.isoformat(),
            -abs(round(amount, 2)),
            category["id"],
            person["id"] if person else None,
            account["id"] if account else None,
            notes,
            TAG,
        ),
    )
    _remember(conn, user, "expense", cur.lastrowid, label=f"{money(amount)} ({notes or category['name']})")
    conn.commit()
    _invalidate_stats_cache()

    # The row is saved; nothing after this point may turn the reply into "try again"
    # (a retry would record the expense twice), so the total is best-effort.
    spent_line = None
    try:
        spent_line = f"הוצאות החודש: {money(month_totals(conn, when.strftime('%Y-%m'))['expenses'])}"
    except Exception:
        logger.exception("WhatsApp: month total unavailable after recording an expense")
    head = " · ".join(p for p in (money(amount), notes, category["name"], account["name"] if account else None) if p)
    return _lines(f"✅ נרשם: {head}", spent_line, UNDO_HINT)


# ---------------------------------------------------------------- tasks

def _owner_from_prefix(conn: sqlite3.Connection, user: Any, token: str) -> tuple[bool, str | None]:
    """(matched, users.name) for a leading 'אני:' / 'יוסף:' / 'קארינה:'."""
    if not token.endswith(":") or len(token) < 2:
        return False, None
    word = token[:-1].strip()
    if word == SELF_OWNER:
        person = find_person(household(conn), user)
        return (True, person["name"]) if person else (False, None)
    by_display = {shown: key for key, shown in USER_DISPLAY_NAMES.items()}
    try:
        owner = valid_owner(conn, by_display.get(word, word))
    except ValueError:
        return False, None
    return (owner is not None), owner


def _add_task(conn: sqlite3.Connection, user: Any, tokens: list[str], today: date) -> str | None:
    """Add a wedding task; None when nothing is left for a title."""
    owner = None
    if tokens:
        matched, found = _owner_from_prefix(conn, user, tokens[0])
        if matched:
            owner, tokens = found, tokens[1:]
    tokens, due = _split_due(tokens, today)
    priority = "high" if URGENT_WORD in tokens else "medium"
    title = " ".join(t for t in tokens if t != URGENT_WORD).strip()
    if not title:
        return None

    cur = conn.execute(
        "INSERT INTO wedding_tasks (title, category, due_date, completed, priority, owner) "
        "VALUES (?, 'general', ?, 0, ?, ?)",
        (title, due.isoformat() if due else None, priority, owner),
    )
    task_id = cur.lastrowid
    _remember(conn, user, "task", task_id, label=title)
    conn.commit()

    due_text = ""
    if due:
        due_text = hd.due_label(due, today)
        if not due_text.startswith(UNTIL_WORD + " "):
            due_text = f"{UNTIL_WORD} {due_text}"
    head = " · ".join(p for p in (f"#{task_id}: {title}", due_text, _owner_label(owner)) if p)
    return _lines(f"📝 נוספה משימה {head}", _countdown_line(conn, today), UNDO_HINT)


def _open_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM wedding_tasks WHERE completed = 0").fetchone()[0])


_GROUP_ORDER = {"overdue": 0, "week": 1, "later": 2, "nodate": 3}


def _list_tasks(conn: sqlite3.Connection, user: Any, mine: bool, today: date) -> str:
    query = "SELECT id, title, due_date, completed, owner FROM wedding_tasks WHERE completed = 0"
    params: tuple = ()
    if mine:
        person = find_person(household(conn), user)
        query += " AND owner = ?"
        params = (person["name"] if person else "",)
    tasks = [dict(r) for r in conn.execute(query, params).fetchall()]
    countdown = _countdown_line(conn, today)
    if not tasks:
        return _lines(NO_TASKS_MINE if mine else NO_OPEN_TASKS, countdown)

    for t in tasks:
        t["group"] = task_group(t, today)
    tasks.sort(key=lambda t: (_GROUP_ORDER.get(t["group"], 9), t["due_date"] or "9999-12-31", t["id"]))

    header = f"📋 המשימות שלך ({len(tasks)})" if mine else f"📋 משימות פתוחות ({len(tasks)})"
    lines = [header]
    for t in tasks[:LIST_LIMIT]:
        due = hd.parse_iso(t["due_date"])
        parts = [f"#{t['id']} {t['title']}", hd.due_label(due, today) if due else "", _owner_label(t["owner"])]
        line = " · ".join(p for p in parts if p)
        lines.append(f"⚠️ {line}" if t["group"] == "overdue" else line)
    if len(tasks) > LIST_LIMIT:
        lines.append(f"…ועוד {len(tasks) - LIST_LIMIT}")
    return _lines(*lines, countdown)


def _resolve_task(conn: sqlite3.Connection, ref: str) -> tuple[dict | None, str | None]:
    """(task, None) for exactly one match, else (None, the reply to send)."""
    ref = ref.strip()
    bare = ref.lstrip("#").strip()
    if bare.isdigit():
        row = conn.execute(
            "SELECT id, title, completed, owner FROM wedding_tasks WHERE id = ?", (int(bare),)
        ).fetchone()
        return (dict(row), None) if row else (None, NO_SUCH_TASK)
    needle = ref.lower()
    matches = [
        dict(r) for r in conn.execute(
            "SELECT id, title, completed, owner FROM wedding_tasks WHERE completed = 0 ORDER BY id"
        ).fetchall()
        if needle in (r["title"] or "").lower()
    ]
    if not matches:
        return None, NO_SUCH_TASK
    if len(matches) > 1:
        return None, _lines(WHICH_ONE, *(f"#{m['id']} {m['title']}" for m in matches[:AMBIGUOUS_LIMIT]))
    return matches[0], None


def _remaining_text(count: int) -> str:
    if count == 0:
        return "לא נשארו משימות פתוחות 🎉"
    if count == 1:
        return "נשארה משימה פתוחה אחת."
    return f"נשארו {count} משימות פתוחות."


def _done(conn: sqlite3.Connection, user: Any, ref: str) -> str:
    task, reply = _resolve_task(conn, ref)
    if task is None:
        return reply or NO_SUCH_TASK
    if task["completed"]:
        return f"#{task['id']} כבר בוצעה"
    conn.execute("UPDATE wedding_tasks SET completed = 1 WHERE id = ?", (task["id"],))
    _remember(conn, user, "done", task["id"], label=task["title"])
    conn.commit()
    head = f"✔️ #{task['id']} {task['title']} — בוצע. {_remaining_text(_open_count(conn))}"
    return _lines(head, UNDO_HINT)


def _take(conn: sqlite3.Connection, user: Any, ref: str) -> str:
    task, reply = _resolve_task(conn, ref)
    if task is None:
        return reply or NO_SUCH_TASK
    if task["completed"]:
        return f"#{task['id']} כבר בוצעה"
    person = find_person(household(conn), user)
    if person is None:
        return UNKNOWN_SENDER
    if task["owner"] and normalise_username(task["owner"]) == normalise_username(person["name"]):
        return f"#{task['id']} כבר שלך"
    conn.execute("UPDATE wedding_tasks SET owner = ? WHERE id = ?", (person["name"], task["id"]))
    _remember(conn, user, "take", task["id"], prev_owner=task["owner"] or None, label=task["title"])
    conn.commit()
    return _lines(f"🙋 #{task['id']} {task['title']} — על {person['display']}.", UNDO_HINT)


# ---------------------------------------------------------------- the grammar

def _strip_prefix(text: str, prefix: str) -> str | None:
    """The rest after a leading command phrase (case-insensitive, optional ':'), or None."""
    lowered = text.lower()
    if lowered == prefix or lowered == prefix + ":":
        return ""
    for sep in (" ", ": "):
        if lowered.startswith(prefix + sep):
            return text[len(prefix) + len(sep):].strip()
    return None


def handle_message(conn: sqlite3.Connection, user: Any, text: str, today: date | None = None) -> str:
    """Run one chat message from `user` (a household username) and return the reply."""
    today = today or hd.today_local()
    text = normalise(text)
    command = _command(text)
    if not text:
        return _lines(NOT_UNDERSTOOD, HELP_TEXT)

    if command in UNDO_WORDS:
        return _undo(conn, user)
    if command in HELP_WORDS:
        return HELP_TEXT
    if command in LIST_ALL_WORDS:
        return _list_tasks(conn, user, mine=False, today=today)
    if command in LIST_MINE_WORDS:
        return _list_tasks(conn, user, mine=True, today=today)

    tokens = text.split(" ")
    if _command(tokens[0]) in DONE_WORDS and len(tokens) > 1:
        return _done(conn, user, " ".join(tokens[1:]))
    for prefix in TAKE_PREFIXES:
        rest = _strip_prefix(text, prefix)
        if rest:
            return _take(conn, user, rest)

    reply = _try_expense(conn, user, tokens, today)
    if reply:
        return reply

    if len(tokens) >= 2:
        reply = _add_task(conn, user, tokens, today)
        if reply:
            return reply
    return _lines(NOT_UNDERSTOOD, HELP_TEXT)
