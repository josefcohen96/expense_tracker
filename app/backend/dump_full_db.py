#!/usr/bin/env python3
"""
Dump full database contents and human-friendly joined views.

Usage examples:
  python app/backend/dump_full_db.py
  python app/backend/dump_full_db.py --db C:/path/to/budget.db

Notes:
  - By default the script looks for the DB at:
      1) --db path if provided
      2) BUDGET_DB_PATH env var
      3) app/backend/app/data/budget.db (relative to this file)
      4) app/backend/data/budget.db (legacy location)
  - Prints all rows from each table, and also joined views for readability.
"""

import argparse
import json
import os
import sqlite3
import sys
from typing import Dict, List, Optional, Sequence

# Ensure UTF-8 output on Windows consoles
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def resolve_db_path(cli_path: Optional[str]) -> str:
    candidates: List[str] = []
    if cli_path:
        candidates.append(cli_path)
    env_path = os.environ.get("BUDGET_DB_PATH")
    if env_path:
        candidates.append(env_path)
    here = os.path.dirname(__file__)
    # Prefer the application's default DB path first (app/backend/data/budget.db)
    candidates.append(os.path.join(here, "data", "budget.db"))
    # Legacy/alternate path (app/backend/app/data/budget.db)
    candidates.append(os.path.join(here, "app", "data", "budget.db"))

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    # Fallback to first candidate even if missing (will error clearly)
    return candidates[0] if candidates else "budget.db"


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    return [r[1] for r in rows]


def print_header(title: str) -> None:
    print("\n" + "=" * 100)
    print(f"{title}")
    print("=" * 100)


def print_section(title: str) -> None:
    print("\n" + "-" * 100)
    print(title)
    print("-" * 100)


def format_row(row: Sequence[object]) -> str:
    return " | ".join(str(v) if v is not None else "" for v in row)


def dump_table(conn: sqlite3.Connection, table: str, limit: Optional[int] = None) -> None:
    cols = get_columns(conn, table)
    limit_sql = f" LIMIT {int(limit)}" if isinstance(limit, int) and limit > 0 else ""
    sql = f"SELECT * FROM {table}{limit_sql}"
    rows = conn.execute(sql).fetchall()
    print_section(f"Table: {table}  (rows: {len(rows)})")
    if not rows:
        print("<empty>")
        return
    print(" | ".join(cols))
    for r in rows:
        print(format_row([r[c] for c in cols]))


def dump_transactions_joined(conn: sqlite3.Connection) -> None:
    print_section("Joined View: transactions (with category/user/account names)")
    sql = (
        """
        SELECT t.id,
               t.date,
               t.amount,
               c.name AS category,
               u.name AS user,
               COALESCE(a.name, 'לא מוגדר') AS account,
               t.notes,
               t.tags,
               t.recurrence_id
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        ORDER BY t.date DESC, t.id DESC
        """
    )
    rows = conn.execute(sql).fetchall()
    if not rows:
        print("<empty>")
        return
    cols = list(rows[0].keys())
    print(" | ".join(cols))
    for r in rows:
        print(format_row([r[c] for c in cols]))


def dump_recurrences_joined(conn: sqlite3.Connection) -> None:
    print_section("Joined View: recurrences (with category/user/account when available)")
    # Determine if recurrences has account_id column
    rec_cols = set(get_columns(conn, "recurrences"))
    has_account = "account_id" in rec_cols
    sql = (
        """
        SELECT r.id,
               r.name,
               r.amount,
               r.frequency,
               r.day_of_month,
               r.weekday,
               r.next_charge_date,
               r.active,
               c.name AS category,
               u.name AS user
        FROM recurrences r
        LEFT JOIN categories c ON r.category_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
        """
    )
    if has_account:
        sql = sql.replace("FROM recurrences r", "FROM recurrences r LEFT JOIN accounts a ON r.account_id = a.id")
        select_tail = ", COALESCE(a.name, 'לא מוגדר') AS account"
        sql = sql.replace("u.name AS user", f"u.name AS user{select_tail}")
    sql += " ORDER BY r.id DESC"

    rows = conn.execute(sql).fetchall()
    if not rows:
        print("<empty>")
        return
    cols = list(rows[0].keys())
    print(" | ".join(cols))
    for r in rows:
        print(format_row([r[c] for c in cols]))


def dump_cash_vs_credit_window(conn: sqlite3.Connection) -> None:
    print_section("Window: last 6 months cash vs credit by user and account")
    sql = (
        """
        SELECT strftime('%Y-%m', t.date) AS month,
               u.name AS user_name,
               COALESCE(a.name, 'לא מוגדר') AS account_name,
               COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) as total_expenses,
               COUNT(CASE WHEN t.amount < 0 THEN 1 END) as transaction_count
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.date >= date('now','-6 months')
          AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY month, u.name, a.name
        ORDER BY month DESC, total_expenses DESC
        """
    )
    rows = conn.execute(sql).fetchall()
    if not rows:
        print("<empty>")
        return
    cols = list(rows[0].keys())
    print(" | ".join(cols))
    for r in rows:
        print(format_row([r[c] for c in cols]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump full DB contents and joined views")
    parser.add_argument("--db", dest="db_path", help="Path to SQLite DB file")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit per raw table dump")
    args = parser.parse_args()

    db_path = resolve_db_path(args.db_path)
    print_header(f"Using database: {db_path}")
    try:
        conn = connect(db_path)
    except Exception as exc:
        print(f"Failed to open DB: {exc}")
        sys.exit(1)

    # 1) Raw tables dump
    tables = list_tables(conn)
    print_header("Raw tables dump")
    for t in tables:
        dump_table(conn, t, limit=args.limit)

    # 2) Joined, human-friendly views
    print_header("Joined views")
    if "transactions" in tables:
        dump_transactions_joined(conn)
    if "recurrences" in tables:
        dump_recurrences_joined(conn)
    dump_cash_vs_credit_window(conn)

    conn.close()
    print_header("Done")


if __name__ == "__main__":
    main()


