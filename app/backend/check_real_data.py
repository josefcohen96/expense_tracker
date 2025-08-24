import sqlite3
from pathlib import Path

def check_real_data():
    """Check the real data in the database."""
    
    db_path = "app/data/couplebudget.sqlite3"
    
    if not Path(db_path).exists():
        print(f"❌ מסד הנתונים לא נמצא: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("=== בדיקת הנתונים האמיתיים באוגוסט 2025 ===")
    
    # Count all transactions for August 2025
    cur = conn.execute("""
        SELECT COUNT(*) as count 
        FROM transactions 
        WHERE strftime('%Y-%m', date) = '2025-08'
    """)
    total_count = cur.fetchone()['count']
    print(f"סה\"כ עסקאות באוגוסט 2025: {total_count}")
    
    # Get all transactions
    cur = conn.execute("""
        SELECT t.id, t.date, t.amount, c.name as category, u.name as user, 
               a.name as account, t.notes, t.tags
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE strftime('%Y-%m', t.date) = '2025-08'
        ORDER BY t.date DESC, t.id DESC
    """)
    
    transactions = cur.fetchall()
    print(f"\nכל העסקאות באוגוסט 2025:")
    for tx in transactions:
        amount_type = "הכנסה" if tx['amount'] > 0 else "הוצאה"
        print(f"  ID: {tx['id']}, תאריך: {tx['date']}, סכום: {tx['amount']} ({amount_type}), קטגוריה: {tx['category']}, משתמש: {tx['user']}")
    
    # Get categories
    cur = conn.execute("""
        SELECT DISTINCT c.name as category
        FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', t.date) = '2025-08'
        ORDER BY c.name
    """)
    
    categories = cur.fetchall()
    print(f"\nקטגוריות באוגוסט 2025:")
    for cat in categories:
        print(f"  - {cat['category']}")
    
    # Check if we have the categories you mentioned
    target_categories = ['רכב', 'קניות', 'פנאי', 'אוכל בחוץ', 'הוצאות דירה']
    found_categories = [cat['category'] for cat in categories]
    
    print(f"\nקטגוריות שאתה רואה בדף:")
    for cat in target_categories:
        if cat in found_categories:
            print(f"  ✅ {cat}")
        else:
            print(f"  ❌ {cat} - לא נמצא")
    
    conn.close()

if __name__ == "__main__":
    check_real_data()
