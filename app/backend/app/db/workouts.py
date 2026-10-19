"""The arena's schema: workouts, spanish_reviews (Spanish between sets) and push_subscriptions
(קריאה לזירה). The three tables live together on purpose: all three belong to the workouts arena."""

import sqlite3


def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Workouts Tracker Table
    cur.execute("""
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
    # Migration: the quest station an exercise row trained (skill_key + stage_index, counted to
    # conquer stations) and its best single set (max_reps, read for personal records).
    try:
        workout_cols = [r[1] for r in cur.execute("PRAGMA table_info('workouts')").fetchall()]
        for col, typedef in [("skill_key", "TEXT"), ("stage_index", "INTEGER"), ("max_reps", "INTEGER")]:
            if col not in workout_cols:
                conn.execute(f"ALTER TABLE workouts ADD COLUMN {col} {typedef}")
        conn.commit()
    except Exception:
        pass

    # Spanish between sets: one row per graded card. Stage, due date, "words in your pocket"
    # and streaks are replayed from these rows at read time (services/spanish.py), never stored.
    # item_id references an id in static/spanish/deck.json (a file, not a table).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS spanish_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            grade INTEGER NOT NULL,
            mode TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT 'rest',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_spanish_reviews_user_item ON spanish_reviews (user_id, item_id)"
    )

    # קריאה לזירה: one Web Push subscription per device (services/push_service.py).
    # The texts are derived at send time; only the browser's endpoint + keys are kept.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
