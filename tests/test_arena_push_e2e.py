"""קריאה לזירה: Web Push from the workouts arena (services/push_service.py, api/push.py).

The shared `app_client` runs with AUTH_ENABLED=0, so every API call is Yosef's. The message
tests use a dedicated users row with its own workout rows, removed again after each test.
The network send is always mocked.
"""
import base64
import json
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.backend.app.services import push_service
from app.backend.app.services.cron_service import CronService

TODAY = date(2026, 6, 15)
TEST_USER = "PushTester"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@pytest.fixture()
def vapid(monkeypatch):
    """A real P-256 key pair in the env, in the formats Railway will hold."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = _b64url(key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    private = _b64url(key.private_numbers().private_value.to_bytes(32, "big"))
    monkeypatch.setenv("VAPID_PUBLIC_KEY", public)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    return public


@pytest.fixture()
def no_vapid(monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)


@pytest.fixture()
def clean_subscriptions(app_client, db_conn):
    def wipe():
        db_conn.execute("DELETE FROM push_subscriptions")
        db_conn.execute("DELETE FROM system_settings WHERE key LIKE 'push_sent:%'")
        db_conn.commit()
    wipe()
    yield
    wipe()


@pytest.fixture()
def trainee(app_client, db_conn, clean_subscriptions):
    """A users row of its own, so other tests' workout history is untouched."""
    cur = db_conn.execute("INSERT INTO users (name) VALUES (?)", (TEST_USER,))
    db_conn.commit()
    user_id = cur.lastrowid
    yield user_id
    db_conn.execute("DELETE FROM workouts WHERE user_id = ?", (user_id,))
    db_conn.execute("DELETE FROM push_subscriptions WHERE user_id = ?", (user_id,))
    db_conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db_conn.commit()


def _trained(db_conn, user_id, *days_ago, workout_type="Pull"):
    for n in days_ago:
        db_conn.execute(
            "INSERT INTO workouts (user_id, date, workout_type, total_duration, exercise_name, total_sets, total_reps) "
            "VALUES (?, ?, ?, 30, 'Basic Pull-ups', 4, 40)",
            (user_id, (TODAY - timedelta(days=n)).isoformat(), workout_type),
        )
    db_conn.commit()


def _subscribe_row(db_conn, user_id, endpoint="https://push.example/ep-1"):
    push_service.save_subscription(db_conn, user_id, endpoint, "p256dh-key", "auth-key")


def _body(endpoint="https://push.example/ep-1"):
    return {"endpoint": endpoint, "keys": {"p256dh": "p256dh-key", "auth": "auth-key"}}


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""


# ─── Config / API ───────────────────────────────────────────────────────────

def test_key_disabled_without_env(app_client, no_vapid, monkeypatch):
    r = app_client.get("/api/workouts/push/key")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "public_key": None}
    assert app_client.post("/api/workouts/push/test").status_code == 503
    assert app_client.post("/api/workouts/push/subscribe", json=_body()).status_code == 503

    # No push jobs are scheduled
    monkeypatch.setattr(CronService, "_run_apply_recurring", staticmethod(lambda: None))
    cron = CronService()
    cron.start()
    try:
        ids = {job.id for job in cron._scheduler.get_jobs()}
    finally:
        cron.stop()
    assert not any(i.startswith("arena_push") for i in ids)


def test_key_enabled_with_env(app_client, vapid, monkeypatch):
    r = app_client.get("/api/workouts/push/key")
    assert r.json() == {"enabled": True, "public_key": vapid}

    monkeypatch.setattr(CronService, "_run_apply_recurring", staticmethod(lambda: None))
    cron = CronService()
    cron.start()
    try:
        jobs = {job.id: job for job in cron._scheduler.get_jobs()}
    finally:
        cron.stop()
    assert "arena_push_morning" in jobs and "arena_push_evening" in jobs
    assert "hour='8'" in str(jobs["arena_push_morning"].trigger)
    assert "minute='40'" in str(jobs["arena_push_morning"].trigger)
    assert "hour='21'" in str(jobs["arena_push_evening"].trigger)
    assert "Asia/Jerusalem" in str(jobs["arena_push_evening"].trigger.timezone)


def test_subscribe_upserts_by_endpoint(app_client, db_conn, vapid, clean_subscriptions):
    yosef_id = db_conn.execute("SELECT id FROM users WHERE name = 'Yosef'").fetchone()["id"]
    for _ in range(2):
        r = app_client.post("/api/workouts/push/subscribe", json=_body())
        assert r.status_code == 200
        assert r.json() == {"ok": True}
    rows = db_conn.execute("SELECT user_id, endpoint FROM push_subscriptions").fetchall()
    assert [(r["user_id"], r["endpoint"]) for r in rows] == [(yosef_id, "https://push.example/ep-1")]

    # A missing field is a 422
    assert app_client.post("/api/workouts/push/subscribe", json={"endpoint": "x"}).status_code == 422
    assert app_client.post("/api/workouts/push/subscribe",
                           json={"endpoint": "x", "keys": {"p256dh": "a"}}).status_code == 422


def test_subscribe_repoints_a_shared_phone(app_client, db_conn, vapid, trainee):
    _subscribe_row(db_conn, trainee)
    app_client.post("/api/workouts/push/subscribe", json=_body())
    yosef_id = db_conn.execute("SELECT id FROM users WHERE name = 'Yosef'").fetchone()["id"]
    rows = db_conn.execute("SELECT user_id FROM push_subscriptions").fetchall()
    assert [r["user_id"] for r in rows] == [yosef_id]


def test_unsubscribe_idempotent(app_client, db_conn, vapid, clean_subscriptions):
    app_client.post("/api/workouts/push/subscribe", json=_body())
    for _ in range(2):
        r = app_client.request("DELETE", "/api/workouts/push/subscribe", json={"endpoint": "https://push.example/ep-1"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
    assert db_conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0


def test_unsubscribe_leaves_other_users_rows(app_client, db_conn, vapid, trainee):
    _subscribe_row(db_conn, trainee, "https://push.example/theirs")
    r = app_client.request("DELETE", "/api/workouts/push/subscribe", json={"endpoint": "https://push.example/theirs"})
    assert r.status_code == 200
    assert db_conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 1


def test_push_test_endpoint_counts_accepted(app_client, db_conn, vapid, clean_subscriptions, monkeypatch):
    route = next(r for r in app_client.app.routes if getattr(r, "path", "") == "/api/workouts/push/test")
    service = route.endpoint.__globals__["push_service"]  # the module the running app uses
    sent = []
    monkeypatch.setattr(service, "_webpush_send", lambda info, data, config: sent.append(json.loads(data)))
    app_client.post("/api/workouts/push/subscribe", json=_body())
    r = app_client.post("/api/workouts/push/test")
    assert r.status_code == 200
    assert r.json() == {"sent": 1}
    assert sent[0]["tag"] == "arena-test"
    assert sent[0]["url"] == "/workouts#profile"
    assert sent[0]["title"] == "🔔 קריאה לזירה"


# ─── The texts ──────────────────────────────────────────────────────────────

def test_evening_skipped_when_trained_today(db_conn, trainee):
    _trained(db_conn, trainee, 0, 1, 2)
    assert push_service.evening_message(db_conn, trainee, TODAY) is None


def test_evening_streak_at_risk_text(db_conn, trainee):
    _trained(db_conn, trainee, 1, 2, 3, 5)
    msg = push_service.evening_message(db_conn, trainee, TODAY)
    assert msg["title"] == "🔥 הרצף בסכנה"
    assert msg["body"] == "הרצף של 3 ימים נגמר בחצות. אימון אחד קצר שומר עליו."
    assert msg["url"] == "/workouts#home"
    assert msg["tag"] == "arena-evening"
    assert (msg["lang"], msg["dir"], msg["icon"]) == ("he", "rtl", "/static/icons/icon-192.png")


def test_evening_streak_of_one_day(db_conn, trainee):
    _trained(db_conn, trainee, 1)
    msg = push_service.evening_message(db_conn, trainee, TODAY)
    assert msg["body"].startswith("הרצף של יום אחד נגמר בחצות")


def test_evening_no_streak_points_to_house(db_conn, trainee):
    _trained(db_conn, trainee, 2, 3)
    msg = push_service.evening_message(db_conn, trainee, TODAY)
    assert msg["title"] == "🏠 עוד לא מאוחר"
    assert msg["body"] == "15 דקות בסלון מספיקות להיום."
    assert msg["url"] == "/workouts#home"


def test_morning_rest_day(db_conn, trainee):
    import app.backend.app.routes.workouts as wk
    _trained(db_conn, trainee, *range(1, wk.RECOVERY_STREAK_DAYS + 1))
    msg = push_service.morning_message(db_conn, trainee, TODAY)
    assert msg["title"] == "☀️ בוקר טוב — יום מנוחה"
    assert msg["body"] == f"{wk.RECOVERY_STREAK_DAYS} ימים ברצף. היום נחים, והכוח נבנה."
    assert msg["url"] == "/workouts#home"
    assert msg["tag"] == "arena-morning"


def test_morning_mission_names_path(db_conn, trainee):
    import app.backend.app.routes.workouts as wk
    _trained(db_conn, trainee, 1)  # a streak of one: not a rest day, and at risk
    history = wk._fetch_history(db_conn, trainee)
    game = wk.compute_gamification(history, TODAY)
    paths = wk.compute_paths(history, game["level"], {}, TODAY)
    key, _note = wk.plan_today(paths, history, TODAY)
    path = next(p for p in paths if p["key"] == key)

    msg = push_service.morning_message(db_conn, trainee, TODAY)
    assert msg["title"] == "☀️ המשימה של היום"
    assert msg["body"] == f"{path['icon']} {path['name']} · {path['current']['hebrew']} · הרצף (1) מחכה לך"
    assert msg["url"] == "/workouts#home"


def test_morning_mission_without_history(db_conn, trainee):
    msg = push_service.morning_message(db_conn, trainee, TODAY)
    assert msg["title"] == "☀️ המשימה של היום"
    assert "הרצף" not in msg["body"]


# ─── Sending ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status, kept", [(410, 0), (404, 0), (500, 1)])
def test_dead_subscription_removed(db_conn, vapid, trainee, monkeypatch, status, kept):
    from pywebpush import WebPushException

    def boom(info, data, config):
        raise WebPushException("push service said no", response=_Resp(status))

    monkeypatch.setattr(push_service, "_webpush_send", boom)
    _subscribe_row(db_conn, trainee)
    assert push_service.send_to_user(db_conn, trainee, push_service.test_message()) == 0
    count = db_conn.execute(
        "SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (trainee,)
    ).fetchone()[0]
    assert count == kept


def test_run_daily_idempotent(db_conn, vapid, trainee, monkeypatch):
    calls = []
    monkeypatch.setattr(push_service, "_webpush_send", lambda info, data, config: calls.append(json.loads(data)))
    _subscribe_row(db_conn, trainee, "https://push.example/a")
    _subscribe_row(db_conn, trainee, "https://push.example/b")

    assert push_service.run_daily("morning", TODAY, conn=db_conn) == 2
    assert push_service.run_daily("morning", TODAY, conn=db_conn) == 0
    assert len(calls) == 2
    assert all(c["tag"] == "arena-morning" for c in calls)
    assert db_conn.execute(
        "SELECT 1 FROM system_settings WHERE key = ?", (f"push_sent:morning:{TODAY.isoformat()}",)
    ).fetchone()

    # The evening is its own run, and silent on a trained day
    _trained(db_conn, trainee, 0)
    assert push_service.run_daily("evening", TODAY, conn=db_conn) == 0
    assert len(calls) == 2


def test_run_daily_off_without_keys(db_conn, no_vapid, trainee, monkeypatch):
    monkeypatch.setattr(push_service, "_webpush_send", lambda *a: pytest.fail("sent without keys"))
    _subscribe_row(db_conn, trainee)
    assert push_service.run_daily("evening", TODAY, conn=db_conn) == 0


# ─── Service worker, manifest, page ─────────────────────────────────────────

def test_sw_has_push_handlers(app_client):
    r = app_client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    assert "addEventListener('push'" in r.text
    assert "notificationclick" in r.text
    assert "addEventListener('fetch'" in r.text


def test_manifest_standalone(app_client):
    r = app_client.get("/static/manifest.json")
    assert r.status_code == 200
    manifest = json.loads(r.content)
    assert manifest["display"] == "standalone"
    assert manifest["id"] == "/"


def test_profile_renders_hidden_push_card(app_client, db_conn):
    # The profile view exists once there is a first workout (before it, the page is the empty state)
    yosef_id = db_conn.execute("SELECT id FROM users WHERE name = 'Yosef'").fetchone()["id"]
    cur = db_conn.execute(
        "INSERT INTO workouts (user_id, date, workout_type, total_duration, exercise_name, total_sets, total_reps) "
        "VALUES (?, ?, 'Pull', 30, 'Basic Pull-ups', 4, 40)",
        (yosef_id, TODAY.isoformat()),
    )
    db_conn.commit()
    try:
        r = app_client.get("/workouts")
    finally:
        db_conn.execute("DELETE FROM workouts WHERE id = ?", (cur.lastrowid,))
        db_conn.commit()
    assert r.status_code == 200
    assert "data-arena-push hidden" in r.text
    assert "בוקר 08:40 · ערב 21:00, רק אם עוד לא התאמנת" in r.text
    assert "/static/js/components/arena-push.js" in r.text
