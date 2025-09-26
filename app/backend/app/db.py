# app/backend/app/db.py
"""
Database connection and initialization helpers.
This file is the single source of truth for opening the SQLite connection.
"""

import sqlite3
import os
from pathlib import Path
from typing import Generator
from datetime import date, timedelta

# מיקום ברירת מחדל של מסד הנתונים (תעדכן אם שינית את השם/נתיב)
# ניתן לעקוף באמצעות משתנה סביבה BUDGET_DB_PATH כדי להריץ בדיקות על עותק זמני ובטוח
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "budget.db"
DB_PATH = Path(os.environ.get("BUDGET_DB_PATH", str(_DEFAULT_DB_PATH)))


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

def _reset_database_if_requested() -> None:
    """
    אם FORCE_DB_RESET=1 – מוחק את קובץ ה-DB (אם קיים),
    וכדי להיות עמיד גם במקרה של Volume נעשה גם ניסיון Drop לכל הטבלאות.
    לקרוא לפונקציה הזו בתחילת initialise_database().
    """
    flag = os.environ.get("FORCE_DB_RESET", "").strip()
    if flag != "1":
        return

    # 1) מחיקת הקובץ (הדרך הנקייה ביותר לאתחול מלא)
    try:
        if DB_PATH.exists():
            DB_PATH.unlink()
            return  # אין צורך ב-DROP כשמחקנו קובץ
    except Exception:
        # אם לא הצלחנו למחוק קובץ (למשל על Volume), נמשיך ל-DROP
        pass

    # 2) אתחול בקונקציה וקיפול יחסי זרים, ואז DROP לכל הטבלאות (סדר: ילדים -> הורים)
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("PRAGMA foreign_keys = OFF;")
        for tbl in [
            "transactions",
            "recurrence_skips",
            "recurrences",
            "accounts",
            "users",
            "categories",
            "system_settings",
        ]:
            try:
                cur.execute(f"DROP TABLE IF EXISTS {tbl}")
            except sqlite3.Error:
                pass
        conn.commit()
    finally:
        conn.close()

def initialise_database() -> None:
    """Create database tables if they don't exist."""
    _reset_database_if_requested()
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
            day_of_month INTEGER,
            weekday INTEGER,
            next_charge_date TEXT NOT NULL,
            active BOOLEAN DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES categories (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # Track skipped recurring occurrences so they won't be recreated
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recurrence_skips (
            recurrence_id INTEGER NOT NULL,
            period_key TEXT NOT NULL,
            skipped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (recurrence_id, period_key),
            FOREIGN KEY (recurrence_id) REFERENCES recurrences (id)
        )
    """)

    # (removed) challenges-related tables

    # System settings table for tracking CRON jobs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- Migrations ---
    # 1) Ensure recurrences table has next_charge_date. If missing (legacy schema), add and populate.
    try:
        cols = [r[1] for r in cur.execute("PRAGMA table_info('recurrences')").fetchall()]
        if "next_charge_date" not in cols:
            cur.execute("ALTER TABLE recurrences ADD COLUMN next_charge_date TEXT")
            # Populate next_charge_date for existing rows based on frequency/day_of_month/weekday and today
            today = date.today()

            def clamp_day(year: int, month: int, day: int) -> str:
                import calendar
                last = calendar.monthrange(year, month)[1]
                if day < 1:
                    day = 1
                if day > last:
                    day = last
                return f"{year:04d}-{month:02d}-{day:02d}"

            rows = cur.execute("SELECT id, frequency, day_of_month, weekday, start_date FROM recurrences").fetchall()
            for r in rows:
                freq = r[1]
                dom = r[2]
                wday = r[3]
                start_date_val = r[4]
                next_date = None

                if freq == "monthly":
                    day = int(dom) if dom is not None else 1
                    y, m = today.year, today.month
                    tentative = clamp_day(y, m, day)
                    if tentative < today.isoformat():
                        # move to next month
                        if m == 12:
                            y, m = y + 1, 1
                        else:
                            m += 1
                        tentative = clamp_day(y, m, day)
                    next_date = tentative
                elif freq == "weekly":
                    # Python Monday=0..Sunday=6, default Sunday
                    target = int(wday) if wday is not None else 6
                    # compute days until target weekday
                    delta = (target - today.weekday()) % 7
                    if delta == 0:
                        # today or next week? assume today
                        next_dt = today
                    else:
                        next_dt = today + timedelta(days=delta)
                    next_date = next_dt.isoformat()
                elif freq == "yearly":
                    # Use start_date if exists; otherwise default Aug 1st
                    if start_date_val:
                        try:
                            mm = int(start_date_val.split("-")[1])
                            dd = int(start_date_val.split("-")[2])
                        except Exception:
                            mm, dd = 8, 1
                    else:
                        mm, dd = 8, 1
                    y = today.year
                    candidate = f"{y:04d}-{mm:02d}-{dd:02d}"
                    if candidate < today.isoformat():
                        candidate = f"{y+1:04d}-{mm:02d}-{dd:02d}"
                    next_date = candidate
                else:
                    # Fallback: schedule for tomorrow
                    next_date = (today + timedelta(days=1)).isoformat()

                cur.execute(
                    "UPDATE recurrences SET next_charge_date = ? WHERE id = ?",
                    (next_date, r[0]),
                )
        # 2) Ensure recurrences has account_id column (nullable FK)
        cols = [r[1] for r in cur.execute("PRAGMA table_info('recurrences')").fetchall()]
        if "account_id" not in cols:
            cur.execute("ALTER TABLE recurrences ADD COLUMN account_id INTEGER")
    except Exception:
        # Migration best-effort; do not fail app startup
        pass

    # Insert default data if tables are empty
    if not cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0]:
        for _cat in ("משכורת", "קליניקה", "בריאות", "חסכונות", "פנאי", "הוצאות בית", "רכב", "תחבורה"):
            cur.execute("INSERT INTO categories (name) VALUES (?)", (_cat,))

    if not cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        # Seed only the real users
        cur.execute("INSERT INTO users (name) VALUES ('יוסף')")
        cur.execute("INSERT INTO users (name) VALUES ('קארינה')")

    if not cur.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
        cur.execute("INSERT INTO accounts (name) VALUES ('מזומן')")
        cur.execute("INSERT INTO accounts (name) VALUES ('כרטיס אשראי')")



    # (removed) default challenges seed

    conn.commit()
    conn.close()
