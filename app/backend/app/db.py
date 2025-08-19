"""Database utilities for the expense tracker.

This module encapsulates access to a SQLite database used by the
expense tracker. It provides functions to initialise the schema,
seed default values (such as two demo users and some example
categories) and obtain new database connections. It avoids
introducing external dependencies like SQLAlchemy by using
Python's built‑in `sqlite3` module.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterator, Any, Iterable, Tuple, Optional


# Path to the directory containing this file (app/backend/app)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Path to the SQLite database file
DB_PATH = DATA_DIR / "budget.db"


def get_connection() -> sqlite3.Connection:
    """Return a new connection to the database.

    The `sqlite3` module defaults to returning rows as tuples. To
    access columns by name, row_factory is set to `sqlite3.Row`.
    The connection is created with `check_same_thread=False` to
    allow usage across threads or in asynchronous contexts. Each
    caller should ensure the connection is closed after use.
    """
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


def initialise_schema(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not already exist.

    Parameters
    ----------
    conn : sqlite3.Connection
        An open connection on which to execute the schema creation.
    """
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
    """Insert initial default data for users, categories and accounts.

    If the database already contains users or categories, this
    function will not duplicate them. Only missing defaults are
    inserted. Two demonstration users are added with IDs 1 and
    2; a set of common categories and a couple of payment
    accounts are also inserted.
    """
    # Insert default users if none exist
    users = list(conn.execute("SELECT id FROM users").fetchall())
    if not users:
        conn.executemany(
            "INSERT INTO users (id, name, is_active) VALUES (?, ?, 1)",
            [
                (1, "User 1"),
                (2, "User 2"),
            ],
        )

    # Insert default categories
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

    # Insert default accounts
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
    """Initialise the database if necessary.

    This convenience function opens a connection, creates the
    required schema and inserts default records. It should be
    called once at application startup. It does nothing if the
    database already exists with the correct schema.
    """
    with get_connection() as conn:
        initialise_schema(conn)
        seed_defaults(conn)


def iter_query(conn: sqlite3.Connection, query: str, params: Tuple[Any, ...] = ()) -> Iterator[sqlite3.Row]:
    """Yield rows from a SELECT query.

    Parameters
    ----------
    conn : sqlite3.Connection
        A connection object.
    query : str
        The SELECT statement to execute.
    params : tuple
        Parameters to bind to the query.

    Returns
    -------
    Iterator[sqlite3.Row]
        An iterator over rows, each of which can be indexed by
        column name.
    """
    cur = conn.execute(query, params)
    try:
        for row in cur:
            yield row
    finally:
        cur.close()


def execute(conn: sqlite3.Connection, query: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
    """Execute a single statement.

    This helper runs a statement such as INSERT, UPDATE or
    DELETE and commits immediately. It returns the cursor for
    introspection (e.g. `lastrowid`).
    """
    cur = conn.execute(query, params)
    conn.commit()
    return cur


def fetchone(conn: sqlite3.Connection, query: str, params: Tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
    """Fetch a single row from a query or return None if no rows."""
    cur = conn.execute(query, params)
    row = cur.fetchone()
    cur.close()
    return row