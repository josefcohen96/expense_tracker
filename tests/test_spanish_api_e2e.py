"""Spanish between sets over HTTP: the queue/reviews/stats API, per-user progress, access
rules, and what the workouts page ships (rest card, #spanish view, profile card, queue).

The shared `app_client` runs with AUTH_ENABLED=0, so every request is Yosef's.
"""
import json
import re

import pytest

from app.backend.app.routes.workouts import compute_gamification
from app.backend.app.services import spanish
from app.backend.app.services.access import can_access_path

QUEUE = "/api/workouts/spanish/queue"
REVIEWS = "/api/workouts/spanish/reviews"
STATS = "/api/workouts/spanish/stats"


@pytest.fixture()
def clean_spanish(db_conn):
    def wipe():
        db_conn.execute("DELETE FROM spanish_reviews")
        db_conn.commit()
    wipe()
    yield
    wipe()


def _user_id(db_conn, name):
    return db_conn.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()["id"]


def test_review_post_validation_and_stage(app_client, db_conn, clean_spanish):
    # Unknown item and out-of-range grade are rejected
    assert app_client.post(REVIEWS, json={"item_id": "basics-999", "grade": 2, "mode": "intro"}).status_code == 422
    assert app_client.post(REVIEWS, json={"item_id": "basics-001", "grade": 4, "mode": "recall"}).status_code == 422
    assert app_client.post(REVIEWS, json={"item_id": "basics-001", "grade": 2, "mode": "quiz"}).status_code == 422
    assert app_client.post(REVIEWS, json={"item_id": "basics-001", "grade": 2, "mode": "intro",
                                          "context": "gym"}).status_code == 422
    assert db_conn.execute("SELECT COUNT(*) FROM spanish_reviews").fetchone()[0] == 0

    # intro → stage 0 due today; טוב → 1; קל → 3
    r = app_client.post(REVIEWS, json={"item_id": "basics-001", "grade": 2, "mode": "intro"})
    assert r.status_code == 201
    body = r.json()
    assert body["item_id"] == "basics-001" and body["stage"] == 0
    assert body["stats"]["seen"] == 1 and body["stats"]["due_today"] == 1

    assert app_client.post(REVIEWS, json={"item_id": "basics-001", "grade": 2, "mode": "recall",
                                          "context": "study"}).json()["stage"] == 1
    last = app_client.post(REVIEWS, json={"item_id": "basics-001", "grade": 3, "mode": "recall"}).json()
    assert last["stage"] == 3
    assert last["stats"]["in_pocket"] == 1

    rows = db_conn.execute("SELECT item_id, grade, mode, context FROM spanish_reviews ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [
        ("basics-001", 2, "intro", "rest"),
        ("basics-001", 2, "recall", "study"),
        ("basics-001", 3, "recall", "rest"),
    ]
    assert rows and all(r["item_id"] for r in rows)
    user_ids = {r[0] for r in db_conn.execute("SELECT user_id FROM spanish_reviews")}
    assert user_ids == {_user_id(db_conn, "Yosef")}

    # Graded קל today → not in today's queue; the stats endpoint agrees
    queue = app_client.get(QUEUE, params={"limit": 50, "new_cap": 15}).json()
    assert "basics-001" not in [c["id"] for c in queue["items"]]
    assert app_client.get(STATS).json()["in_pocket"] == 1


def test_queue_endpoint_fresh_user_and_caps(app_client, clean_spanish):
    body = app_client.get(QUEUE).json()
    assert len(body["items"]) == spanish.DEFAULT_NEW_CAP
    assert all(c["mode"] == "intro" for c in body["items"])
    assert set(body["items"][0]) == {"id", "theme", "theme_title", "es", "he", "target_es",
                                     "target_he", "note", "mode", "stage"}
    assert body["stats"]["new_today_left"] == spanish.DEFAULT_NEW_CAP
    assert len(app_client.get(QUEUE, params={"limit": 3}).json()["items"]) == 3
    assert len(app_client.get(QUEUE, params={"limit": 50, "new_cap": 15}).json()["items"]) == 15
    assert app_client.get(QUEUE, params={"limit": 0}).status_code == 422


def test_reviews_are_per_user(app_client, db_conn, clean_spanish):
    yonatan = _user_id(db_conn, "Yonatan")
    deck = spanish.load_deck()
    for item in deck["items"][:8]:
        spanish.record_review(db_conn, yonatan, item["id"], 2, "intro")
    for item in deck["items"][:3]:
        spanish.record_review(db_conn, yonatan, item["id"], 3, "recall")
        spanish.record_review(db_conn, yonatan, item["id"], 3, "recall")

    theirs = spanish.snapshot(db_conn, yonatan)
    assert theirs["stats"]["in_pocket"] == 3
    assert theirs["stats"]["new_today_left"] == 0

    mine = app_client.get(QUEUE).json()     # Yosef
    assert [c["mode"] for c in mine["items"]] == ["intro"] * spanish.DEFAULT_NEW_CAP
    assert mine["items"][0]["id"] == deck["items"][0]["id"]
    assert mine["stats"]["in_pocket"] == 0
    assert mine["stats"]["seen"] == 0
    assert mine["stats"]["new_today_left"] == spanish.DEFAULT_NEW_CAP

    app_client.post(REVIEWS, json={"item_id": "work-001", "grade": 2, "mode": "intro"})
    assert spanish.snapshot(db_conn, yonatan)["stats"]["seen"] == 8


@pytest.mark.parametrize("user, allowed", [
    ("YOSEF", True),
    ("KARINA", True),
    ("YONATAN", True),
    ("TSAHALA", False),
])
def test_spanish_routes_follow_workouts_access(user, allowed):
    for path in (QUEUE, REVIEWS, STATS):
        assert can_access_path({"username": user}, path) is allowed, (user, path)


def _client_data(html):
    m = re.search(r'<script type="application/json" id="workout-data">(.*?)</script>', html, re.S)
    assert m, "client_data script missing"
    return json.loads(m.group(1))


def test_workout_page_ships_spanish_queue_and_view(app_client, db_conn, clean_spanish):
    yosef = _user_id(db_conn, "Yosef")
    # One session so the page renders the full views (profile included), not the first-workout state
    cur = db_conn.execute(
        "INSERT INTO workouts (user_id, date, workout_type, total_duration, exercise_name, total_sets, total_reps) "
        "VALUES (?, '2026-01-02', 'upper_body', 20, 'Push-ups', 3, 30)", (yosef,))
    db_conn.commit()
    try:
        r = app_client.get("/workouts")
        assert r.status_code == 200
        html = r.text
        assert 'class="rest-card rest-spanish"' in html
        assert 'data-view="spanish"' in html
        assert "wk-spanish-card" in html and 'href="#spanish"' in html
        assert "ספרדית: פועל" in html
        assert "/static/js/spanish.js?v=" in html
        assert "אין מה לחזור עליו עכשיו" in html
        assert "בסיס ונימוס" in html          # theme progress list

        data = _client_data(html)
        queue = data["spanish"]["queue"]
        assert 0 < len(queue) <= 12
        assert queue[0]["id"] == "basics-001" and queue[0]["mode"] == "intro"
        assert data["spanish"]["stats"]["in_pocket"] == 0

        # The one Spanish achievement sits in the achievements list, locked for a fresh learner
        assert "50 מילים בכיס" in html
        badge = re.search(r'data-title="50 מילים בכיס"[^>]*data-unlocked="(\d)"', html)
        assert badge and badge.group(1) == "0"
    finally:
        db_conn.execute("DELETE FROM workouts WHERE id = ?", (cur.lastrowid,))
        db_conn.commit()


def test_spanish_view_renders_before_the_first_workout(app_client, db_conn, clean_spanish):
    yosef = _user_id(db_conn, "Yosef")
    saved = db_conn.execute("SELECT * FROM workouts WHERE user_id = ?", (yosef,)).fetchall()
    db_conn.execute("DELETE FROM workouts WHERE user_id = ?", (yosef,))
    db_conn.commit()
    try:
        html = app_client.get("/workouts").text
        assert "wk-empty" in html
        assert 'data-view="spanish"' in html
        assert 'class="rest-card rest-spanish"' in html
        assert _client_data(html)["spanish"]["queue"]
    finally:
        for row in saved:
            cols = row.keys()
            db_conn.execute(
                f"INSERT INTO workouts ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", tuple(row))
        db_conn.commit()


def test_spanish_50_achievement():
    fresh = {a["id"]: a for a in compute_gamification([])["achievements"]}
    assert fresh["spanish_50"]["unlocked"] is False
    assert fresh["spanish_50"]["title"] == "50 מילים בכיס"
    assert fresh["spanish_50"]["target"] == 50
    unlocked = {a["id"]: a for a in compute_gamification([], spanish_in_pocket=50)["achievements"]}
    assert unlocked["spanish_50"]["unlocked"] is True
