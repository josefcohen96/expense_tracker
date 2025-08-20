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
    FastAPI dependency: yields a sqlite3.Connection and closes it afterwards.
    """
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def initialise_database() -> None:
    """
    Ensure all tables exist. Run this once at app startup.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category_id INTEGER,
            user_id INTEGER,
            account_id INTEGER,
            notes TEXT,
            tags TEXT,
            recurrence_id INTEGER,
            period_key TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            category_id INTEGER,
            user_id INTEGER,
            account_id INTEGER,
            start_date TEXT NOT NULL,
            end_date TEXT,
            frequency TEXT NOT NULL,
            day_of_month INTEGER,
            weekday INTEGER,
            active INTEGER DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)



        # הוספת קטגוריות ברירת מחדל
            # Insert default data only if tables are empty
        user_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            cursor.execute("INSERT OR IGNORE INTO users (id, name) VALUES (1, 'YOSEF')")
            cursor.execute("INSERT OR IGNORE INTO users (id, name) VALUES (2, 'KARINA')")
        
        category_count = cursor.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if category_count == 0:
            default_categories = ["אוכל", "קניות", "חברים", "בילויים", "תחבורה", "חשמל", "מים", "שכירות"]
            for cat in default_categories:
                cursor.execute(
                "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                (cat,)
            )
            
        account_count = cursor.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        if account_count == 0:
            default_payments = ["מזומן", "אשראי"]
            for payment in default_payments:
                cursor.execute(
                "INSERT OR IGNORE INTO accounts (name) VALUES (?)",
                (payment,)
            )

        conn.commit()
    finally:
        conn.close()
