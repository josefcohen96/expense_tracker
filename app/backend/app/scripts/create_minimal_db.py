#!/usr/bin/env python3
"""
Create a minimal SQLite database containing only essential tables.

Kept tables (and why):
  - transactions: holds both expenses and income (sign/category decide)
  - recurrences: recurring definitions
  - recurrence_skips: track skipped occurrences
  - system_settings: status/meta used by CRON/recurrence
  - users: owners of transactions/recurrences
  - categories: FK dependency of transactions/recurrences
  - accounts: FK dependency of transactions (payment method)

Usage:
  python app/backend/app/scripts/create_minimal_db.py \
    --source app/backend/data/budget.db \
    --dest   app/backend/data/budget_minimal.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Iterable, List


KEEP_TABLES: List[str] = [
    "transactions",
    "recurrences",
    "recurrence_skips",
    "system_settings",
    "users",
    "categories",
    "accounts",
]


def ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)


def run(args: argparse.Namespace) -> None:
    source = os.path.abspath(args.source)
    dest = os.path.abspath(args.dest)

    if not os.path.isfile(source):
        raise SystemExit(f"Source DB not found: {source}")

    ensure_dir(dest)
    if os.path.exists(dest):
        if not args.overwrite:
            raise SystemExit(f"Destination already exists: {dest} (use --overwrite to replace)")
        os.remove(dest)

    # Create destination DB
    dest_conn = sqlite3.connect(dest)
    dest_conn.row_factory = sqlite3.Row
    dest_conn.execute("PRAGMA foreign_keys = ON")

    try:
        # Attach source DB for direct copying
        dest_conn.execute("ATTACH DATABASE ? AS src", (source,))

        # Fetch CREATE TABLE sql for kept tables from source
        rows = dest_conn.execute(
            "SELECT name, sql FROM src.sqlite_master WHERE type='table' AND name IN (%s)" % (
                ",".join(["?"] * len(KEEP_TABLES))
            ),
            KEEP_TABLES,
        ).fetchall()

        src_tables = {r["name"]: r["sql"] for r in rows}
        missing = [t for t in KEEP_TABLES if t not in src_tables]
        if missing:
            raise SystemExit(f"Missing tables in source: {missing}")

        # Create tables in destination (add IF NOT EXISTS defensively)
        for name in KEEP_TABLES:
            create_sql = src_tables[name]
            if not create_sql:
                raise SystemExit(f"No CREATE SQL for table {name}")
            # normalize to add IF NOT EXISTS
            create_sql = create_sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
            dest_conn.execute(create_sql)

        # Copy data: INSERT INTO main.t SELECT * FROM src.t
        for name in KEEP_TABLES:
            dest_conn.execute(f"INSERT INTO main.{name} SELECT * FROM src.{name}")

        dest_conn.commit()

        # Verify destination tables
        out = dest_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        names = [r[0] for r in out]
        print("Created minimal DB at:", dest)
        print("Tables (", len(names), "):", ", ".join(names))

    finally:
        dest_conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a minimal clone of the DB with essential tables only")
    parser.add_argument("--source", default=os.path.join("app", "backend", "data", "budget.db"), help="Path to source DB")
    parser.add_argument("--dest", default=os.path.join("app", "backend", "data", "budget_minimal.db"), help="Path to destination DB")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite destination if exists")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()


