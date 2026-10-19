# app/backend/app/db/__init__.py
"""
Database connection and initialization helpers.
This file is the single source of truth for opening the SQLite connection.
"""

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

from . import finance, renovation, wedding, workouts

# מיקום ברירת מחדל של מסד הנתונים (תעדכן אם שינית את השם/נתיב)
# ניתן לעקוף באמצעות משתנה סביבה BUDGET_DB_PATH כדי להריץ בדיקות על עותק זמני ובטוח
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "budget.db"
DB_PATH = Path(os.environ.get("BUDGET_DB_PATH", str(_DEFAULT_DB_PATH)))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(DB_PATH),
        check_same_thread=False,  # <— הוספה חשובה
    )
    conn.row_factory = sqlite3.Row
    # Enforce declared ON DELETE CASCADE rules (SQLite is off by default per-connection)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error:
        pass
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
    conn = get_connection()
    for module in (finance, wedding, renovation, workouts):
        module.ensure_schema(conn)
    conn.commit()
    conn.close()
