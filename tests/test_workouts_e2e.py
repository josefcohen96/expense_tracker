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
    assert "push_ups" in data["holo"]["clips"]  # the shipped model drives the hologram
    assert "full_human_flag_hold" in data["holo"]["front"]
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
    assert rewards["station_progress"] == []  # no station trained
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
    # Below the rep range (avg 5 < 8) — trained, but doesn't count, and the reward says so
    body = _save(app_client, (today - timedelta(days=10)).isoformat(),
                 [{**station, "total_reps": 15, "max_reps": 5}])
    assert body["rewards"]["station_progress"] == [{
        "path": "עליית כוח", "icon": "🧗", "station": "עליות מתח בסיסיות", "unit_label": "חזרות",
        "average": 5, "floor": 8, "target": 10, "counted": False,
        "in_range": 0, "to_conquer": 5, "conquered": False,
    }]
    for i in range(4):
        body = _save(app_client, (today - timedelta(days=8 - i)).isoformat(), [station])
        assert body["rewards"]["new_stations"] == []
        verdict, = body["rewards"]["station_progress"]
        assert (verdict["counted"], verdict["in_range"], verdict["conquered"]) == (True, i + 1, False)
    body = _save(app_client, today.isoformat(), [station])
    assert body["rewards"]["new_stations"] == [{
        "path": "עליית כוח", "icon": "🧗", "station": "עליות מתח בסיסיות", "next": "מקבילים",
    }]
    verdict, = body["rewards"]["station_progress"]
    assert (verdict["counted"], verdict["in_range"], verdict["conquered"]) == (True, 5, True)

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


def test_long_streak_details():
    today = date(2026, 9, 24)
    days = [(today - timedelta(days=n)).isoformat() for n in range(17)]  # 17 days ending today
    game = workouts.compute_gamification([_session(d, [("Dips", 1, 1)]) for d in days], today)
    assert game["current_streak"] == 17
    assert (game["streak_weeks"], game["streak_extra_days"]) == (2, 3)
    assert game["streak_milestone"] == {"target": 21, "remaining": 4, "pct": 43}
    assert game["streak_is_best"] is True
    assert game["streak_at_risk"] is False
    assert len(game["streak_grid"]) == 4 and all(len(row) == 7 for row in game["streak_grid"])
    assert game["streak_grid"][-1][-1]["is_today"] is True
    assert game["streak_grid_count"] == 17
    assert [d["trained"] for d in game["streak_grid"][1]] == [False] * 4 + [True] * 3  # run starts mid-row

    # Trained through yesterday only: the run is alive but today's workout keeps it
    risky = workouts.compute_gamification([_session(d, [("Dips", 1, 1)]) for d in days[1:]], today)
    assert risky["current_streak"] == 16 and risky["streak_at_risk"] is True

    # Past the last milestone there is no goal bar
    far = workouts.compute_gamification(
        [_session((today - timedelta(days=n)).isoformat(), [("Dips", 1, 1)]) for n in range(400)], today
    )
    assert far["streak_milestone"] is None


def test_long_streak_card_html(app_client, clean_workouts):
    for n in range(10):
        _save(app_client, (date.today() - timedelta(days=n)).isoformat(), [{"exercise_name": "Dips", "total_sets": 1, "total_reps": 1}])
    html = app_client.get("/workouts").text
    assert "wk-streak is-long" in html
    assert "שבוע ו-" in html and "wk-weeks" in html and "wk-streak-bar" in html
    assert 'ל-<span class="wk-num" dir="ltr">14</span>' in html


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
    assert station["unit_label"] == "חזרות"
    # A station carries its own cues and its own "how it is done" line, not the path's
    step = next(s for s in workouts.SKILL_PROGRESSIONS["muscle_up"]["progressions"]
                if s["name"] == "Negative Muscle-Up")
    assert station["cues"] == step["cues"] and station["how"] == step["how"]
    assert form["פלאנץ' מלא (Full Planche Hold)"]["tempo"] is None  # static hold
    assert workouts.holo_key("Australian Pull-ups / Rows") == "australian_pull_ups_rows"


def test_holds_are_counted_in_seconds():
    """A hold's target is seconds, and it says so everywhere it is shown."""
    hold = workouts.exercise_form_data()["סמיכה קדמית מלאה (Full Front Lever Hold)"]
    assert hold["unit"] == "sec" and hold["unit_label"] == "שניות" and hold["tempo"] is None

    paths = {p["key"]: p for p in workouts.compute_paths([], level=1)}
    stations = {st["name"]: st for st in paths["front_lever"]["stations"]}
    assert stations["Full Front Lever Hold"]["unit_label"] == "שניות"
    assert stations["Hanging Leg Raises"]["unit_label"] == "חזרות"
    # The time estimate uses the hold itself as the work time
    assert all("unit_label" in ex for ex in paths["front_lever"]["plan"]["exercises"])


def test_every_station_is_documented():
    for skill_key, skill in workouts.SKILL_PROGRESSIONS.items():
        assert skill["prereq"], skill_key
        for step in skill["progressions"]:
            where = f"{skill_key}/{step['name']}"
            assert step["unit"] in ("reps", "sec"), where
            assert step["how"].endswith("."), where
            assert len(step["cues"]) == 2, where
            assert all(c["pin"] and c["text"] for c in step["cues"]), where


def test_stations_follow_the_accepted_order():
    """An easier lever always comes before a longer one on the same path."""
    def order(skill_key):
        return [s["name"] for s in workouts.SKILL_PROGRESSIONS[skill_key]["progressions"]]

    fl = order("front_lever")
    assert fl.index("Tuck Front Lever Hold") < fl.index("Advanced Tuck FL Hold") \
        < fl.index("One-Legged FL Hold") < fl.index("Straddle Front Lever Hold") \
        < fl.index("Half Lay Front Lever Hold") < fl.index("Full Front Lever Hold")

    pl = order("planche")
    assert pl.index("Tuck Planche Hold") < pl.index("Advanced Tuck Planche") \
        < pl.index("One-Legged Advanced Tuck") < pl.index("Straddle Planche Hold") \
        < pl.index("Full Planche Hold")

    # The false grip the muscle-up cues talk about is trained before it is needed
    mu = order("muscle_up")
    assert mu.index("False Grip Hang") < mu.index("False Grip Pull-ups") < mu.index("Full Muscle-Up")

    # A freestanding handstand is a prerequisite of a freestanding press, not a surprise
    hs = order("hspu")
    assert hs.index("Wall-Assisted HSPU") < hs.index("Freestanding Handstand Hold") \
        < hs.index("Straddle Freestanding HSPU")

    # The flag starts vertical (feet up) and works down towards horizontal
    hf = order("human_flag")
    assert hf.index("Vertical Flag Hold") < hf.index("Angled Tucked Flag Hold") \
        < hf.index("Tuck Human Flag Hold") < hf.index("One-Legged Human Flag Hold") \
        < hf.index("Straddle Human Flag Hold") < hf.index("Full Human Flag Hold")

    # The nordic curl is earned from the back up: bridges, then the hinge on the knees, and
    # the eccentric before the full rep
    nc = order("nordic_curl")
    assert nc.index("Glute Bridge") < nc.index("Single-Leg Glute Bridge") < nc.index("Sliding Leg Curl")         < nc.index("Nordic Curl Hold") < nc.index("Nordic Negatives") < nc.index("Partial Nordic Curl")         < nc.index("Nordic Hamstring Curls")


def test_rows_survive_a_reordered_path():
    """The saved name identifies the station, so a stale index never credits the wrong one."""
    # Renamed station: the row still carries the name it was saved under
    old_name = "עמידת ידיים נתמכת קיר (החזקה) (Wall-Assisted Handstand Hold)"
    assert workouts._station_for("hspu", 0, old_name) == ("hspu", 0)
    # A name that moved: the name wins over the index stored beside it
    moved = "הרמות רגליים ישרות למוט (Hanging Leg Raises)"
    assert workouts._station_for("front_lever", 3, moved) == ("front_lever", 1)
    # An exercise that is not a station at all keeps its stored index
    assert workouts._station_for("front_lever", 2, "Dips") == ("front_lever", 2)
    assert workouts._station_for(None, None, "Dips") is None


def test_legacy_flags_are_read_in_the_order_they_were_written(app_client, clean_workouts):
    """Imported "כבשתי!" flags are stored in the old numbering and translated on the way out."""
    # Old human_flag order: 3 = the vertical flag, 2 = the low flag (no longer a station)
    r = app_client.post("/workouts/legacy-progress", json={"progress": {"human_flag": [2, 3]}})
    assert r.json() == {"status": "success", "stations": 2}

    paths = {p["key"]: p for p in workouts.compute_paths(
        [], level=1, legacy_conquered=workouts._legacy_to_current({"human_flag": [2, 3]}))}
    stations = paths["human_flag"]["stations"]
    assert stations[workouts.STATION_INDEX[("human_flag", "דגל אנכי (רגליים למעלה) (Vertical Flag Hold)")]]["conquered"]
    assert sum(1 for st in stations if st["conquered"]) == 1  # the dropped low flag brings nothing


def test_shipped_model_asks_for_the_front_camera_on_flags():
    """A human flag is edge-on from the side, so the model names the clips that read from the front."""
    front = workouts.holo_front_clips()
    assert "full_human_flag_hold" in front
    assert "push_ups" not in front
    assert front <= workouts.holo_clips()


def test_shipped_model_covers_every_exercise():
    """The model in static/holo has one clip per exercise the arena can show."""
    clips = workouts.holo_clips()
    assert clips, f"missing hologram model at {workouts.HOLO_MODEL_PATH}"
    wanted = {form["holo_key"] for form in workouts.exercise_form_data().values()}
    missing = sorted(wanted - clips)
    assert not missing, f"re-run tools/build_exercises_glb.py — no clip for: {missing}"
    # ...and says where each clip lives, so the arena can frame a bar clip as well as a floor one
    bounds = workouts.holo_clip_bounds()
    assert not sorted(clips - set(bounds)), "clip_bounds missing from the model's extras"
    assert bounds["pull_ups"][4] > bounds["push_ups"][4]  # a hanging clip is the taller box


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


# ====================== holds, warm-up, recovery-aware mission ======================

FL_TUCK = "סמיכה קדמית מקופלת (Tuck Front Lever Hold)"  # front_lever station 2, 15 seconds


def test_exercise_units_reach_the_arena():
    """Hold stations carry unit 'sec' all the way to the arena's form data; rep stations stay 'reps'."""
    form = workouts.exercise_form_data()
    assert form[FL_TUCK]["unit"] == "sec" and form[FL_TUCK]["unit_label"] == "שניות"
    assert form[MU_BASIC]["unit"] == "reps" and form[MU_BASIC]["unit_label"] == "חזרות"
    assert form["Plank"]["unit"] == "sec"
    assert form["Push-ups"]["unit"] == "reps"


def test_every_path_has_a_warmup():
    for key in workouts.SKILL_PROGRESSIONS:
        items = workouts.WARMUPS[key]
        assert 4 <= len(items) <= 6
        assert all(item["title"] and item["detail"] for item in items)
    paths = workouts.compute_paths([], level=1)
    assert all(p["warmup"] == workouts.WARMUPS[p["key"]] for p in paths)
    assert all(p["warmup_minutes"] == workouts.WARMUP_MINUTES for p in paths)
    # Station and plan rows carry their unit so the arena can run a hold timer
    fl = next(p for p in paths if p["key"] == "front_lever")
    assert fl["stations"][0]["unit"] == "reps" and fl["stations"][2]["unit"] == "sec"
    assert fl["stations"][2]["unit_label"] == "שניות"
    assert fl["plan"]["exercises"][0]["unit"] == "reps"


def test_plan_today_switches_muscle_group_after_yesterday():
    today = date(2026, 9, 20)
    yesterday = (today - timedelta(days=1)).isoformat()
    history = [_session(yesterday, [(MU_BASIC, 4, 40)])]  # a pull day
    paths = workouts.compute_paths(history, level=1, today=today)
    key, note = workouts.plan_today(paths, history, today)
    assert key == "hspu"  # the easiest push path, not the pull path trained yesterday
    assert note == "אתמול היה יום משיכה — היום דחיפה, השרירים של אתמול נחים."

    # A push path already trained wins over an untrained one
    hspu_station = "עמידת ידיים לקיר (החזקה) (Wall-Assisted Handstand Hold)"
    history2 = [_session(yesterday, [(MU_BASIC, 4, 40)]),
                _session((today - timedelta(days=3)).isoformat(), [(hspu_station, 4, 120)])]
    history2[1]["workout_type"] = "Push"
    paths2 = workouts.compute_paths(history2, level=1, today=today)
    assert workouts.plan_today(paths2, history2, today)[0] == "hspu"


def test_plan_today_keeps_path_when_rested_or_already_trained_today():
    today = date(2026, 9, 20)
    rested = [_session((today - timedelta(days=2)).isoformat(), [(MU_BASIC, 4, 40)])]
    paths = workouts.compute_paths(rested, level=1, today=today)
    assert workouts.plan_today(paths, rested, today) == ("muscle_up", None)

    trained_today = [_session(today.isoformat(), [(MU_BASIC, 4, 40)])]
    paths = workouts.compute_paths(trained_today, level=1, today=today)
    assert workouts.plan_today(paths, trained_today, today) == ("muscle_up", None)

    # No history at all → first unlocked path, no note
    paths = workouts.compute_paths([], level=1, today=today)
    assert workouts.plan_today(paths, [], today) == ("muscle_up", None)


def test_plan_today_rest_day_nudge_after_a_streak():
    today = date(2026, 9, 20)
    history = [_session((today - timedelta(days=d)).isoformat(), [(MU_BASIC, 4, 40)]) for d in (1, 2, 3)]
    paths = workouts.compute_paths(history, level=1, today=today)
    key, note = workouts.plan_today(paths, history, today)
    assert key == "hspu"
    assert note.startswith("3 ימים ברצף")


def test_page_shows_units_note_and_warmup(app_client, clean_workouts):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _save(app_client, yesterday, [
        {"exercise_name": FL_TUCK, "total_sets": 4, "total_reps": 60, "max_reps": 15,
         "skill_key": "front_lever", "stage_index": 2},
    ])
    html = app_client.get("/workouts").text
    # History and map rows say seconds for the hold station
    assert "4 סטים · 60 שניות" in html.replace('<span class="wk-num" dir="ltr">', "").replace("</span>", "")
    assert "12–15 שניות" in html  # station list: the hold's range in seconds
    # The mission moved to a push path with a recovery note
    assert "wk-mission-note" in html
    assert "אתמול היה יום משיכה — היום דחיפה" in html
    # Warm-up phase and the plain-arena form guide are on the page
    for marker in ('data-phase-panel="warmup"', 'id="warmup-list"', 'id="arena-hold-btn"',
                   'id="arena-cues"', 'id="arena-tempo"'):
        assert marker in html
    data = json.loads(html.split('id="workout-data">')[1].split("</script>")[0])
    assert data["default_path"] == "hspu"
    assert data["paths"]["hspu"]["warmup"] == workouts.WARMUPS["hspu"]
    assert data["stations"]["front_lever"][2]["unit"] == "sec"
    assert data["form"][FL_TUCK]["unit"] == "sec"
