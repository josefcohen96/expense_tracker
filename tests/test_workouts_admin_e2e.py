import json
from datetime import date

import pytest

MU_BASIC = "עליות מתח בסיסיות (Basic Pull-ups)"  # muscle_up station 0


@pytest.fixture()
def clean_workouts(app_client, db_conn):
    """Start and finish every test with no workouts / imported flags."""
    def wipe():
        db_conn.execute("DELETE FROM workouts")
        db_conn.execute("DELETE FROM system_settings WHERE key LIKE 'workouts_legacy_conquered:%'")
        db_conn.commit()
    wipe()
    yield
    wipe()


@pytest.fixture()
def user_id(db_conn):
    return db_conn.execute("SELECT id FROM users WHERE name = 'Yosef'").fetchone()["id"]


def _create(app_client, user_id, day="2026-06-13", exercises=None, workout_type="Pull", duration=30):
    r = app_client.post("/api/workouts/sessions", json={
        "user_id": user_id,
        "date": day,
        "workout_type": workout_type,
        "total_duration": duration,
        "exercises": exercises if exercises is not None else [
            {"exercise_name": MU_BASIC, "total_sets": 4, "total_reps": 40, "max_reps": 11,
             "skill_key": "muscle_up", "stage_index": 0},
            {"exercise_name": "Dips", "total_sets": 3, "total_reps": 30},
        ],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _admin_data(app_client, user_id=None):
    url = "/workouts/admin" + (f"?user={user_id}" if user_id else "")
    html = app_client.get(url).text
    return html, json.loads(html.split('id="workout-admin-data">')[1].split("</script>")[0])


def test_admin_page_lists_saved_sessions(app_client, user_id, clean_workouts):
    _create(app_client, user_id)
    html, data = _admin_data(app_client, user_id)

    assert "ניהול אימונים" in html
    assert "2026-06-13" in html
    assert "עליות מתח בסיסיות" in html  # station rows show their Hebrew title
    assert "מקבילים" in html            # catalog exercise (Dips)

    assert data["user_id"] == user_id
    session = data["sessions"][0]
    assert session["workout_type"] == "Pull" and session["total_duration"] == 30
    assert session["sets"] == 7 and session["reps"] == 70
    assert session["xp"] == 50 + 7 * 10 + 70 + 30 * 2
    assert [ex["skill_key"] for ex in session["exercises"]] == ["muscle_up", None]
    # The picker offers every quest station and the free-workout catalog
    values = {o["value"] for group in data["exercise_options"] for o in group["options"]}
    assert MU_BASIC in values and "Push-ups" in values


def test_admin_page_is_empty_for_the_other_person(app_client, db_conn, user_id, clean_workouts):
    _create(app_client, user_id)
    karina = db_conn.execute("SELECT id FROM users WHERE name = 'Karina'").fetchone()["id"]
    html, data = _admin_data(app_client, karina)
    assert data["sessions"] == []
    assert "אין אימונים שמורים" in html


def test_create_session_feeds_the_game(app_client, db_conn, user_id, clean_workouts):
    body = _create(app_client, user_id, day=date.today().isoformat())
    assert body["date"] == date.today().isoformat()
    assert len(body["exercises"]) == 2

    rows = db_conn.execute(
        "SELECT exercise_name, total_sets, total_reps, max_reps, skill_key, stage_index "
        "FROM workouts ORDER BY id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        (MU_BASIC, 4, 40, 11, "muscle_up", 0),
        ("Dips", 3, 30, None, None, None),
    ]
    # The arena picks the manual session up like any other workout
    assert "המשימה של היום" in app_client.get("/workouts").text


def test_create_resolves_the_station_by_name(app_client, db_conn, user_id, clean_workouts):
    """A station saved without skill_key is still matched back to its quest station."""
    _create(app_client, user_id, exercises=[
        {"exercise_name": MU_BASIC, "total_sets": 3, "total_reps": 30},
    ])
    row = db_conn.execute("SELECT skill_key, stage_index FROM workouts").fetchone()
    assert (row["skill_key"], row["stage_index"]) == ("muscle_up", 0)


def test_update_session_edits_details_and_rows(app_client, db_conn, user_id, clean_workouts):
    created = _create(app_client, user_id)
    kept = created["exercises"][0]

    r = app_client.put(f"/api/workouts/sessions/{created['id']}", json={
        "user_id": user_id,
        "date": "2026-06-14",
        "workout_type": "Push",
        "total_duration": 45,
        "exercises": [
            {"id": kept["id"], "exercise_name": MU_BASIC, "total_sets": 5, "total_reps": 45,
             "max_reps": 12, "skill_key": "muscle_up", "stage_index": 0},
            {"exercise_name": "Push-ups", "total_sets": 2, "total_reps": 24},
        ],
    })
    assert r.status_code == 200, r.text
    session = r.json()
    assert session["date"] == "2026-06-14"
    assert session["workout_type"] == "Push" and session["total_duration"] == 45
    assert session["sets"] == 7 and session["reps"] == 69

    # The dropped row is gone, the kept row moved with the session
    rows = db_conn.execute(
        "SELECT exercise_name, date, workout_type, total_duration, total_sets FROM workouts ORDER BY id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        (MU_BASIC, "2026-06-14", "Push", 45, 5),
        ("Push-ups", "2026-06-14", "Push", 45, 2),
    ]


def test_update_rejects_a_row_from_another_session(app_client, user_id, clean_workouts):
    first = _create(app_client, user_id, day="2026-06-13")
    second = _create(app_client, user_id, day="2026-06-20")
    r = app_client.put(f"/api/workouts/sessions/{second['id']}", json={
        "user_id": user_id,
        "date": "2026-06-20",
        "workout_type": "Pull",
        "total_duration": 30,
        "exercises": [{"id": first["exercises"][0]["id"], "exercise_name": "Dips",
                       "total_sets": 1, "total_reps": 10}],
    })
    assert r.status_code == 400
    assert "not in this session" in r.json()["detail"]


def test_write_validation(app_client, user_id, clean_workouts):
    base = {"user_id": user_id, "date": "2026-06-13", "workout_type": "Pull", "total_duration": 30}
    one = [{"exercise_name": "Dips", "total_sets": 1, "total_reps": 10}]

    assert app_client.post("/api/workouts/sessions", json={**base, "exercises": []}).status_code == 400
    assert app_client.post("/api/workouts/sessions", json={**base, "date": "13/06/2026",
                                                           "exercises": one}).status_code == 400
    assert app_client.post("/api/workouts/sessions", json={**base, "user_id": 9999,
                                                           "exercises": one}).status_code == 400
    assert app_client.post("/api/workouts/sessions", json={**base, "exercises": [
        {"exercise_name": "Dips", "total_sets": -1, "total_reps": 10}]}).status_code == 422
    assert app_client.put("/api/workouts/sessions/999999", json={**base, "exercises": one}).status_code == 404
    assert app_client.delete("/api/workouts/sessions/999999").status_code == 404


def test_delete_session_removes_every_row(app_client, db_conn, user_id, clean_workouts):
    created = _create(app_client, user_id)
    r = app_client.delete(f"/api/workouts/sessions/{created['id']}")
    assert r.status_code == 200
    assert r.json() == {"deleted": True, "exercises": 2}
    assert db_conn.execute("SELECT COUNT(*) c FROM workouts").fetchone()["c"] == 0


def test_list_sessions_endpoint(app_client, user_id, clean_workouts):
    _create(app_client, user_id, day="2026-06-13")
    _create(app_client, user_id, day="2026-06-20")
    sessions = app_client.get("/api/workouts/sessions", params={"user_id": user_id}).json()
    assert [s["date"] for s in sessions] == ["2026-06-20", "2026-06-13"]  # newest first
    assert app_client.get("/api/workouts/sessions", params={"user_id": 9999}).status_code == 400


def test_imported_stations_are_shown_and_can_be_cleared(app_client, db_conn, user_id, clean_workouts):
    app_client.post("/workouts/legacy-progress", json={"progress": {"muscle_up": [0, 1], "planche": [0]}})
    html, _ = _admin_data(app_client, user_id)
    assert "תחנות שיובאו ידנית" in html
    assert html.count('data-legacy data-skill') == 3  # one chip per imported station

    # Keep one station, drop the rest
    r = app_client.put("/api/workouts/legacy-progress",
                       json={"user_id": user_id, "progress": {"muscle_up": [1]}})
    assert r.status_code == 200
    assert r.json()["progress"] == {"muscle_up": [1]}

    r = app_client.put("/api/workouts/legacy-progress", json={"user_id": user_id, "progress": {}})
    assert r.json() == {"status": "success", "progress": {}, "stations": 0}
    assert db_conn.execute(
        "SELECT COUNT(*) c FROM system_settings WHERE key LIKE 'workouts_legacy_conquered:%'"
    ).fetchone()["c"] == 0
    html, _ = _admin_data(app_client, user_id)
    assert 'data-legacy data-skill' not in html
