# app/backend/app/db.py
"""
Database connection and initialization helpers.
This file is the single source of truth for opening the SQLite connection.
"""

import sqlite3
from pathlib import Path
from typing import Generator

# מיקום ברירת מחדל של מסד הנתונים (תעדכן אם שינית את השם/נתיב)
DB_PATH = Path(__file__).resolve().parent / "data" / "couplebudget.sqlite3"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,  # <— הוספה חשובה
    )
    conn.row_factory = sqlite3.Row
    return conn


def get_db_conn() -> Generator[sqlite3.Connection, None, None]:
    """
    Dependency for FastAPI to get database connection.
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_db_path() -> str:
    """Get the database file path."""
    return str(DB_PATH)


def initialise_database() -> None:
    """Create database tables if they don't exist."""
    conn = get_connection()
    cur = conn.cursor()

    # Create tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            account_id INTEGER,
            notes TEXT,
            tags TEXT,
            recurrence_id INTEGER,
            period_key TEXT,
            FOREIGN KEY (category_id) REFERENCES categories (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (account_id) REFERENCES accounts (id),
            FOREIGN KEY (recurrence_id) REFERENCES recurrences (id),
            UNIQUE (recurrence_id, period_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            category_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            frequency TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            day_of_month INTEGER,
            weekday INTEGER,
            active BOOLEAN DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES categories (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # Challenges tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            target_value REAL NOT NULL,
            target_period TEXT NOT NULL, -- 'week', 'month', 'year'
            points INTEGER NOT NULL DEFAULT 10,
            difficulty TEXT NOT NULL DEFAULT 'bronze', -- 'bronze', 'silver', 'gold', 'platinum', 'master'
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL,
            current_progress REAL DEFAULT 0,
            target_value REAL NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT DEFAULT 'active', -- 'active', 'completed', 'failed'
            completed_at TEXT,
            points_earned INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (challenge_id) REFERENCES challenges (id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS challenge_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_challenge_id INTEGER NOT NULL,
            progress_date TEXT NOT NULL,
            progress_value REAL NOT NULL,
            notes TEXT,
            FOREIGN KEY (user_challenge_id) REFERENCES user_challenges (id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_points INTEGER DEFAULT 0,
            current_level TEXT DEFAULT 'bronze',
            level_progress INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # System settings table for tracking CRON jobs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert default data if tables are empty
    if not cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0]:
        cur.execute("INSERT INTO categories (name) VALUES ('מזון')")
        cur.execute("INSERT INTO categories (name) VALUES ('תחבורה')")
        cur.execute("INSERT INTO categories (name) VALUES ('בילויים')")
        cur.execute("INSERT INTO categories (name) VALUES ('קניות')")
        cur.execute("INSERT INTO categories (name) VALUES ('חשבונות')")

    if not cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        cur.execute("INSERT INTO users (name) VALUES ('משתמש 1')")
        cur.execute("INSERT INTO users (name) VALUES ('משתמש 2')")

    if not cur.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
        cur.execute("INSERT INTO accounts (name) VALUES ('חשבון עו\"ש')")
        cur.execute("INSERT INTO accounts (name) VALUES ('כרטיס אשראי')")

    # Insert default challenges
    if not cur.execute("SELECT COUNT(*) FROM challenges").fetchone()[0]:
        # שבוע בלי להזמין אוכל מבחוץ
        cur.execute("""
            INSERT INTO challenges (name, description, category, target_value, target_period, points, difficulty)
            VALUES ('שבוע נקי', 'שבוע שלם בלי להזמין אוכל מבחוץ', 'expertise', 0, 'week', 25, 'bronze')
        """)
        
        # חודש בלי להזמין אוכל מבחוץ
        cur.execute("""
            INSERT INTO challenges (name, description, category, target_value, target_period, points, difficulty)
            VALUES ('חודש נקי', 'חודש שלם בלי להזמין אוכל מבחוץ', 'veterancy', 0, 'month', 50, 'silver')
        """)
        
        # חודש עם הוצאות קטנות מ-7000
        cur.execute("""
            INSERT INTO challenges (name, description, category, target_value, target_period, points, difficulty)
            VALUES ('חוסך מתחיל', 'הוצאות חודשיות מתחת ל-7000 ₪', 'expertise', 7000, 'month', 35, 'bronze')
        """)

    conn.commit()
    conn.close()
