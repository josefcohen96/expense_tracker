"""
סקריפט בדיקה לוודא שהתיקונים עובדים נכון
"""
import sqlite3
from datetime import datetime

# התחבר ל-DB
conn = sqlite3.connect('budget.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 60)
print("בדיקת תיקוני חישובים - פברואר 2026")
print("=" * 60)

# בדיקה 1: חישוב הוצאות והכנסות לחודש נוכחי (עם סינון קטגוריות)
print("\n1️⃣ חישוב חודש נוכחי עם סינון קטגוריות:")
result = cur.execute("""
    SELECT 
        SUM(CASE WHEN t.amount < 0 AND c.name NOT IN ('משכורת', 'קליניקה') 
                 THEN ABS(t.amount) ELSE 0 END) as total_expenses,
        SUM(CASE WHEN t.amount > 0 AND c.name IN ('משכורת', 'קליניקה') 
                 THEN t.amount ELSE 0 END) as total_income
    FROM transactions t
    LEFT JOIN categories c ON t.category_id = c.id
    WHERE strftime('%Y-%m', t.date) = '2026-02'
""").fetchone()

expenses = result['total_expenses'] or 0
income = result['total_income'] or 0

print(f"   הוצאות: ₪{expenses:.2f}")
print(f"   הכנסות: ₪{income:.2f}")
print(f"   יתרה: ₪{income - expenses:.2f}")

# בדיקה 2: השוואה - מה היה ללא סינון?
print("\n2️⃣ חישוב ללא סינון (הדרך הישנה - שגויה):")
result_old = cur.execute("""
    SELECT 
        SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_expenses,
        SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_income
    FROM transactions
    WHERE strftime('%Y-%m', date) = '2026-02'
""").fetchone()

expenses_old = result_old['total_expenses'] or 0
income_old = result_old['total_income'] or 0

print(f"   הוצאות: ₪{expenses_old:.2f}")
print(f"   הכנסות: ₪{income_old:.2f}")
print(f"   ⚠️ הבדל בהוצאות: ₪{abs(expenses - expenses_old):.2f}")
print(f"   ⚠️ הבדל בהכנסות: ₪{abs(income - income_old):.2f}")

# בדיקה 3: פירוט לפי קטגוריות
print("\n3️⃣ פירוט עסקאות לפי קטגוריה (פברואר 2026):")
categories = cur.execute("""
    SELECT c.name, 
           COUNT(*) as count, 
           SUM(t.amount) as total,
           CASE WHEN c.name IN ('משכורת', 'קליניקה') THEN 'הכנסה' ELSE 'הוצאה' END as type
    FROM transactions t
    JOIN categories c ON t.category_id = c.id
    WHERE strftime('%Y-%m', t.date) = '2026-02'
    GROUP BY c.name
    ORDER BY type, ABS(total) DESC
""").fetchall()

for cat in categories:
    print(f"   {cat['type']:8} | {cat['name']:20} | {cat['count']:3} עסקאות | ₪{cat['total']:10.2f}")

# בדיקה 4: ספירת הוצאות קבועות
print("\n4️⃣ הוצאות קבועות פעילות:")
rec_all = cur.execute("SELECT COUNT(*) as cnt FROM recurrences WHERE active = 1").fetchone()
print(f"   כל ההוצאות הקבועות: {rec_all['cnt']}")

# קבלת IDs של משתמשים ראשיים
main_users = cur.execute("SELECT id FROM users WHERE name IN ('Yosef','Karina')").fetchall()
if main_users:
    user_ids_str = ','.join(str(row['id']) for row in main_users)
    rec_main = cur.execute(f"SELECT COUNT(*) as cnt FROM recurrences WHERE active = 1 AND user_id IN ({user_ids_str})").fetchone()
    print(f"   הוצאות קבועות של משתמשים ראשיים: {rec_main['cnt']}")
    if rec_all['cnt'] != rec_main['cnt']:
        print(f"   ⚠️ הבדל: {rec_all['cnt'] - rec_main['cnt']} הוצאות של משתמשים אחרים")

print("\n" + "=" * 60)
print("✅ בדיקה הושלמה!")
print("=" * 60)

conn.close()
