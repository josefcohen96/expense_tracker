# app/backend/app/seed_data.py
import sqlite3
from pathlib import Path
import random, datetime

DB_PATH = Path(__file__).resolve().parent / "data" / "couplebudget.sqlite3"

def seed_transactions(n_months=6, per_month=8):
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
    seed_transactions()
