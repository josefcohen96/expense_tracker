"""תרשום — the WhatsApp bot: webhook security, the chat grammar, undo and dedup.

Grammar cases call `handle_message` directly with a fixed `today` (2032-03-10, a
Wednesday) so the dates are deterministic; the webhook cases go through HTTP with a
Meta-shaped, correctly signed body and a fake `send_text`.
"""
import hashlib
import hmac
import importlib
import json
import os
import sqlite3
import sys
from datetime import date

import pytest

SECRET = "pytest-wa-app-secret"
VERIFY = "pytest-wa-verify-token"
PHONE_YOSEF = "972500000001"
PHONE_KARINA = "972500000002"
TODAY = date(2032, 3, 10)  # a Wednesday
WEDDING = "2032-06-02"     # 84 days after TODAY → "12 שבועות"


@pytest.fixture()
def wa(app_client):
    """The services.whatsapp module the running app actually uses."""
    for route in app_client.app.routes:
        if getattr(route, "path", "") == "/api/whatsapp/webhook":
            return route.endpoint.__globals__["whatsapp"]
    raise AssertionError("whatsapp webhook route is not registered")


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", VERIFY)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "pytest-wa-access")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456789")
    monkeypatch.setenv("WHATSAPP_PHONE_YOSEF", PHONE_YOSEF)
    monkeypatch.setenv("WHATSAPP_PHONE_KARINA", "+972-50-000-0002")  # formatting is ignored


@pytest.fixture()
def sent(wa, monkeypatch):
    calls = []

    def fake_send(to, text, reply_to=None):
        calls.append((to, text, reply_to))
        return True

    monkeypatch.setattr(wa, "send_text", fake_send)
    return calls


@pytest.fixture()
def clean(db_conn):
    """Start with no wedding tasks and a known wedding date; put everything back after."""
    tasks = [dict(r) for r in db_conn.execute("SELECT * FROM wedding_tasks").fetchall()]
    old_date = db_conn.execute("SELECT value FROM wedding_settings WHERE key='wedding_date'").fetchone()

    def wipe():
        db_conn.execute("DELETE FROM wedding_tasks")
        db_conn.execute("DELETE FROM transactions WHERE tags = 'whatsapp'")
        db_conn.execute("DELETE FROM system_settings WHERE key LIKE 'whatsapp_undo:%'")
        db_conn.commit()

    wipe()
    db_conn.execute("INSERT OR REPLACE INTO wedding_settings (key, value) VALUES ('wedding_date', ?)", (WEDDING,))
    db_conn.commit()
    yield
    wipe()
    for t in tasks:
        cols = ",".join(t.keys())
        marks = ",".join("?" * len(t))
        db_conn.execute(f"INSERT INTO wedding_tasks ({cols}) VALUES ({marks})", tuple(t.values()))
    if old_date:
        db_conn.execute("UPDATE wedding_settings SET value=? WHERE key='wedding_date'", (old_date[0],))
    else:
        db_conn.execute("DELETE FROM wedding_settings WHERE key='wedding_date'")
    db_conn.commit()


def _meta(wa_id, wamid, text=None, kind="text"):
    message = {"from": wa_id, "id": wamid, "timestamp": "1700000000", "type": kind}
    if kind == "text":
        message["text"] = {"body": text}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "contacts": [{"wa_id": wa_id, "profile": {"name": "x"}}],
            "messages": [message],
        }}]}],
    }


def _signed(client, payload, secret=SECRET, signature=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json"}
    if signature:
        headers["X-Hub-Signature-256"] = signature
    return client.post("/api/whatsapp/webhook", content=body, headers=headers)


def _last_tx(db_conn):
    return db_conn.execute(
        "SELECT t.*, c.name AS category, a.name AS account, u.name AS user FROM transactions t "
        "LEFT JOIN categories c ON c.id = t.category_id LEFT JOIN accounts a ON a.id = t.account_id "
        "LEFT JOIN users u ON u.id = t.user_id WHERE t.tags = 'whatsapp' ORDER BY t.id DESC LIMIT 1"
    ).fetchone()


def _wa_count(db_conn):
    return db_conn.execute("SELECT COUNT(*) FROM transactions WHERE tags = 'whatsapp'").fetchone()[0]


def _task(db_conn, task_id):
    return db_conn.execute("SELECT * FROM wedding_tasks WHERE id = ?", (task_id,)).fetchone()


def _add_task(db_conn, title, due=None, owner=None, completed=0):
    cur = db_conn.execute(
        "INSERT INTO wedding_tasks (title, category, due_date, completed, priority, owner) "
        "VALUES (?, 'general', ?, ?, 'medium', ?)",
        (title, due, completed, owner),
    )
    db_conn.commit()
    return cur.lastrowid


# ─── Webhook security ───────────────────────────────────────────────────────

def test_webhook_verify_handshake(app_client, env, monkeypatch):
    ok = app_client.get("/api/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "abc",
    })
    assert ok.status_code == 200
    assert ok.text == "abc"

    wrong = app_client.get("/api/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "abc",
    })
    assert wrong.status_code == 403
    assert wrong.json() == {"detail": "אסימון לא תקין"}

    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN")
    off = app_client.get("/api/whatsapp/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "abc",
    })
    assert off.status_code == 403
    assert off.json() == {"detail": "וואטסאפ כבוי"}


def test_webhook_rejects_bad_signature_and_when_off(app_client, db_conn, env, sent, clean, monkeypatch):
    payload = _meta(PHONE_KARINA, "wamid.pytest-badsig", "350 פרחים")
    for signature in ("sha256=" + "0" * 64, "", "md5=abc"):
        r = _signed(app_client, payload, signature=signature)
        assert r.status_code == 401
        assert r.json() == {"detail": "חתימה לא תקינה"}
    wrong_secret = _signed(app_client, payload, secret="another-secret")
    assert wrong_secret.status_code == 401
    assert _wa_count(db_conn) == 0
    assert sent == []

    monkeypatch.delenv("WHATSAPP_APP_SECRET")
    off = _signed(app_client, payload)
    assert off.status_code == 403
    assert off.json() == {"detail": "וואטסאפ כבוי"}
    assert _wa_count(db_conn) == 0


def test_unknown_sender_is_ignored(app_client, db_conn, env, sent, clean):
    r = _signed(app_client, _meta("972599999999", "wamid.pytest-stranger", "350 פרחים"))
    assert r.status_code == 200
    assert r.json() == {"handled": 0}
    assert _wa_count(db_conn) == 0
    assert db_conn.execute("SELECT COUNT(*) FROM wedding_tasks").fetchone()[0] == 0
    assert sent == []

    # A status/receipt payload carries no messages at all.
    status = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.x", "status": "read"}]}}]}]}
    r = _signed(app_client, status)
    assert r.json() == {"handled": 0}
    assert sent == []


# ─── Expenses ───────────────────────────────────────────────────────────────

def test_expense_from_each_phone_uses_their_account(app_client, db_conn, wa, env, sent, clean):
    r = _signed(app_client, _meta(PHONE_KARINA, "wamid.pytest-karina-1", "350 פרחים"))
    assert r.status_code == 200
    assert r.json() == {"handled": 1}
    row = _last_tx(db_conn)
    assert row["amount"] == -350
    assert row["user"] == "Karina"
    assert row["account"] == "כרטיס אשראי"
    assert row["category"] == "הוצאות בית"
    assert row["notes"] == "פרחים"
    assert row["tags"] == "whatsapp"
    assert row["date"] == wa.hd.today_local().isoformat()

    assert len(sent) == 1
    to, text, reply_to = sent[0]
    assert to == PHONE_KARINA
    assert reply_to == "wamid.pytest-karina-1"
    assert text.startswith("✅ נרשם: ₪350 · פרחים · הוצאות בית · כרטיס אשראי")
    assert "הוצאות החודש: ₪" in text
    assert text.endswith("בטל — לביטול")

    r = _signed(app_client, _meta(PHONE_YOSEF, "wamid.pytest-yosef-1", "₪1,200 פרחים"))
    assert r.json() == {"handled": 1}
    row = _last_tx(db_conn)
    assert row["amount"] == -1200
    assert row["user"] == "Yosef"
    assert row["account"] == "מזומן"
    assert sent[1][1].startswith("✅ נרשם: ₪1,200 · פרחים · הוצאות בית · מזומן")

    # A non-text message from a known phone gets the text-only line.
    r = _signed(app_client, _meta(PHONE_YOSEF, "wamid.pytest-sticker", kind="sticker"))
    assert r.json() == {"handled": 1}
    assert sent[2] == (PHONE_YOSEF, wa.TEXT_ONLY, "wamid.pytest-sticker")


def test_expense_category_and_yesterday(db_conn, wa, clean):
    reply = wa.handle_message(db_conn, "KARINA", "פיצה 89.90 אתמול", today=TODAY)
    row = _last_tx(db_conn)
    assert row["category"] == "אוכל בחוץ"
    assert row["date"] == "2032-03-09"
    assert row["notes"] == "פיצה"
    assert row["amount"] == pytest.approx(-89.9)
    assert reply.startswith("✅ נרשם: ₪89.90 · פיצה · אוכל בחוץ · כרטיס אשראי")

    wa.handle_message(db_conn, "KARINA", "120 רכב", today=TODAY)
    row = _last_tx(db_conn)
    assert row["category"] == "רכב"
    assert row["notes"] is None
    assert row["amount"] == -120

    # A d.m-looking amount with no 'עד' before it is still money.
    wa.handle_message(db_conn, "KARINA", "3.11 קפה", today=TODAY)
    row = _last_tx(db_conn)
    assert row["amount"] == pytest.approx(-3.11)
    assert row["category"] == "אוכל בחוץ"


# ─── Tasks ──────────────────────────────────────────────────────────────────

def test_task_with_weekday_owner_priority_and_date(db_conn, wa, clean):
    reply = wa.handle_message(db_conn, "KARINA", "להתקשר לצלם עד חמישי", today=TODAY)
    task = db_conn.execute("SELECT * FROM wedding_tasks ORDER BY id DESC LIMIT 1").fetchone()
    assert task["title"] == "להתקשר לצלם"
    assert task["owner"] is None
    assert task["priority"] == "medium"
    assert task["completed"] == 0
    assert task["category"] == "general"
    assert task["due_date"] == "2032-03-11"
    assert f"📝 נוספה משימה #{task['id']}: להתקשר לצלם · עד מחר" in reply
    assert "עוד 12 שבועות לחתונה" in reply
    assert _wa_count(db_conn) == 0

    reply = wa.handle_message(db_conn, "YOSEF", "קארינה: דחוף לאשר תפריט עד 3.11", today=TODAY)
    task = db_conn.execute("SELECT * FROM wedding_tasks ORDER BY id DESC LIMIT 1").fetchone()
    assert task["owner"] == "Karina"
    assert task["priority"] == "high"
    assert task["title"] == "לאשר תפריט"
    assert task["due_date"] == "2032-11-03"
    assert "עד 3 בנובמבר · קארינה" in reply
    assert _wa_count(db_conn) == 0  # 'עד 3.11' is a date, never ₪3.11

    # A weekday is the next such day, never today; a past d.m rolls to next year.
    wa.handle_message(db_conn, "YOSEF", "אני: לקנות פרחים עד יום רביעי", today=TODAY)
    task = db_conn.execute("SELECT * FROM wedding_tasks ORDER BY id DESC LIMIT 1").fetchone()
    assert (task["title"], task["due_date"], task["owner"]) == ("לקנות פרחים", "2032-03-17", "Yosef")
    wa.handle_message(db_conn, "YOSEF", "לסגור די ג'יי עד 2.3", today=TODAY)
    task = db_conn.execute("SELECT * FROM wedding_tasks ORDER BY id DESC LIMIT 1").fetchone()
    assert task["due_date"] == "2033-03-02"
    # 'עד' with no date stays in the title.
    wa.handle_message(db_conn, "YOSEF", "לבדוק עד כמה זה עולה", today=TODAY)
    task = db_conn.execute("SELECT * FROM wedding_tasks ORDER BY id DESC LIMIT 1").fetchone()
    assert (task["title"], task["due_date"]) == ("לבדוק עד כמה זה עולה", None)

    # Without a wedding date the countdown line is omitted.
    db_conn.execute("DELETE FROM wedding_settings WHERE key='wedding_date'")
    db_conn.commit()
    reply = wa.handle_message(db_conn, "YOSEF", "לבחור שמלה", today=TODAY)
    assert "לחתונה" not in reply


def test_list_groups_caps_and_mine(db_conn, wa, clean):
    assert wa.handle_message(db_conn, "KARINA", "משימות", today=TODAY).startswith("אין משימות פתוחות 🎉")
    assert wa.handle_message(db_conn, "KARINA", "שלי", today=TODAY).startswith("אין משימות על שמך")

    later = _add_task(db_conn, "לבחור מגנטים", due="2032-05-01")
    nodate = _add_task(db_conn, "רעיון לשיר")
    week = _add_task(db_conn, "לשלם מקדמה", due="2032-03-12", owner="Karina")
    overdue = _add_task(db_conn, "לסגור צלם", due="2032-03-08", owner="Yosef")
    _add_task(db_conn, "משימה שנסגרה", completed=1)

    reply = wa.handle_message(db_conn, "KARINA", "משימות", today=TODAY)
    lines = reply.split("\n")
    assert lines[0] == "📋 משימות פתוחות (4)"
    assert lines[1] == f"⚠️ #{overdue} לסגור צלם · באיחור ביומיים · יוסף"
    assert lines[2].startswith(f"#{week} לשלם מקדמה")
    assert lines[3].startswith(f"#{later} לבחור מגנטים")
    assert lines[4] == f"#{nodate} רעיון לשיר"
    assert lines[5] == "עוד 12 שבועות לחתונה"
    assert "שנסגרה" not in reply

    mine = wa.handle_message(db_conn, "KARINA", "המשימות שלי", today=TODAY)
    assert mine.split("\n")[0] == "📋 המשימות שלך (1)"
    assert f"#{week} לשלם מקדמה" in mine
    assert "לסגור צלם" not in mine

    for i in range(22):
        _add_task(db_conn, f"משימה נוספת {i}")
    lines = wa.handle_message(db_conn, "KARINA", "מה נשאר", today=TODAY).split("\n")
    assert lines[0] == "📋 משימות פתוחות (26)"
    assert len([line for line in lines if "#" in line]) == 20
    assert "…ועוד 6" in lines


def test_done_by_id_fragment_ambiguous_missing_and_already_done(db_conn, wa, clean):
    first = _add_task(db_conn, "לסגור צלם")
    second = _add_task(db_conn, "לשלם לצלם")
    third = _add_task(db_conn, "להזמין פרחים")

    reply = wa.handle_message(db_conn, "KARINA", f"סיימתי {third}", today=TODAY)
    assert reply == f"✔️ #{third} להזמין פרחים — בוצע. נשארו 2 משימות פתוחות.\nבטל — לביטול"
    assert _task(db_conn, third)["completed"] == 1

    reply = wa.handle_message(db_conn, "KARINA", "סיימתי צלם", today=TODAY)
    assert reply.split("\n") == ["איזו מהן?", f"#{first} לסגור צלם", f"#{second} לשלם לצלם"]
    assert _task(db_conn, first)["completed"] == 0
    assert _task(db_conn, second)["completed"] == 0

    assert wa.handle_message(db_conn, "KARINA", "סיימתי דינוזאור", today=TODAY) == "לא מצאתי משימה כזו"
    assert wa.handle_message(db_conn, "KARINA", f"בוצע #{third}", today=TODAY) == f"#{third} כבר בוצעה"

    reply = wa.handle_message(db_conn, "KARINA", "✅ לשלם", today=TODAY)
    assert reply.startswith(f"✔️ #{second} לשלם לצלם — בוצע.")


def test_take_sets_owner(db_conn, wa, clean):
    task_id = _add_task(db_conn, "לאשר תפריט")
    reply = wa.handle_message(db_conn, "KARINA", f"לקחתי {task_id}", today=TODAY)
    assert reply == f"🙋 #{task_id} לאשר תפריט — על קארינה.\nבטל — לביטול"
    assert _task(db_conn, task_id)["owner"] == "Karina"
    assert wa.handle_message(db_conn, "KARINA", "אני על זה תפריט", today=TODAY) == f"#{task_id} כבר שלך"

    reply = wa.handle_message(db_conn, "YOSEF", "אני אעשה תפריט", today=TODAY)
    assert reply.startswith(f"🙋 #{task_id} לאשר תפריט — על יוסף.")
    assert _task(db_conn, task_id)["owner"] == "Yosef"


# ─── Undo ───────────────────────────────────────────────────────────────────

def test_undo_each_kind_and_nothing_to_undo(db_conn, wa, clean):
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == "אין מה לבטל"

    # expense
    wa.handle_message(db_conn, "KARINA", "350 פרחים", today=TODAY)
    tx_id = _last_tx(db_conn)["id"]
    assert wa.handle_message(db_conn, "KARINA", "בטל!", today=TODAY) == "↩️ ההוצאה ₪350 (פרחים) בוטלה"
    assert db_conn.execute("SELECT 1 FROM transactions WHERE id=?", (tx_id,)).fetchone() is None
    assert wa.handle_message(db_conn, "KARINA", "ביטול", today=TODAY) == "אין מה לבטל"

    # task added
    wa.handle_message(db_conn, "KARINA", "להזמין רב", today=TODAY)
    task_id = db_conn.execute("SELECT MAX(id) FROM wedding_tasks").fetchone()[0]
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == f"↩️ המשימה #{task_id} נמחקה"
    assert _task(db_conn, task_id) is None

    # done
    task_id = _add_task(db_conn, "לסגור אולם")
    wa.handle_message(db_conn, "KARINA", f"סיימתי {task_id}", today=TODAY)
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == f"↩️ #{task_id} חזרה לפתוחה"
    assert _task(db_conn, task_id)["completed"] == 0

    # take, from Yosef and from nobody
    owned = _add_task(db_conn, "לבחור טבעות", owner="Yosef")
    wa.handle_message(db_conn, "KARINA", f"לקחתי {owned}", today=TODAY)
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == f"↩️ #{owned} חזרה ליוסף"
    assert _task(db_conn, owned)["owner"] == "Yosef"
    free = _add_task(db_conn, "לבחור הזמנות")
    wa.handle_message(db_conn, "KARINA", f"לקחתי {free}", today=TODAY)
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == f"↩️ #{free} חזרה ללא אחראי"
    assert _task(db_conn, free)["owner"] is None
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == "אין מה לבטל"

    # Each phone undoes only its own last action.
    wa.handle_message(db_conn, "KARINA", "45 מכולת", today=TODAY)
    assert wa.handle_message(db_conn, "YOSEF", "בטל", today=TODAY) == "אין מה לבטל"

    # Undo never deletes a transaction that is not the bot's.
    tx_id = _last_tx(db_conn)["id"]
    db_conn.execute("UPDATE transactions SET tags = NULL WHERE id = ?", (tx_id,))
    db_conn.commit()
    try:
        assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == wa.UNDO_STALE
        assert db_conn.execute("SELECT 1 FROM transactions WHERE id=?", (tx_id,)).fetchone() is not None
    finally:
        db_conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        db_conn.commit()


# ─── Reliability and fallbacks ──────────────────────────────────────────────

def test_duplicate_wamid_handled_once(app_client, db_conn, env, sent, clean):
    payload = _meta(PHONE_KARINA, "wamid.pytest-duplicate", "41 פרחים")
    first = _signed(app_client, payload)
    again = _signed(app_client, payload)
    assert first.status_code == 200 and again.status_code == 200
    assert first.json() == {"handled": 1}
    assert again.json() == {"handled": 0}
    assert _wa_count(db_conn) == 1
    assert len(sent) == 1


def test_unknown_single_word_gets_help(db_conn, wa, clean):
    reply = wa.handle_message(db_conn, "KARINA", "בוקר", today=TODAY)
    assert reply == "לא הבנתי.\n" + wa.HELP_TEXT
    assert db_conn.execute("SELECT COUNT(*) FROM wedding_tasks").fetchone()[0] == 0
    assert _wa_count(db_conn) == 0
    assert wa.handle_message(db_conn, "KARINA", "עזרה", today=TODAY) == wa.HELP_TEXT

    reply = wa.handle_message(db_conn, "KARINA", "בוקר טוב", today=TODAY)
    assert reply.startswith("📝 נוספה משימה #")
    assert db_conn.execute("SELECT title FROM wedding_tasks").fetchone()["title"] == "בוקר טוב"


def test_test_endpoint_returns_reply_without_sending(app_client, db_conn, wa, env, sent, clean):
    r = app_client.post("/api/whatsapp/test", json={"text": "עזרה"})
    assert r.status_code == 200
    assert r.json() == {"reply": wa.HELP_TEXT}

    # auth is off in the shared client, so the session user is Yosef
    r = app_client.post("/api/whatsapp/test", json={"text": "77 פרחים"})
    assert r.status_code == 200
    assert r.json()["reply"].startswith("✅ נרשם: ₪77 · פרחים · הוצאות בית · מזומן")
    assert _last_tx(db_conn)["user"] == "Yosef"
    assert sent == []


def test_whatsapp_webhook_is_public_but_test_is_not():
    from app.backend.app.auth import build_public_route_matchers
    from app.backend.app.main import app

    matchers = build_public_route_matchers(app)
    webhook_methods = set()
    for regex, methods in matchers:
        if regex.match("/api/whatsapp/webhook"):
            webhook_methods |= methods
    assert {"GET", "POST"} <= webhook_methods
    assert not any(regex.match("/api/whatsapp/test") for regex, _methods in matchers)


# ─── Yonatan over HTTP (auth genuinely enabled) — keep last: it re-imports the app ──

@pytest.fixture(scope="module")
def authed(tmp_path_factory):
    keys = (
        "BUDGET_DB_PATH", "AUTH_ENABLED", "USER_PASSWORD_YOSEF", "USER_PASSWORD_KARINA",
        "USER_PASSWORD_YONATAN", "SESSION_SECRET_KEY", "ALLOWED_HOSTS",
    )
    saved_env = {k: os.environ.get(k) for k in keys}

    tmp_db = tmp_path_factory.mktemp("whatsapp_db") / "budget_whatsapp_test.sqlite3"
    os.environ["BUDGET_DB_PATH"] = str(tmp_db)
    os.environ["AUTH_ENABLED"] = "1"
    os.environ["USER_PASSWORD_YOSEF"] = "test-password-yosef"
    os.environ["USER_PASSWORD_KARINA"] = "test-password-karina"
    os.environ["USER_PASSWORD_YONATAN"] = "pytest-yonatan"
    os.environ.setdefault("SESSION_SECRET_KEY", "pytest-only-not-for-production")
    os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

    def forget_app_modules():
        for mod_name in list(sys.modules):
            if mod_name.startswith("app.backend.app"):
                del sys.modules[mod_name]

    forget_app_modules()
    import app.backend.app.db as db_module
    importlib.reload(db_module)
    db_module.initialise_database()
    from fastapi.testclient import TestClient

    import app.backend.app.main as main_module
    client = TestClient(main_module.app)
    try:
        yield client, tmp_db
    finally:
        client.close()
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        forget_app_modules()


def _login(client, username, password):
    import app.backend.app.routes.auth as auth_routes
    auth_routes._login_attempts.clear()
    r = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text


def test_whatsapp_api_blocked_for_workouts_only_user(authed):
    client, tmp_db = authed
    _login(client, "yonatan", "pytest-yonatan")
    try:
        r = client.post("/api/whatsapp/test", json={"text": "350 פרחים"}, follow_redirects=False)
        assert r.status_code == 403
    finally:
        client.get("/logout", follow_redirects=False)
    conn = sqlite3.connect(str(tmp_db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM transactions WHERE tags = 'whatsapp'").fetchone()[0] == 0
    finally:
        conn.close()

    # The household can use it with a real session.
    _login(client, "karina", "test-password-karina")
    try:
        r = client.post("/api/whatsapp/test", json={"text": "עזרה"})
        assert r.status_code == 200
        assert r.json()["reply"].startswith("תרשום")
    finally:
        client.get("/logout", follow_redirects=False)


# ─── Review follow-ups: a date anywhere, typed category names, undo safety, odd payloads ──

def _last_task(db_conn):
    return db_conn.execute("SELECT * FROM wedding_tasks ORDER BY id DESC LIMIT 1").fetchone()


def test_task_date_is_found_anywhere_in_the_sentence(db_conn, wa, clean):
    reply = wa.handle_message(db_conn, "KARINA", "להתקשר לצלם עד חמישי דחוף", today=TODAY)
    row = _last_task(db_conn)
    assert row["title"] == "להתקשר לצלם"
    assert row["priority"] == "high"
    assert row["due_date"] == "2032-03-11"
    assert "עד מחר" in reply

    wa.handle_message(db_conn, "KARINA", "עד 3.11 לאשר תפריט", today=TODAY)
    row = _last_task(db_conn)
    assert row["title"] == "לאשר תפריט"
    assert row["due_date"] == "2032-11-03"


def test_typed_category_name_with_a_prefix_letter(db_conn, wa, clean):
    reply = wa.handle_message(db_conn, "YOSEF", "60 בתחבורה", today=TODAY)
    row = _last_tx(db_conn)
    assert row["category"] == "תחבורה"
    assert row["notes"] is None
    assert reply.startswith("✅ נרשם: ₪60 · תחבורה · מזומן")


def test_undo_leaves_a_row_the_app_changed_meanwhile(db_conn, wa, clean):
    wa.handle_message(db_conn, "KARINA", "להזמין מגנטים", today=TODAY)
    task_id = _last_task(db_conn)["id"]
    # Yosef finishes it in the app before Karina's stray בטל.
    db_conn.execute("UPDATE wedding_tasks SET completed = 1 WHERE id = ?", (task_id,))
    db_conn.commit()
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == wa.UNDO_STALE
    assert _task(db_conn, task_id) is not None
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == wa.NOTHING_TO_UNDO

    # A take undone after the app re-assigned the task.
    other = _add_task(db_conn, "pytest-wa-stale-take")
    wa.handle_message(db_conn, "YOSEF", f"לקחתי {other}", today=TODAY)
    db_conn.execute("UPDATE wedding_tasks SET owner = 'Karina' WHERE id = ?", (other,))
    db_conn.commit()
    assert wa.handle_message(db_conn, "YOSEF", "בטל", today=TODAY) == wa.UNDO_STALE
    assert _task(db_conn, other)["owner"] == "Karina"


def test_undo_expires_after_the_window(db_conn, wa, clean):
    wa.handle_message(db_conn, "KARINA", "350 פרחים", today=TODAY)
    assert _wa_count(db_conn) == 1
    db_conn.execute(
        "UPDATE system_settings SET updated_at = datetime('now', '-2 days') WHERE key = 'whatsapp_undo:KARINA'"
    )
    db_conn.commit()
    assert wa.handle_message(db_conn, "KARINA", "בטל", today=TODAY) == wa.NOTHING_TO_UNDO
    assert _wa_count(db_conn) == 1


def test_webhook_survives_odd_payload_shapes(app_client, db_conn, env, sent, clean):
    for payload in (
        {"entry": {"changes": "abc"}},
        {"entry": ["x", None, {"changes": "nope"}]},
        {"entry": [{"changes": [{"value": {"messages": {}}}, {"value": "str"}, None]}]},
        {"entry": [{"changes": [{"value": {"messages": ["str", 5]}}]}]},
        [],
    ):
        r = _signed(app_client, payload)
        assert r.status_code == 200, payload
        assert r.json() == {"handled": 0}
    assert sent == []
    assert _wa_count(db_conn) == 0
