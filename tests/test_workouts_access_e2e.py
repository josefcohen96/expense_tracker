"""Yonatan logs in for the workouts module only: the arena, his own sessions,
and nothing of the household (finances, wedding, renovation).

The shared `app_client` runs with AUTH_ENABLED=0, where AuthMiddleware stands in
Yosef for every request, so everything Yonatan does over HTTP goes through a
client with auth genuinely enabled (same recipe as the redirect-loop test).
"""
import importlib
import json
import os
import sqlite3
import sys

import pytest

from app.backend.app.services.access import (
    can_access_path,
    home_path_for,
    is_module_only_user,
    password_env_var,
)
from app.backend.app.services.people import household, workout_people

MU_BASIC = "עליות מתח בסיסיות (Basic Pull-ups)"  # muscle_up station 0
YONATAN_PASSWORD = "pytest-yonatan"


# ─── Access rules (pure functions, no HTTP) ─────────────────────────────────

@pytest.mark.parametrize("path, allowed", [
    ("/workouts", True),
    ("/workouts/admin", True),
    ("/workouts/legacy-progress", True),
    ("/api/workouts/sessions", True),
    ("/", True),
    ("/logout", True),
    ("/static/css/workout.css", True),
    ("/sw.js", True),
    ("/finances", False),
    ("/finances/transactions", False),
    ("/api/transactions", False),
    ("/wedding/guests", False),
    ("/api/wedding/guests", False),
    ("/renovation", False),
    ("/api/renovation/tasks", False),
    ("/more", False),
    ("/api/today", False),
])
def test_yonatan_reaches_only_the_workouts_module(path, allowed):
    assert can_access_path({"username": "YONATAN"}, path) is allowed
    assert can_access_path("yonatan", path) is allowed


def test_the_household_still_reaches_workouts():
    assert can_access_path({"username": "YOSEF"}, "/workouts/admin") is True
    assert can_access_path({"username": "KARINA"}, "/api/workouts/sessions") is True
    assert can_access_path({"username": "TSAHALA"}, "/workouts") is False


def test_yonatan_is_a_single_module_login():
    assert is_module_only_user("yonatan") is True
    assert is_module_only_user({"username": "TSAHALA"}) is True
    assert is_module_only_user("KARINA") is False
    assert is_module_only_user(None) is False
    assert home_path_for({"username": "YONATAN"}) == "/workouts"
    assert password_env_var("yonatan") == "USER_PASSWORD_YONATAN"


# ─── Who trains, who pays (shared client, auth off) ─────────────────────────

def test_yonatan_has_a_users_row_but_is_not_household(app_client, db_conn):
    row = db_conn.execute("SELECT id FROM users WHERE name = 'Yonatan'").fetchone()
    assert row is not None

    assert {p["name"] for p in household(db_conn)} == {"Yosef", "Karina"}

    everyone = workout_people(db_conn)
    assert [p["name"] for p in everyone] == ["Yosef", "Karina", "Yonatan"]
    assert len({p["color"] for p in everyone}) == 3

    own = workout_people(db_conn, {"username": "YONATAN"})
    assert [p["name"] for p in own] == ["Yonatan"]
    assert own[0]["display"] == "יונתן"

    # The household back office sees everyone who trains
    assert [p["name"] for p in workout_people(db_conn, "YOSEF")] == ["Yosef", "Karina", "Yonatan"]


def test_finance_payer_dropdown_never_lists_yonatan(app_client, db_conn):
    yosef_id = db_conn.execute("SELECT id FROM users WHERE name = 'Yosef'").fetchone()["id"]
    category_id = db_conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()["id"]
    cur = db_conn.execute(
        "INSERT INTO transactions (date, amount, category_id, user_id, notes) VALUES (?, ?, ?, ?, ?)",
        ("2026-06-01", -12.5, category_id, yosef_id, "payer dropdown check"),
    )
    db_conn.commit()
    try:
        html = app_client.get(f"/transactions/{cur.lastrowid}/edit-inline").text
        assert "Yosef" in html
        assert "Yonatan" not in html
    finally:
        db_conn.execute("DELETE FROM transactions WHERE id = ?", (cur.lastrowid,))
        db_conn.commit()


def test_household_admin_can_pick_yonatan(app_client, db_conn):
    html = app_client.get("/workouts/admin").text
    yonatan_id = db_conn.execute("SELECT id FROM users WHERE name = 'Yonatan'").fetchone()["id"]
    assert f'href="/workouts/admin?user={yonatan_id}"' in html
    assert "יונתן" in html


# ─── Yonatan over HTTP (auth genuinely enabled) ─────────────────────────────

@pytest.fixture(scope="module")
def authed(tmp_path_factory):
    """A TestClient with real auth and its own fresh DB, plus that DB's path."""
    keys = (
        "BUDGET_DB_PATH", "AUTH_ENABLED", "USER_PASSWORD_YOSEF", "USER_PASSWORD_KARINA",
        "USER_PASSWORD_YONATAN", "SESSION_SECRET_KEY", "ALLOWED_HOSTS",
    )
    saved_env = {k: os.environ.get(k) for k in keys}

    tmp_db = tmp_path_factory.mktemp("yonatan_db") / "budget_yonatan_test.sqlite3"
    os.environ["BUDGET_DB_PATH"] = str(tmp_db)
    os.environ["AUTH_ENABLED"] = "1"
    os.environ["USER_PASSWORD_YOSEF"] = "test-password-yosef"
    os.environ["USER_PASSWORD_KARINA"] = "test-password-karina"
    os.environ["USER_PASSWORD_YONATAN"] = YONATAN_PASSWORD
    os.environ.setdefault("SESSION_SECRET_KEY", "pytest-only-not-for-production")
    os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")

    def forget_app_modules():
        for mod_name in list(sys.modules):
            if mod_name.startswith("app.backend.app"):
                del sys.modules[mod_name]

    # main.py reads AUTH_ENABLED at import time, so import the app afresh.
    forget_app_modules()
    import app.backend.app.db as db_module
    importlib.reload(db_module)
    db_module.initialise_database()
    import app.backend.app.main as main_module

    from fastapi.testclient import TestClient
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


@pytest.fixture()
def authed_client(authed):
    return authed[0]


@pytest.fixture()
def authed_db(authed):
    conn = sqlite3.connect(str(authed[1]))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def ids(authed_db):
    rows = authed_db.execute("SELECT id, name FROM users WHERE name IN ('Yosef', 'Yonatan')").fetchall()
    return {row["name"]: row["id"] for row in rows}


@pytest.fixture()
def clean_workouts(authed_db):
    def wipe():
        authed_db.execute("DELETE FROM workouts")
        authed_db.execute("DELETE FROM system_settings WHERE key LIKE 'workouts_legacy_conquered:%'")
        authed_db.commit()
    wipe()
    yield
    wipe()


def _session_body(user_id, day="2026-06-13"):
    return {
        "user_id": user_id,
        "date": day,
        "workout_type": "Pull",
        "total_duration": 30,
        "exercises": [
            {"exercise_name": MU_BASIC, "total_sets": 4, "total_reps": 40, "max_reps": 11,
             "skill_key": "muscle_up", "stage_index": 0},
        ],
    }


def _login(client, username, password):
    # This module logs in more often than the per-IP limit allows in one window.
    import app.backend.app.routes.pages as pages
    pages._login_attempts.clear()
    r = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


@pytest.fixture()
def yosef_session(authed_client, ids, clean_workouts):
    """A session of Yosef's, saved by Yosef himself."""
    _login(authed_client, "yosef", "test-password-yosef")
    r = authed_client.post("/api/workouts/sessions", json=_session_body(ids["Yosef"]))
    assert r.status_code == 201, r.text
    authed_client.get("/logout", follow_redirects=False)
    return r.json()


@pytest.fixture()
def as_yonatan(authed_client):
    r = _login(authed_client, "yonatan", YONATAN_PASSWORD)
    assert r.headers["location"] == "/workouts"
    try:
        yield
    finally:
        authed_client.get("/logout", follow_redirects=False)


def _admin_data(html):
    return json.loads(html.split('id="workout-admin-data">')[1].split("</script>")[0])


def test_home_forwards_yonatan_to_the_arena(authed_client, as_yonatan):
    r = authed_client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/workouts"


@pytest.mark.parametrize("path", ["/finances", "/wedding/tasks", "/more", "/renovation"])
def test_other_modules_send_yonatan_back_to_the_arena(authed_client, as_yonatan, path):
    r = authed_client.get(path, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/workouts"


def test_other_apis_are_forbidden_for_yonatan(authed_client, as_yonatan):
    assert authed_client.get("/api/transactions", follow_redirects=False).status_code == 302
    assert authed_client.post("/api/wedding/tasks", json={"title": "x"}).status_code == 403
    assert authed_client.get("/api/today", follow_redirects=False).status_code == 302


def test_arena_has_no_household_navigation(authed_client, as_yonatan):
    r = authed_client.get("/workouts")
    assert r.status_code == 200
    html = r.text
    assert 'id="mobile-tab-bar"' not in html
    assert 'href="/finances"' not in html
    assert 'href="/wedding"' not in html
    assert 'href="/renovation"' not in html
    assert 'href="/logout"' in html


def test_admin_page_shows_only_yonatan(authed_client, ids, yosef_session, as_yonatan):
    html = authed_client.get("/workouts/admin").text
    data = _admin_data(html)
    assert data["user_id"] == ids["Yonatan"]
    assert data["sessions"] == []
    assert 'href="/workouts/admin?user=' not in html  # no person switcher

    # Asking for Yosef by id falls back to his own view
    data = _admin_data(authed_client.get(f"/workouts/admin?user={ids['Yosef']}").text)
    assert data["user_id"] == ids["Yonatan"]


def test_api_lists_and_writes_only_his_own_sessions(authed_client, ids, yosef_session, as_yonatan):
    assert authed_client.get("/api/workouts/sessions").json() == []
    assert authed_client.get(f"/api/workouts/sessions?user_id={ids['Yosef']}").status_code == 403

    denied = authed_client.post("/api/workouts/sessions", json=_session_body(ids["Yosef"], "2026-06-14"))
    assert denied.status_code == 403

    created = authed_client.post("/api/workouts/sessions", json=_session_body(ids["Yonatan"], "2026-06-14"))
    assert created.status_code == 201, created.text
    own_id = created.json()["id"]
    assert created.json()["user_id"] == ids["Yonatan"]

    listed = authed_client.get("/api/workouts/sessions").json()
    assert [s["user_id"] for s in listed] == [ids["Yonatan"]]

    # Yosef's session is out of reach for editing, moving or deleting
    r = authed_client.put(f"/api/workouts/sessions/{yosef_session['id']}", json=_session_body(ids["Yosef"]))
    assert r.status_code == 403
    r = authed_client.put(f"/api/workouts/sessions/{own_id}", json=_session_body(ids["Yosef"]))
    assert r.status_code == 403
    assert authed_client.delete(f"/api/workouts/sessions/{yosef_session['id']}").status_code == 403
    assert authed_client.put("/api/workouts/legacy-progress",
                             json={"user_id": ids["Yosef"], "progress": {}}).status_code == 403

    # His own are fine
    r = authed_client.put(f"/api/workouts/sessions/{own_id}", json=_session_body(ids["Yonatan"], "2026-06-15"))
    assert r.status_code == 200, r.text
    own_id = r.json()["id"]  # the exercise list was replaced, so the session has a new row id
    assert authed_client.delete(f"/api/workouts/sessions/{own_id}").status_code == 200
    assert authed_client.put("/api/workouts/legacy-progress",
                             json={"user_id": ids["Yonatan"], "progress": {}}).status_code == 200


def test_arena_saves_under_yonatans_own_row(authed_client, ids, clean_workouts, as_yonatan, authed_db):
    r = authed_client.post("/workouts", json={
        "date": "2026-06-15",
        "workout_type": "Pull",
        "total_duration": 20,
        "exercises": [{"exercise_name": MU_BASIC, "total_sets": 3, "total_reps": 24,
                       "skill_key": "muscle_up", "stage_index": 0, "max_reps": 8}],
    })
    assert r.status_code in (200, 201), r.text
    owners = {row["user_id"] for row in authed_db.execute("SELECT user_id FROM workouts").fetchall()}
    assert owners == {ids["Yonatan"]}


def test_yosef_still_manages_everyone(authed_client, ids, clean_workouts):
    _login(authed_client, "yosef", "test-password-yosef")
    try:
        html = authed_client.get("/workouts/admin").text
        assert f'href="/workouts/admin?user={ids["Yonatan"]}"' in html
        r = authed_client.post("/api/workouts/sessions", json=_session_body(ids["Yonatan"]))
        assert r.status_code == 201, r.text
        assert authed_client.delete(f"/api/workouts/sessions/{r.json()['id']}").status_code == 200
    finally:
        authed_client.get("/logout", follow_redirects=False)
