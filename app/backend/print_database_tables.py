#!/usr/bin/env python3
"""
סקריפט להצגת נתונים מהדאטהבייס בטבלה יפה מותאמת לעברית
"""

import sqlite3
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
import sys

# הוספת הנתיב לפרויקט
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

def get_db_connection():
    """יצירת חיבור לדאטהבייס"""
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'budget.db')
    return sqlite3.connect(db_path)

def get_last_6_months():
    """קבלת 6 החודשים האחרונים בפורמט YYYY-MM"""
    today = datetime.today().replace(day=1)
    months = []
    for i in range(5, -1, -1):
        month = (today - relativedelta(months=i)).strftime('%Y-%m')
        months.append(month)
    return months

def print_header(title):
    """הדפסת כותרת יפה"""
    print("\n" + "="*80)
    print(f"📊 {title}")
    print("="*80)

def print_section_header(title):
    """הדפסת כותרת סעיף"""
    print(f"\n🔹 {title}")
    print("-" * 60)

def format_currency(amount):
    """עיצוב סכום כסף"""
    if amount is None:
        return "0.00 ₪"
    return f"{abs(amount):,.2f} ₪"

def print_table(data, headers, title=None):
    """הדפסת טבלה יפה"""
    if title:
        print_section_header(title)
    
    if not data:
        print("❌ אין נתונים זמינים")
        return
    
    # חישוב רוחב העמודות
    col_widths = []
    for i, header in enumerate(headers):
        max_width = len(header)
        for row in data:
            if i < len(row):
                cell_width = len(str(row[i]))
                max_width = max(max_width, cell_width)
        col_widths.append(max_width + 2)  # רווח נוסף
    
    # הדפסת כותרות
    header_line = " | ".join(f"{header:<{col_widths[i]}}" for i, header in enumerate(headers))
    print(header_line)
    print("-" * len(header_line))
    
    # הדפסת נתונים
    for row in data:
        formatted_row = []
        for i, cell in enumerate(row):
            if i < len(col_widths):
                formatted_row.append(f"{str(cell):<{col_widths[i]}}")
        print(" | ".join(formatted_row))

def print_summary_statistics(conn):
    """הדפסת סטטיסטיקות סיכום"""
    print_header("📈 סטטיסטיקות סיכום - חודש נוכחי")
    
    cur = conn.cursor()
    
    # הוצאות רגילות לחודש הנוכחי
    regular_expenses = cur.execute("""
        SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        AND t.recurrence_id IS NULL
    """).fetchone()[0]
    
    # הוצאות קבועות לחודש הנוכחי
    recurring_expenses = cur.execute("""
        SELECT COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) as total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        AND t.recurrence_id IS NOT NULL
    """).fetchone()[0]
    
    # הכנסות לחודש הנוכחי
    income = cur.execute("""
        SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        AND c.name IN ('משכורת', 'קליניקה')
    """).fetchone()[0]
    
    # כמות עסקאות רגילות
    regular_count = cur.execute("""
        SELECT COUNT(*) as total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        AND t.recurrence_id IS NULL
    """).fetchone()[0]
    
    # כמות עסקאות קבועות
    recurring_count = cur.execute("""
        SELECT COUNT(*) as total
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        AND t.recurrence_id IS NOT NULL
    """).fetchone()[0]
    
    total_expenses = regular_expenses + recurring_expenses
    balance = income - total_expenses
    
    print(f"💰 הוצאות רגילות:     {format_currency(regular_expenses)} ({regular_count} עסקאות)")
    print(f"🔄 הוצאות קבועות:     {format_currency(recurring_expenses)} ({recurring_count} עסקאות)")
    print(f"📊 סה״כ הוצאות:       {format_currency(total_expenses)}")
    print(f"💵 הכנסות:            {format_currency(income)}")
    print(f"⚖️  יתרה:              {format_currency(balance)}")
    print(f"📈 סה״כ עסקאות:       {regular_count + recurring_count}")

def print_monthly_expenses(conn):
    """הדפסת הוצאות חודשיות"""
    print_header("📅 הוצאות חודשיות - 6 חודשים אחרונים")
    
    cur = conn.cursor()
    
    # הוצאות חודשיות כולל רגילות וקבועות
    monthly_data = cur.execute("""
        SELECT 
            strftime('%Y-%m', t.date) AS month,
            COALESCE(SUM(CASE WHEN t.amount < 0 AND t.recurrence_id IS NULL THEN -t.amount ELSE 0 END), 0) as regular_expenses,
            COALESCE(SUM(CASE WHEN t.amount < 0 AND t.recurrence_id IS NOT NULL THEN -t.amount ELSE 0 END), 0) as recurring_expenses,
            COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) as total_expenses,
            COUNT(CASE WHEN t.amount < 0 AND t.recurrence_id IS NULL THEN 1 END) as regular_count,
            COUNT(CASE WHEN t.amount < 0 AND t.recurrence_id IS NOT NULL THEN 1 END) as recurring_count
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY strftime('%Y-%m', t.date)
        ORDER BY month DESC
    """).fetchall()
    
    if not monthly_data:
        print("❌ אין נתונים זמינים")
        return
    
    # המרת נתונים לפורמט מתאים להצגה
    formatted_data = []
    for row in monthly_data:
        formatted_data.append([
            row[0],  # חודש
            format_currency(row[1]),  # הוצאות רגילות
            format_currency(row[2]),  # הוצאות קבועות
            format_currency(row[3]),  # סה״כ הוצאות
            str(row[4]),  # כמות רגילות
            str(row[5])   # כמות קבועות
        ])
    
    headers = ['חודש', 'הוצאות רגילות', 'הוצאות קבועות', 'סה״כ הוצאות', 'כמות רגילות', 'כמות קבועות']
    print_table(formatted_data, headers)

def print_category_expenses(conn):
    """הדפסת הוצאות לפי קטגוריה"""
    print_header("🏷️  הוצאות לפי קטגוריה - 6 חודשים אחרונים")
    
    cur = conn.cursor()
    
    category_data = cur.execute("""
        SELECT 
            c.name AS category,
            COALESCE(SUM(CASE WHEN t.amount < 0 AND t.recurrence_id IS NULL THEN -t.amount ELSE 0 END), 0) as regular_expenses,
            COALESCE(SUM(CASE WHEN t.amount < 0 AND t.recurrence_id IS NOT NULL THEN -t.amount ELSE 0 END), 0) as recurring_expenses,
            COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) as total_expenses,
            COUNT(CASE WHEN t.amount < 0 AND t.recurrence_id IS NULL THEN 1 END) as regular_count,
            COUNT(CASE WHEN t.amount < 0 AND t.recurrence_id IS NOT NULL THEN 1 END) as recurring_count
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY c.name
        HAVING total_expenses > 0
        ORDER BY total_expenses DESC
    """).fetchall()
    
    if not category_data:
        print("❌ אין נתונים זמינים")
        return
    
    # המרת נתונים לפורמט מתאים להצגה
    formatted_data = []
    for row in category_data:
        formatted_data.append([
            row[0],  # קטגוריה
            format_currency(row[1]),  # הוצאות רגילות
            format_currency(row[2]),  # הוצאות קבועות
            format_currency(row[3]),  # סה״כ הוצאות
            str(row[4]),  # כמות רגילות
            str(row[5])   # כמות קבועות
        ])
    
    headers = ['קטגוריה', 'הוצאות רגילות', 'הוצאות קבועות', 'סה״כ הוצאות', 'כמות רגילות', 'כמות קבועות']
    print_table(formatted_data, headers)

def print_user_expenses(conn):
    """הדפסת הוצאות לפי משתמש"""
    print_header("👥 הוצאות לפי משתמש - 6 חודשים אחרונים")
    
    cur = conn.cursor()
    
    user_data = cur.execute("""
        SELECT 
            u.name AS user_name,
            COALESCE(SUM(CASE WHEN t.amount < 0 AND t.recurrence_id IS NULL THEN -t.amount ELSE 0 END), 0) as regular_expenses,
            COALESCE(SUM(CASE WHEN t.amount < 0 AND t.recurrence_id IS NOT NULL THEN -t.amount ELSE 0 END), 0) as recurring_expenses,
            COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) as total_expenses,
            COUNT(CASE WHEN t.amount < 0 AND t.recurrence_id IS NULL THEN 1 END) as regular_count,
            COUNT(CASE WHEN t.amount < 0 AND t.recurrence_id IS NOT NULL THEN 1 END) as recurring_count
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        JOIN categories c ON t.category_id = c.id
        WHERE t.date >= date('now', '-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY u.name
        HAVING total_expenses > 0
        ORDER BY total_expenses DESC
    """).fetchall()
    
    if not user_data:
        print("❌ אין נתונים זמינים")
        return
    
    # המרת נתונים לפורמט מתאים להצגה
    formatted_data = []
    for row in user_data:
        formatted_data.append([
            row[0],  # משתמש
            format_currency(row[1]),  # הוצאות רגילות
            format_currency(row[2]),  # הוצאות קבועות
            format_currency(row[3]),  # סה״כ הוצאות
            str(row[4]),  # כמות רגילות
            str(row[5])   # כמות קבועות
        ])
    
    headers = ['משתמש', 'הוצאות רגילות', 'הוצאות קבועות', 'סה״כ הוצאות', 'כמות רגילות', 'כמות קבועות']
    print_table(formatted_data, headers)

def print_top_expenses(conn):
    """הדפסת 10 ההוצאות הגדולות ביותר"""
    print_header("🔥 10 ההוצאות הגדולות ביותר - 3 חודשים אחרונים")
    
    cur = conn.cursor()
    
    top_expenses = cur.execute("""
        SELECT 
            t.date,
            COALESCE(t.notes, 'ללא הערות') AS notes,
            c.name AS category,
            u.name AS user_name,
            COALESCE(a.name, 'לא מוגדר') AS account_name,
            t.amount,
            CASE WHEN t.recurrence_id IS NOT NULL THEN 'קבועה' ELSE 'רגילה' END AS expense_type
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        WHERE t.date >= date('now', '-3 months')
        AND t.amount < 0
        AND c.name NOT IN ('משכורת', 'קליניקה')
        ORDER BY ABS(t.amount) DESC
        LIMIT 10
    """).fetchall()
    
    if not top_expenses:
        print("❌ אין נתונים זמינים")
        return
    
    # המרת נתונים לפורמט מתאים להצגה
    formatted_data = []
    for row in top_expenses:
        formatted_data.append([
            row[0],  # תאריך
            row[1][:20] + "..." if len(row[1]) > 20 else row[1],  # הערות (מוגבל ל-20 תווים)
            row[2],  # קטגוריה
            row[3],  # משתמש
            row[4],  # חשבון
            format_currency(row[5]),  # סכום
            row[6]   # סוג
        ])
    
    headers = ['תאריך', 'הערות', 'קטגוריה', 'משתמש', 'חשבון', 'סכום', 'סוג']
    print_table(formatted_data, headers)

def print_cash_vs_credit(conn):
    """הדפסת מזומן מול אשראי"""
    print_header("💳 מזומן מול אשראי - 6 חודשים אחרונים")
    
    cur = conn.cursor()
    
    cash_credit_data = cur.execute("""
        SELECT 
            strftime('%Y-%m', t.date) AS month,
            u.name AS user_name,
            COALESCE(a.name, 'לא מוגדר') AS account_type,
            COALESCE(SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END), 0) as total_expenses,
            COUNT(CASE WHEN t.amount < 0 THEN 1 END) as transaction_count
        FROM transactions t
        LEFT JOIN accounts a ON t.account_id = a.id
        JOIN categories c ON t.category_id = c.id
        JOIN users u ON t.user_id = u.id
        WHERE t.date >= date('now','start of month','-6 months')
        AND c.name NOT IN ('משכורת', 'קליניקה')
        GROUP BY month, u.name, a.name
        HAVING total_expenses > 0
        ORDER BY month DESC, total_expenses DESC
    """).fetchall()
    
    if not cash_credit_data:
        print("❌ אין נתונים זמינים")
        return
    
    # המרת נתונים לפורמט מתאים להצגה
    formatted_data = []
    for row in cash_credit_data:
        formatted_data.append([
            row[0],  # חודש
            row[1],  # משתמש
            row[2],  # סוג חשבון
            format_currency(row[3]),  # סה״כ הוצאות
            str(row[4])   # כמות עסקאות
        ])
    
    headers = ['חודש', 'משתמש', 'סוג חשבון', 'סה״כ הוצאות', 'כמות עסקאות']
    print_table(formatted_data, headers)

def main():
    """פונקציה ראשית"""
    try:
        print_header("📊 דוח סטטיסטיקות הוצאות")
        print(f"📅 תאריך יצירת הדוח: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        conn = get_db_connection()
        
        # הדפסת כל הסעיפים
        print_summary_statistics(conn)
        print_monthly_expenses(conn)
        print_category_expenses(conn)
        print_user_expenses(conn)
        print_top_expenses(conn)
        print_cash_vs_credit(conn)
        
        conn.close()
        
        print_header("✅ הדוח הושלם בהצלחה")
        
    except Exception as e:
        print(f"❌ שגיאה: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
