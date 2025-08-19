from __future__ import annotations

# Copied from original location app/backend/app/db.py with minimal changes

import sqlite3
from pathlib import Path
from typing import Iterator, Any, Tuple, Optional


BASE_DIR = Path(__file__).resolve().parents[2] / "app"
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "budget.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


def initialise_schema(conn: sqlite3.Connection) -> None:
    schema_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        type TEXT CHECK(type IN ('expense','income')) DEFAULT 'expense',
        color TEXT
    );

    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS recurrences (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        amount REAL NOT NULL,
        category_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT,
        frequency TEXT NOT NULL,
        day_of_month INTEGER,
        weekday INTEGER,
        custom_cron TEXT,
        account_id INTEGER,
        active INTEGER DEFAULT 1,
        FOREIGN KEY (category_id) REFERENCES categories(id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (account_id) REFERENCES accounts(id)
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY,
        date TEXT NOT NULL,
        amount REAL NOT NULL,
        category_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        account_id INTEGER,
        notes TEXT,
        tags TEXT,
        recurrence_id INTEGER,
        period_key TEXT,
        FOREIGN KEY (category_id) REFERENCES categories(id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (account_id) REFERENCES accounts(id),
        FOREIGN KEY (recurrence_id) REFERENCES recurrences(id)
    );

    CREATE UNIQUE INDEX IF NOT EXISTS uniq_rec_period
        ON transactions (recurrence_id, period_key);

    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """
    conn.executescript(schema_sql)
    conn.commit()


def seed_defaults(conn: sqlite3.Connection) -> None:
    users = list(conn.execute("SELECT id FROM users").fetchall())
    if not users:
        conn.executemany(
            "INSERT INTO users (id, name, is_active) VALUES (?, ?, 1)",
            [
                (1, "User 1"),
                (2, "User 2"),
            ],
        )

    categories = [row[0] for row in conn.execute("SELECT name FROM categories").fetchall()]
    default_categories = [
        ("Food", "expense", "#F87171"),
        ("Housing", "expense", "#60A5FA"),
        ("Transport", "expense", "#FBBF24"),
        ("Entertainment", "expense", "#34D399"),
        ("Salary", "income", "#A78BFA"),
    ]
    for name, typ, color in default_categories:
        if name not in categories:
            conn.execute(
                "INSERT INTO categories (name, type, color) VALUES (?, ?, ?)",
                (name, typ, color),
            )

    accounts = [row[0] for row in conn.execute("SELECT name FROM accounts").fetchall()]
    default_accounts = ["Cash", "Credit Card"]
    for name in default_accounts:
        if name not in accounts:
            conn.execute(
                "INSERT INTO accounts (name) VALUES (?)",
                (name,),
            )
    conn.commit()


def initialise_database() -> None:
    with get_connection() as conn:
        initialise_schema(conn)
        seed_defaults(conn)


def execute(conn: sqlite3.Connection, query: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
    cur = conn.execute(query, params)
    conn.commit()
    return cur


def fetchone(conn: sqlite3.Connection, query: str, params: Tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
    cur = conn.execute(query, params)
    row = cur.fetchone()
    cur.close()
    return row

