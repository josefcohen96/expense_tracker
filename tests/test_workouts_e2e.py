import json
import struct
from datetime import date, timedelta

import pytest

import app.backend.app.routes.workouts as workouts

MU_BASIC = "עליות מתח בסיסיות (Basic Pull-ups)"  # muscle_up station 0, target 10 reps


@pytest.fixture()
def clean_workouts(app_client, db_conn):
    """Start and finish every test with no workouts / imported flags for the test user."""
    def wipe():
        db_conn.execute("DELETE FROM workouts")
        db_conn.execute("DELETE FROM system_settings WHERE key LIKE 'workouts_legacy_conquered:%'")
        db_conn.commit()
    wipe()
    yield
    wipe()


def _save(app_client, day, exercises, workout_type="Pull", duration=30):
    r = app_client.post("/workouts", json={
        "date": day,
        "workout_type": workout_type,
        "total_duration": duration,
        "exercises": exercises,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _session(day, exercises, duration=30):
    """History entry in the shape _fetch_history returns."""
    return {
        "date": day,
        "workout_type": "Pull",
        "total_duration": duration,
        "exercises": [
            {"name": name, "title": name, "sets": sets, "reps": reps, "max_reps": None,
             "station": workouts._station_for(None, None, name)}
            for name, sets, reps in exercises
        ],
    }


def test_first_run_page(app_client, clean_workouts):
    r = app_client.get("/workouts")
    assert r.status_code == 200
    html = r.text
    assert "המסע מתחיל בשלב 1" in html
    assert "או התחל אימון חופשי בלי מסלול" in html
    # Arena shell, sheet and picker are always on the page
    for marker in ('id="arena"', 'data-phase-panel="set"', 'data-phase-panel="rest"',
                   'data-phase-panel="reward"', 'id="arena-sheet"', 'id="exercise-modal"',
                   'id="arena-form-layer"'):
        assert marker in html
    # No dashboards / zero counters on first run, and no manual conquer button anywhere
    assert 'data-view="profile"' not in html
    assert "כבשתי" not in html
    assert "victory-modal" not in html and "rest-timer-banner" not in html
    data = json.loads(html.split('id="workout-data">')[1].split("</script>")[0])
    assert data["first_workout"] is True
    assert "holo" not in data  # no model shipped → plain arena
    assert data["form"]["Push-ups"]["holo_key"] == "push_ups"


def test_page_with_history(app_client, clean_workouts):
    _save(app_client, date.today().isoformat(), [
        {"exercise_name": MU_BASIC, "total_sets": 4, "total_reps": 40, "max_reps": 10,
         "skill_key": "muscle_up", "stage_index": 0},
    ])
    html = app_client.get("/workouts").text
    for view in ("home", "map", "profile", "history"):
        assert f'data-view="{view}"' in html
    assert "המשימה של היום" in html
    assert "סולם הדרגות" in html
    assert "player-level" in html
    for _, title, _ in workouts.RANKS:
        assert title in html
    assert "כבשתי" not in html
    assert 'aria-label="1 מתוך 5 אימונים לכיבוש התחנה"' in html  # station progress is counted


def test_save_workout_success(app_client, db_conn, clean_workouts):
    """Saving aggregates exercise info, stores the station and best set, and returns rewards."""
    test_date = "2026-06-13"
    body = _save(app_client, test_date, [
        {"exercise_name": "Pull-ups", "total_sets": 3, "total_reps": 30, "max_reps": 11},
        {"exercise_name": "Dips", "total_sets": 2, "total_reps": 24},
        {"exercise_name": MU_BASIC, "total_sets": 0, "total_reps": 0,
         "skill_key": "muscle_up", "stage_index": 0},  # no sets → not stored
    ], workout_type="Calisthenics", duration=45)
    assert body["status"] == "success"
    assert body["message"] == "Workout saved successfully!"

    # 5 sets, 54 reps, 45 minutes → 50 + 5*10 + 54 + 45*2 = 244
    rewards = body["rewards"]
    assert rewards["xp_gained"] == 244
    assert rewards["new_level"] >= rewards["old_level"]
    assert rewards["total_xp"] >= rewards["xp_gained"]
    assert "rank" in rewards and "title" in rewards["rank"]
    assert rewards["next_rank"]["xp_needed"] > 0
    assert isinstance(rewards["new_achievements"], list)
    assert rewards["new_records"] == []  # no earlier history to beat
    assert 0 <= rewards["progress_pct"] <= 100

    rows = db_conn.execute(
        "SELECT exercise_name, total_sets, total_reps, max_reps, skill_key, stage_index "
        "FROM workouts WHERE date = ? ORDER BY exercise_name",
        (test_date,)
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("Dips", 2, 24, None, None, None),
        ("Pull-ups", 3, 30, 11, None, None),
    ]


def test_station_is_conquered_by_count(app_client, clean_workouts):
    today = date.today()
    station = {"exercise_name": MU_BASIC, "total_sets": 3, "total_reps": 30, "max_reps": 10,
               "skill_key": "muscle_up", "stage_index": 0}
    # Below the rep range (avg 5 < 8) — trained, but doesn't count
    _save(app_client, (today - timedelta(days=10)).isoformat(),
          [{**station, "total_reps": 15, "max_reps": 5}])
    for i in range(4):
        body = _save(app_client, (today - timedelta(days=8 - i)).isoformat(), [station])
        assert body["rewards"]["new_stations"] == []
    body = _save(app_client, today.isoformat(), [station])
    assert body["rewards"]["new_stations"] == [{
        "path": "עליית כוח", "icon": "🧗", "station": "עליות מתח בסיסיות", "next": "שכיבות סמיכה במקבילים",
    }]

    html = app_client.get("/workouts").text
    assert "is-conquered" in html
    assert "נכבש · <span class=\"wk-num\" dir=\"ltr\">6</span> אימונים" in html


def test_rows_saved_before_station_columns_still_count():
    # Newest first, like _fetch_history; names only — no skill_key on these rows
    history = [_session(f"2026-09-0{i}", [(MU_BASIC, 3, 30)]) for i in range(5, 0, -1)]
    paths = {p["key"]: p for p in workouts.compute_paths(history, level=1, today=date(2026, 9, 10))}
    mu = paths["muscle_up"]
    assert mu["stations"][0]["state"] == "conquered"
    assert mu["current"]["index"] == 1
    assert mu["stations"][2]["state"] == "next"
    assert mu["stations"][3]["state"] == "locked"
    assert mu["position"] == 2 and mu["stations_to_goal"] == mu["total"] - 2
    assert mu["last_ago"] == "לפני 5 ימים"
    # Plan: the station being conquered first, then the conquered one as volume
    assert [(e["stage_index"], e["sets"]) for e in mu["plan"]["exercises"]] == [(1, 4), (0, 3)]
    assert mu["plan"]["minutes"] == 30  # median of the recent sessions on this path
    assert mu["plan"]["xp"] == workouts._session_xp(7, 4 * 12 + 3 * 10, 30)
    # 5 sessions over ~1 week on this path → an ETA is shown
    assert mu["eta"]


def test_paths_lock_and_eta_rules():
    paths = {p["key"]: p for p in workouts.compute_paths([], level=1)}
    assert paths["planche"]["unlocked"] is False
    assert paths["human_flag"]["unlocked"] is False
    assert paths["muscle_up"]["unlocked"] is True
    assert all(p["eta"] is None for p in paths.values())  # no history → no estimate
    # Legacy flags unlock and conquer, even on a locked path
    paths = {p["key"]: p for p in workouts.compute_paths([], level=1, legacy_conquered={"planche": [0]})}
    assert paths["planche"]["unlocked"] is True
    assert paths["planche"]["stations"][0]["state"] == "conquered"


def test_personal_record_in_rewards(app_client, clean_workouts):
    earlier = (date.today() - timedelta(days=9)).isoformat()
    _save(app_client, earlier, [{"exercise_name": "Push-ups", "total_sets": 3, "total_reps": 33, "max_reps": 11}])
    # Matching the record isn't beating it
    same = _save(app_client, date.today().isoformat(),
                 [{"exercise_name": "Push-ups", "total_sets": 2, "total_reps": 22, "max_reps": 11}])
    assert same["rewards"]["new_records"] == []
    better = _save(app_client, date.today().isoformat(),
                   [{"exercise_name": "Push-ups", "total_sets": 3, "total_reps": 34, "max_reps": 12}], duration=31)
    assert better["rewards"]["new_records"] == [{
        "exercise_name": "Push-ups", "title": "שכיבות סמיכה", "reps": 12, "previous": 11,
        "previous_ago": "לפני 9 ימים",
    }]

    html = app_client.get("/workouts").text
    data = json.loads(html.split('id="workout-data">')[1].split("</script>")[0])
    assert data["records"]["Push-ups"] == {"best": 12, "last": 12}


def test_records_fall_back_to_average_set():
    history = [
        _session("2026-09-10", [("Dips", 3, 25)]),   # newest: avg 8
        _session("2026-09-01", [("Dips", 2, 20)]),   # avg 10
    ]
    records = workouts.compute_records(history)
    assert records["Dips"] == {"best": 10, "best_date": "2026-09-01", "last": 8}


def test_legacy_progress_import(app_client, clean_workouts):
    r = app_client.post("/workouts/legacy-progress", json={"progress": {
        "muscle_up": [0, 1, 99, -1],
        "not_a_skill": [0],
    }})
    assert r.status_code == 200
    assert r.json() == {"status": "success", "stations": 2}
    # Imports merge
    r = app_client.post("/workouts/legacy-progress", json={"progress": {"muscle_up": [1, 2]}})
    assert r.json()["stations"] == 3

    html = app_client.get("/workouts").text
    data = json.loads(html.split('id="workout-data">')[1].split("</script>")[0])
    assert data["first_workout"] is True  # imported flags aren't workouts


def test_streaks_week_and_ranks():
    today = date(2026, 9, 17)
    days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-16", "2026-09-17"]
    history = [_session(d, [("Dips", 1, 1)]) for d in days]
    game = workouts.compute_gamification(history, today)
    assert game["streak"] == 2
    assert game["current_streak"] == 2
    assert game["best_streak"] == 4
    assert [d["trained"] for d in game["week"]] == [False] * 5 + [True, True]
    assert game["week"][-1]["is_today"] is True
    assert game["week_count"] == 2
    states = [r["state"] for r in game["ranks"]]
    assert states[game["rank_position"] - 1] == "current"
    assert states.count("current") == 1 and states.count("next") == 1
    assert game["ranks"][0]["title"] == workouts.RANKS[0][1]

    stale = workouts.compute_gamification(history, date(2026, 9, 20))
    assert stale["current_streak"] == 0  # a streak that ended days ago isn't shown as live


def test_labels():
    assert workouts._ago_label(0) == "היום"
    assert workouts._ago_label(2) == "לפני יומיים"
    assert workouts._ago_label(9) == "לפני 9 ימים"
    assert workouts._ago_label(70) == "לפני חודשיים"
    assert workouts._eta_label(2) == "בערך שבועיים"
    assert workouts._eta_label(17) == "בערך 4 חודשים"
    assert workouts._rep_range(10) == (8, 10)
    assert workouts._rep_range(3) == (3, 3)


def test_exercise_form_data():
    form = workouts.exercise_form_data()
    assert form["Push-ups"]["tempo"] == [3, 1, 1]
    assert form["Push-ups"]["cues"][0] == {"pin": "גב ישר", "text": "קו ישר מהעורף לעקבים — בלי לשקוע באגן."}
    station = form["עליית כוח שלילית איטית (Negative Muscle-Up)"]
    assert station["holo_key"] == "negative_muscle_up"
    assert station["tempo"] == [5, 1, 1]
    skill_cues = workouts.SKILL_PROGRESSIONS["muscle_up"]["cues"][:2]
    assert [c["text"] for c in station["cues"]] == skill_cues
    assert form["פלאנץ' מלא (Full Planche Hold)"]["tempo"] is None  # static hold
    assert workouts.holo_key("Australian Pull-ups / Rows") == "australian_pull_ups_rows"


def _write_glb(path, clip_names):
    gltf = json.dumps({"asset": {"version": "2.0"},
                       "animations": [{"name": n, "channels": [], "samplers": []} for n in clip_names]}).encode()
    gltf += b" " * ((-len(gltf)) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 20 + len(gltf))
                     + struct.pack("<I4s", len(gltf), b"JSON") + gltf)


def test_holo_clips_read_from_model(tmp_path, monkeypatch, app_client, clean_workouts):
    # Other tests re-import the app package, so patch the module the /workouts route really uses
    page = next(r.endpoint for r in app_client.app.routes
                if getattr(r, "path", None) == "/workouts" and "GET" in getattr(r, "methods", ()))
    live = page.__globals__
    model = tmp_path / "exercises.glb"
    monkeypatch.setitem(live, "HOLO_MODEL_PATH", model)
    monkeypatch.setitem(live["_holo_clip_cache"], "stamp", None)
    monkeypatch.setitem(live["_holo_clip_cache"], "clips", frozenset())
    assert live["holo_clips"]() == frozenset()  # no file → plain arena

    _write_glb(model, ["push_ups", "dips"])
    assert live["holo_clips"]() == {"push_ups", "dips"}
    html = app_client.get("/workouts").text
    data = json.loads(html.split('id="workout-data">')[1].split("</script>")[0])
    assert data["holo"]["clips"] == ["dips", "push_ups"]
    assert data["holo"]["model"].startswith("/static/holo/exercises.glb?v=")

    model.write_bytes(b"not a model at all")
    assert live["holo_clips"]() == frozenset()  # unreadable → treated as absent
