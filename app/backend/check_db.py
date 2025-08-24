#!/usr/bin/env python3
"""
סקריפט לבדיקת הדאטהבייס
"""

import sqlite3
import os

def check_database(db_path):
    """בדיקת דאטהבייס"""
    print(f"🔍 בודק דאטהבייס: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"❌ הקובץ לא קיים: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # בדיקת טבלאות
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cur.fetchall()
        
        print(f"📊 טבלאות שנמצאו: {len(tables)}")
        for table in tables:
            print(f"  - {table[0]}")
        
        # בדיקה אם יש טבלת transactions
        if any('transactions' in table[0].lower() for table in tables):
            print("✅ נמצאה טבלת transactions")
            
            # בדיקת כמות רשומות
            cur.execute("SELECT COUNT(*) FROM transactions")
            count = cur.fetchone()[0]
            print(f"📈 כמות עסקאות: {count}")
            
            if count > 0:
                # בדיקת דוגמה
                cur.execute("SELECT * FROM transactions LIMIT 1")
                sample = cur.fetchone()
                print(f"📋 דוגמה: {sample}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ שגיאה: {e}")
        return False

def main():
    """פונקציה ראשית"""
    databases = [
        "data/expenses.db",
        "data/budget.db", 
        "data/couplebudget.sqlite3"
    ]
    
    print("🔍 בודק דאטהבייסים...")
    
    for db_path in databases:
        print("\n" + "="*50)
        check_database(db_path)

if __name__ == "__main__":
    main()
