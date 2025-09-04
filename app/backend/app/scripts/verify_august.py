from __future__ import annotations

import sqlite3
from typing import List, Tuple
from .. import db


def fetch_rows(sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
    conn = db.get_connection()
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def main() -> None:
    # Find recurrence ids
    recs = fetch_rows(
        "SELECT id, name FROM recurrences WHERE name IN ('טיפול זוגי','פסיכולוגית') ORDER BY name"
    )
    labels = [f"{r['name']}#{r['id']}" for r in recs]
    print("Recurrences found:", labels)

    if not recs:
        print("No recurrences found.")
        return

    rec_ids = tuple(r["id"] for r in recs)
    placeholders = ",".join(["?"] * len(rec_ids))
    rows = fetch_rows(
        f"""
        SELECT t.date, t.amount, t.recurrence_id, t.period_key, c.name AS category, u.name AS user
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        JOIN users u ON t.user_id = u.id
        WHERE t.recurrence_id IN ({placeholders})
          AND t.date BETWEEN '2025-08-01' AND '2025-08-31'
        ORDER BY t.date ASC, t.recurrence_id ASC
        """,
        rec_ids,
    )
    print(f"August 2025 recurring tx count: {len(rows)}")
    for r in rows:
        print(f"{r['date']} | {r['category']} | {r['user']} | {r['amount']} | rid={r['recurrence_id']} | {r['period_key']}")


if __name__ == "__main__":
    main()


