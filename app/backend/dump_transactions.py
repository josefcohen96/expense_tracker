#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to dump all transactions/expenses from the local database.
"""
import sqlite3
import sys
import io
from pathlib import Path
from datetime import datetime

# Fix encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add the app directory to path so we can import from it
sys.path.insert(0, str(Path(__file__).parent))

from app.db import get_connection

def dump_all_transactions():
    """Retrieve and display all transactions from the database."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all transactions with JOIN to get category, user, and account names
    query = """
        SELECT 
            t.id,
            t.date,
            t.amount,
            c.name as category,
            u.name as user,
            a.name as account,
            t.notes,
            t.tags,
            t.recurrence_id,
            t.period_key
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        JOIN users u ON t.user_id = u.id
        LEFT JOIN accounts a ON t.account_id = a.id
        ORDER BY t.date DESC, t.id DESC
    """
    
    cur.execute(query)
    rows = cur.fetchall()
    
    print(f"\n{'='*100}")
    print(f"כל ההוצאות במסד הנתונים (סה\"כ: {len(rows)} רשומות)")
    print(f"{'='*100}\n")
    
    if not rows:
        print("אין הוצאות במסד הנתונים!")
        conn.close()
        return
    
    # Print header
    print(f"{'ID':<6} {'תאריך':<12} {'סכום':<10} {'קטגוריה':<20} {'משתמש':<15} {'חשבון':<15} {'הערות':<30}")
    print(f"{'-'*6} {'-'*12} {'-'*10} {'-'*20} {'-'*15} {'-'*15} {'-'*30}")
    
    total_amount = 0
    
    for row in rows:
        tx_id = row[0]
        tx_date = row[1]
        amount = row[2]
        category = row[3]
        user = row[4]
        account = row[5] or "N/A"
        notes = row[6] or ""
        tags = row[7] or ""
        recurrence_id = row[8]
        period_key = row[9]
        
        total_amount += amount
        
        # Truncate long notes
        notes_display = (notes[:27] + "...") if len(notes) > 30 else notes
        
        print(f"{tx_id:<6} {tx_date:<12} ₪{amount:<9.2f} {category:<20} {user:<15} {account:<15} {notes_display:<30}")
        
        # Print additional info if exists
        if tags:
            print(f"       תגיות: {tags}")
        if recurrence_id:
            print(f"       חזרתיות: ID {recurrence_id}, תקופה {period_key}")
    
    print(f"\n{'-'*100}")
    print(f"סה\"כ הוצאות: ₪{total_amount:,.2f}")
    print(f"{'='*100}\n")
    
    # Additional statistics
    print("\nסטטיסטיקות נוספות:")
    print(f"{'-'*50}")
    
    # Count by category
    cur.execute("""
        SELECT c.name, COUNT(*), SUM(t.amount)
        FROM transactions t
        JOIN categories c ON t.category_id = c.id
        GROUP BY c.name
        ORDER BY SUM(t.amount) DESC
    """)
    
    print("\nפילוח לפי קטגוריה:")
    for row in cur.fetchall():
        print(f"  {row[0]:<20} - {row[1]:>4} הוצאות, סה\"כ: ₪{row[2]:>10,.2f}")
    
    # Count by user
    cur.execute("""
        SELECT u.name, COUNT(*), SUM(t.amount)
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        GROUP BY u.name
        ORDER BY SUM(t.amount) DESC
    """)
    
    print("\nפילוח לפי משתמש:")
    for row in cur.fetchall():
        print(f"  {row[0]:<20} - {row[1]:>4} הוצאות, סה\"כ: ₪{row[2]:>10,.2f}")
    
    # Count by month
    cur.execute("""
        SELECT 
            strftime('%Y-%m', date) as month,
            COUNT(*),
            SUM(amount)
        FROM transactions
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """)
    
    print("\nפילוח לפי חודש (12 האחרונים):")
    for row in cur.fetchall():
        print(f"  {row[0]} - {row[1]:>4} הוצאות, סה\"כ: ₪{row[2]:>10,.2f}")
    
    conn.close()

if __name__ == "__main__":
    try:
        dump_all_transactions()
    except Exception as e:
        print(f"\n❌ שגיאה בשליפת הנתונים: {e}")
        import traceback
        traceback.print_exc()

