import sqlite3
import sys

from app.backend.app.db import get_connection


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sql = (
        """
        SELECT
            r.id,
            r.name,
            r.amount,
            c.name AS category,
            u.name AS user,
            r.frequency,
            r.day_of_month,
            r.weekday,
            r.next_charge_date,
            r.active,
            a.name AS account
        FROM recurrences r
        JOIN categories c ON r.category_id = c.id
        JOIN users u ON r.user_id = u.id
        LEFT JOIN accounts a ON r.account_id = a.id
        WHERE c.name NOT IN ('משכורת','קליניקה')
        ORDER BY r.id
        """
    )

    rows = cur.execute(sql).fetchall()
    for row in rows:
        print(
            f"{row['id']}\t{row['name']}\t{row['amount']}\t{row['category']}\t{row['user']}\t"
            f"{row['frequency']}\t{row['day_of_month']}\t{row['weekday']}\t{row['next_charge_date']}\t{row['active']}\t"
            f"{(row['account'] or '')}"
        )

    conn.close()


if __name__ == "__main__":
    main()


