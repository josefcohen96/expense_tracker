from __future__ import annotations

import sqlite3
from datetime import date

from .. import db
from .. import recurrence


def ensure_row(conn: sqlite3.Connection, table: str, name: str) -> int:
    row = conn.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
    return int(cur.lastrowid)


def main() -> None:
    # Ensure schema exists
    db.initialise_database()
    conn = db.get_connection()
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        # Ensure user and categories
        user_id = ensure_row(conn, "users", "יוסף")
        cat_ztuv = ensure_row(conn, "categories", "טיפול זוגי")
        cat_psy = ensure_row(conn, "categories", "פסיכולוגית")

        # Insert weekly recurrences for August 2025 (Sundays)
        # Note: amounts are stored positive; generator inserts as negative expenses
        conn.execute(
            """
            INSERT INTO recurrences (name, amount, category_id, user_id, start_date, end_date, frequency, day_of_month, weekday, account_id, active)
            VALUES (?, ?, ?, ?, ?, ?, 'weekly', NULL, 6, NULL, 1)
            """,
            ("טיפול זוגי", 300, cat_ztuv, user_id, "2025-08-01", "2025-08-31"),
        )
        conn.execute(
            """
            INSERT INTO recurrences (name, amount, category_id, user_id, start_date, end_date, frequency, day_of_month, weekday, account_id, active)
            VALUES (?, ?, ?, ?, ?, ?, 'weekly', NULL, 6, NULL, 1)
            """,
            ("פסיכולוגית", 150, cat_psy, user_id, "2025-08-01", "2025-08-31"),
        )

        # Allow backfill for August by moving last_opened back if needed
        try:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('last_opened_at', ?)\n"
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("2025-08-01",),
            )
        except Exception:
            # If meta table doesn't exist, create and set
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('last_opened_at', ?)\n"
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("2025-08-01",),
            )

        conn.commit()

    finally:
        conn.close()

    # Run apply_recurring up to today to generate weekly Sundays in August and keep meta current
    inserted = recurrence.apply_recurring(today=date.today())

    # Print small summary
    print(f"Inserted recurring transactions: {inserted}")


if __name__ == "__main__":
    main()


