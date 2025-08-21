#!/usr/bin/env python3
"""
סקריפט לאיפוס כל הטבלאות של הוצאות והוצאות קבועות
"""

import sqlite3
from pathlib import Path

# נתיב לקובץ הדיבי
DB_PATH = Path(__file__).resolve().parent / "data" / "budget.db"


def reset_expenses():
    """מאפס את כל הטבלאות של הוצאות והוצאות קבועות"""

    if not DB_PATH.exists():
        print(f"❌ קובץ הדיבי לא נמצא: {DB_PATH}")
        return

    try:
        # התחברות לדיבי
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        print("🔄 מתחיל איפוס הטבלאות...")

        # בדיקה כמה רשומות יש לפני האיפוס
        transactions_count = cur.execute(
            "SELECT COUNT(*) FROM transactions").fetchone()[0]
        recurrences_count = cur.execute(
            "SELECT COUNT(*) FROM recurrences").fetchone()[0]

        print(f"📊 לפני האיפוס:")
        print(f"   - עסקאות: {transactions_count}")
        print(f"   - הוצאות קבועות: {recurrences_count}")

        # מחיקת כל העסקאות
        cur.execute("DELETE FROM transactions")
        deleted_transactions = cur.rowcount

        # מחיקת כל ההוצאות הקבועות
        cur.execute("DELETE FROM recurrences")
        deleted_recurrences = cur.rowcount

        # שמירת השינויים
        conn.commit()

        # בדיקה כמה רשומות נשארו אחרי האיפוס
        remaining_transactions = cur.execute(
            "SELECT COUNT(*) FROM transactions").fetchone()[0]
        remaining_recurrences = cur.execute(
            "SELECT COUNT(*) FROM recurrences").fetchone()[0]

        print(f"✅ האיפוס הושלם בהצלחה!")
        print(f"📊 אחרי האיפוס:")
        print(f"   - עסקאות שנמחקו: {deleted_transactions}")
        print(f"   - הוצאות קבועות שנמחקו: {deleted_recurrences}")
        print(f"   - עסקאות שנותרו: {remaining_transactions}")
        print(f"   - הוצאות קבועות שנותרו: {remaining_recurrences}")

        # סגירת החיבור
        conn.close()

        print("\n🎉 כל הטבלאות אופסו בהצלחה!")
        print("💡 עכשיו אתה יכול להתחיל להכניס נתונים חדשים")

    except Exception as e:
        print(f"❌ שגיאה בזמן האיפוס: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()


def confirm_reset():
    """בקשת אישור מהמשתמש לפני האיפוס"""
    print("⚠️  אזהרה: פעולה זו תמחק את כל העסקאות וההוצאות הקבועות!")
    print("📝 פעולה זו בלתי הפיכה!")

    response = input(
        "\nהאם אתה בטוח שברצונך להמשיך? (כן/לא): ").strip().lower()

    if response in ['כן', 'yes', 'y', 'י']:
        return True
    else:
        print("❌ האיפוס בוטל")
        return False


if __name__ == "__main__":
    print("🧹 סקריפט איפוס הוצאות")
    print("=" * 40)

    if confirm_reset():
        reset_expenses()
    else:
        print("👋 לא בוצע איפוס")
