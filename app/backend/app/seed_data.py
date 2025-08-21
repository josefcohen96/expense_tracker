"""
Seed data generation for testing and development.
"""

import sqlite3
from pathlib import Path
import random
import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "budget.db"

def seed_recurrences() -> None:
    """Create recurring transactions for testing."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Recurring transactions data
    recurrences_data = [
        ("שכירות", -3000, 1, 1, "2024-01-01", "monthly", 1, None),
        ("חשמל", -400, 2, 1, "2024-01-15", "monthly", 15, None),
        ("מים", -200, 2, 2, "2024-01-10", "monthly", 10, None),
        ("אינטרנט", -150, 3, 1, "2024-01-05", "monthly", 5, None),
        ("ביטוח רכב", -800, 4, 2, "2024-01-20", "monthly", 20, None),
    ]

    for name, amount, category_id, user_id, start_date, frequency, day_of_month, weekday in recurrences_data:
        cur.execute("""
            INSERT INTO recurrences 
            (name, amount, category_id, user_id, start_date, frequency, day_of_month, weekday, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (name, amount, category_id, user_id, start_date, frequency, day_of_month, weekday))

    conn.commit()
    conn.close()
    print("✅ Seeded recurrences")

def seed_transactions(n_months: int = 2, per_month: int = 8) -> None:
    """Create sample transactions for testing."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    today = datetime.date.today()
    for m in range(n_months):
        base_date = today - datetime.timedelta(days=30*m)
        for _ in range(per_month):
            day = random.randint(1, 28)
            d = base_date.replace(day=min(day, 28))
            amount = -round(random.uniform(20, 500), 2)

            cur.execute("""
                INSERT INTO transactions
                (date, amount, category_id, user_id, account_id, notes, tags)
                VALUES (?, ?, 
                        (SELECT id FROM categories ORDER BY RANDOM() LIMIT 1),
                        (SELECT id FROM users ORDER BY RANDOM() LIMIT 1),
                        (SELECT id FROM accounts ORDER BY RANDOM() LIMIT 1),
                        ?, ?)
            """, (d.isoformat(), amount, "Generated expense", "seed"))

    conn.commit()
    conn.close()
    print("✅ Seeded test transactions")

if __name__ == "__main__":
    seed_recurrences()
    seed_transactions()
