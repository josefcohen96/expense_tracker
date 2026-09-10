from datetime import date

def test_workout_page_loads(app_client):
    """Test that the workouts page loads correctly."""
    r = app_client.get("/workouts")
    assert r.status_code == 200
    assert "היסטוריה" in r.text
    assert "מסע מיומנויות" in r.text
    assert "exercise-modal" in r.text
    # Gamification UI elements
    assert "player-level" in r.text
    assert "session-score" in r.text
    assert "victory-modal" in r.text
    assert "tab-achievements" in r.text

def test_save_workout_success(app_client, db_conn):
    """Test that saving a workout aggregates exercise info and stores it in SQLite."""
    # Ensure tables exist
    db_conn.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            workout_type TEXT NOT NULL,
            total_duration INTEGER NOT NULL,
            exercise_name TEXT NOT NULL,
            total_sets INTEGER NOT NULL,
            total_reps INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    db_conn.commit()

    test_date = "2026-06-13"
    payload = {
        "date": test_date,
        "workout_type": "Calisthenics",
        "total_duration": 45,
        "exercises": [
            {
                "exercise_name": "Pull-ups",
                "total_sets": 3,
                "total_reps": 30
            },
            {
                "exercise_name": "Dips",
                "total_sets": 2,
                "total_reps": 24
            }
        ]
    }
    
    r = app_client.post("/workouts", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["message"] == "Workout saved successfully!"

    # Gamification rewards: 5 sets, 54 reps, 45 minutes
    # XP = 50 (base) + 5*10 (sets) + 54 (reps) + 45*2 (minutes) = 244
    rewards = body["rewards"]
    assert rewards["xp_gained"] == 244
    assert rewards["new_level"] >= rewards["old_level"]
    assert rewards["total_xp"] >= rewards["xp_gained"]
    assert "rank" in rewards and "title" in rewards["rank"]
    assert isinstance(rewards["new_achievements"], list)
    assert 0 <= rewards["progress_pct"] <= 100

    # Verify rows in database
    rows = db_conn.execute(
        "SELECT exercise_name, total_sets, total_reps FROM workouts WHERE date = ? ORDER BY exercise_name",
        (test_date,)
    ).fetchall()
    
    assert len(rows) == 2
    assert rows[0]["exercise_name"] == "Dips"
    assert rows[0]["total_sets"] == 2
    assert rows[0]["total_reps"] == 24

    assert rows[1]["exercise_name"] == "Pull-ups"
    assert rows[1]["total_sets"] == 3
    assert rows[1]["total_reps"] == 30

    # Cleanup the test workout rows
    db_conn.execute("DELETE FROM workouts WHERE date = ?", (test_date,))
    db_conn.commit()
