"""The wedding as the workout game's final boss — Yosef's home view only.

Everything is derived from the wedding date plus the workout history; nothing is stored.
The shared `app_client` runs with AUTH_ENABLED=0, where AuthMiddleware stands in Yosef,
so the "who sees it" test logs in as each user through a client with auth enabled
(same recipe as tests/test_workouts_access_e2e.py). Those tests sit at the end of the
file so the module-scoped auth client is only set up after the shared-client tests.
"""
import importlib
import os
import sqlite3
import sys
from datetime import date, timedelta

import pytest

import app.backend.app.routes.workouts as workouts

HSPU_WALL = workouts.station_exercise_name(workouts.SKILL_PROGRESSIONS["hspu"]["progressions"][0])


# ─── Pure computation ───────────────────────────────────────────────────────

def _history(days):
    return [{"date": d.isoformat(), "workout_type": "Pull", "total_duration": 30, "exercises": []} for d in days]


def _fake_path(key, remaining, unlocked=True):
    stations = [
        {"number": i + 1, "hebrew": f"תחנה-{i + 1}", "remaining": r, "conquered": r == 0}
        for i, r in enumerate(remaining)
    ]
    return {
        "key": key,
        "unlocked": unlocked,
        "complete": all(st["conquered"] for st in stations),
        "stations": stations,
    }


def test_wedding_boss_pace_measured_and_assumed():
    today = date(2026, 9, 25)
    wedding = today + timedelta(days=28)

    # 8 distinct days inside the last 56 (one twice, one future-free), plus one outside the window
    days = [today - timedelta(days=n) for n in (0, 3, 10, 17, 24, 31, 40, 55)]
    history = _history(days + [today - timedelta(days=3), today - timedelta(days=56)])
    boss = workouts.wedding_boss(history, [], wedding, today)
    assert boss["per_week"] == 1.0
    assert boss["trainings_left"] == 4
    assert boss["assumed"] is False
    assert boss["days_left"] == 28
    assert boss["days_label"] == "בעוד 28 ימים"
    assert boss["recent_28"] == 5  # days 0, 3, 10, 17, 24

    two_days = _history([today - timedelta(days=1), today - timedelta(days=5)])
    boss = workouts.wedding_boss(two_days, [], wedding, today)
    assert boss["per_week"] == 2.0
    assert boss["assumed"] is True
    assert boss["trainings_left"] == 8

    # Wording for the last days, and nothing once the wedding has passed
    assert workouts.wedding_boss([], [], today + timedelta(days=1), today)["days_label"] == "מחר"
    assert workouts.wedding_boss([], [], today, today)["days_label"] == "היום"
    assert workouts.wedding_boss([], [], today, today)["trainings_left"] == 0
    assert workouts.wedding_boss([], [], today - timedelta(days=1), today) is None


def test_wedding_boss_pace_of_a_fresh_start_is_measured_since_the_first_training():
    today = date(2026, 9, 24)
    wedding = today + timedelta(days=397)

    # Started on Sunday and trained every day since: five trainings in five days
    five_days = _history([today - timedelta(days=n) for n in range(5)])
    boss = workouts.wedding_boss(five_days, [], wedding, today)
    assert boss["pace_window_days"] == 7          # never shorter than a week
    assert boss["per_week"] == 5.0                # not 5 / 8 weeks = 0.6
    assert boss["assumed"] is False
    assert boss["trainings_left"] == round(5 * 397 / 7)

    # Three weeks in, three trainings a week: the window follows the first training
    three_weeks = _history([today - timedelta(days=n) for n in (0, 2, 4, 7, 9, 11, 14, 16, 18, 20)])
    boss = workouts.wedding_boss(three_weeks, [], wedding, today)
    assert boss["pace_window_days"] == 21
    assert boss["per_week"] == 3.3

    # A history older than eight weeks is still measured over the last eight
    old = _history([today - timedelta(days=n) for n in (0, 3, 70, 90)])
    assert workouts.wedding_boss(old, [], wedding, today)["pace_window_days"] == 56


def test_wedding_boss_forecast_walks_remaining_stations():
    today = date(2026, 9, 25)
    paths = [
        _fake_path("walk", [0, 2, 5, 5]),          # first station already conquered
        _fake_path("done", [0, 0]),                # complete: no forecast
        _fake_path("locked", [5, 5], unlocked=False),
    ]
    # 6 trainings left: 21 days at the assumed 2/week
    boss = workouts.wedding_boss([], paths, today + timedelta(days=21), today)
    assert boss["trainings_left"] == 6
    assert set(boss["paths"]) == {"walk"}
    assert boss["paths"]["walk"] == {"finishes": False, "station_number": 3, "station_hebrew": "תחנה-3"}

    # Same path without the conquered first station: remaining [2, 5, 5] reaches station 2 (index 1)
    boss = workouts.wedding_boss([], [_fake_path("p", [2, 5, 5])], today + timedelta(days=21), today)
    assert boss["paths"]["p"]["station_number"] == 2
    assert boss["paths"]["p"]["finishes"] is False

    # 12 trainings left covers 2 + 5 + 5
    boss = workouts.wedding_boss([], [_fake_path("p", [2, 5, 5])], today + timedelta(days=42), today)
    assert boss["trainings_left"] == 12
    assert boss["paths"]["p"] == {"finishes": True, "station_number": None, "station_hebrew": None}


# ─── Yosef's page (shared client, auth off = Yosef) ─────────────────────────

@pytest.fixture()
def clean_workouts(app_client, db_conn):
    def wipe():
        db_conn.execute("DELETE FROM workouts")
        db_conn.execute("DELETE FROM system_settings WHERE key LIKE 'workouts_legacy_conquered:%'")
        db_conn.commit()
    wipe()
    yield
    wipe()


def _set_wedding_date(conn, value):
    if value is None:
        conn.execute("DELETE FROM wedding_settings WHERE key='wedding_date'")
    else:
        conn.execute(
            "INSERT OR REPLACE INTO wedding_settings (key, value) VALUES ('wedding_date', ?)",
            (value.isoformat(),),
        )
    conn.commit()


@pytest.fixture()
def wedding_date(db_conn):
    """Setter for the wedding date (written directly, so no milestones get seeded); restores it."""
    row = db_conn.execute("SELECT value FROM wedding_settings WHERE key='wedding_date'").fetchone()
    original = row[0] if row else None
    yield lambda value: _set_wedding_date(db_conn, value)
    if original is None:
        db_conn.execute("DELETE FROM wedding_settings WHERE key='wedding_date'")
    else:
        db_conn.execute("INSERT OR REPLACE INTO wedding_settings (key, value) VALUES ('wedding_date', ?)", (original,))
    db_conn.commit()


def _train_hspu(app_client):
    r = app_client.post("/workouts", json={
        "date": date.today().isoformat(),
        "workout_type": "Push",
        "total_duration": 20,
        "exercises": [{"exercise_name": HSPU_WALL, "total_sets": 3, "total_reps": 60,
                       "skill_key": "hspu", "stage_index": 0, "max_reps": 20}],
    })
    assert r.status_code == 200, r.text


def _mission_card(html, key):
    return html.split(f'data-mission="{key}"')[1].split("</article>")[0]


def test_yosef_sees_the_boss_banner(app_client, clean_workouts, wedding_date):
    wedding_date(date.today() + timedelta(days=30))
    _train_hspu(app_client)
    # Five in-range sessions on every muscle-up station: the path is complete
    steps = workouts.SKILL_PROGRESSIONS["muscle_up"]["progressions"]
    for back in range(1, 6):
        r = app_client.post("/workouts", json={
            "date": (date.today() - timedelta(days=back)).isoformat(),
            "workout_type": "Pull",
            "total_duration": 40,
            "exercises": [{"exercise_name": workouts.station_exercise_name(step), "total_sets": 3,
                           "total_reps": 3 * step["reps"], "skill_key": "muscle_up", "stage_index": idx,
                           "max_reps": step["reps"]} for idx, step in enumerate(steps)],
        })
        assert r.status_code == 200, r.text

    html = app_client.get("/workouts").text
    assert 'class="wk-boss"' in html
    assert "הבוס הסופי" in html
    assert "החתונה בעוד 30 ימים" in html
    assert "אימונים בקצב שלך" in html  # six training days in 8 weeks: the pace is measured
    assert html.index("הבוס הסופי") < html.index('data-mission="')  # above the first mission card

    hspu = _mission_card(html, "hspu")
    assert "wk-mission-boss" in hspu
    assert "עד החתונה תגיע לתחנה" in hspu

    muscle_up = _mission_card(html, "muscle_up")
    assert "הושלם" in muscle_up  # precondition: the path is complete
    assert "wk-mission-boss" not in muscle_up


def test_no_banner_without_or_after_wedding_date(app_client, clean_workouts, wedding_date):
    _train_hspu(app_client)

    wedding_date(None)
    html = app_client.get("/workouts").text
    assert "הבוס הסופי" not in html
    assert "wk-mission-boss" not in html

    wedding_date(date.today() - timedelta(days=1))
    html = app_client.get("/workouts").text
    assert "הבוס הסופי" not in html
    assert "wk-mission-boss" not in html

    # The wedding day itself still counts
    wedding_date(date.today())
    assert "החתונה היום" in app_client.get("/workouts").text


# ─── Karina and Yonatan (auth genuinely enabled) ────────────────────────────

@pytest.fixture(scope="module")
def authed(tmp_path_factory):
    """A TestClient with real auth and its own fresh DB, plus that DB's path."""
    keys = (
        "BUDGET_DB_PATH", "AUTH_ENABLED", "USER_PASSWORD_YOSEF", "USER_PASSWORD_KARINA",
        "USER_PASSWORD_YONATAN", "SESSION_SECRET_KEY", "ALLOWED_HOSTS",
    )
    saved_env = {k: os.environ.get(k) for k in keys}

    tmp_db = tmp_path_factory.mktemp("boss_db") / "budget_boss_test.sqlite3"
    os.environ["BUDGET_DB_PATH"] = str(tmp_db)
    os.environ["AUTH_ENABLED"] = "1"
    os.environ["USER_PASSWORD_YOSEF"] = "test-password-yosef"
    os.environ["USER_PASSWORD_KARINA"] = "test-password-karina"
    os.environ["USER_PASSWORD_YONATAN"] = "test-password-yonatan"
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


def _login(client, username, password):
    import app.backend.app.routes.pages as pages
    pages._login_attempts.clear()
    r = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def _page_as(client, username, password):
    _login(client, username, password)
    try:
        r = client.get("/workouts")
        assert r.status_code == 200, r.text
        return r.text
    finally:
        client.get("/logout", follow_redirects=False)


def test_household_and_yonatan_do_not_see_the_boss(authed):
    client, db_path = authed
    conn = sqlite3.connect(str(db_path))
    try:
        _set_wedding_date(conn, date.today() + timedelta(days=30))
        # Each of them has a history, so the home view with mission cards renders
        for name, password in (("yosef", "test-password-yosef"), ("karina", "test-password-karina"),
                               ("yonatan", "test-password-yonatan")):
            _login(client, name, password)
            try:
                _train_hspu(client)
            finally:
                client.get("/logout", follow_redirects=False)

        # Positive control on the same client: the gate opens for Yosef
        assert "הבוס הסופי" in _page_as(client, "yosef", "test-password-yosef")

        for name, password in (("karina", "test-password-karina"), ("yonatan", "test-password-yonatan")):
            html = _page_as(client, name, password)
            assert "המשימה של היום" in html
            assert "הבוס הסופי" not in html
            assert "wk-boss" not in html
            assert "wk-mission-boss" not in html
            assert "החתונה" not in html
    finally:
        conn.close()
