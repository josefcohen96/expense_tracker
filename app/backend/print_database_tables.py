#!/usr/bin/env python3
"""
Script to print all database tables with their data in a nice formatted way.
"""

import sqlite3
from pathlib import Path
from datetime import datetime

# Database path
DB_PATH = Path(__file__).resolve().parent / "data" / "budget.db"

def print_separator(title: str) -> None:
    """Print a nice separator with title."""
    print("\n" + "="*80)
    print(f" {title} ".center(80, "="))
    print("="*80)

def print_table_data(conn: sqlite3.Connection, table_name: str, title: str = None) -> None:
    """Print table data in a nice formatted way."""
    if title is None:
        title = table_name.upper()
    
    print_separator(title)
    
    try:
        # Get table schema
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        if not columns:
            print(f"❌ Table '{table_name}' not found or empty")
            return
        
        # Get column names
        column_names = [col[1] for col in columns]
        
        # Get all data
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        if not rows:
            print(f"📭 Table '{table_name}' is empty")
            return
        
        # Print column headers
        print(f"📊 Found {len(rows)} rows in table '{table_name}'")
        print("-" * 80)
        
        # Print column names
        header = " | ".join(f"{col:15}" for col in column_names)
        print(header)
        print("-" * 80)
        
        # Print data rows
        for i, row in enumerate(rows, 1):
            formatted_row = []
            for j, value in enumerate(row):
                if value is None:
                    formatted_value = "NULL"
                elif isinstance(value, (int, float)):
                    formatted_value = str(value)
                elif isinstance(value, str):
                    # Truncate long strings
                    if len(value) > 15:
                        formatted_value = value[:12] + "..."
                    else:
                        formatted_value = value
                else:
                    formatted_value = str(value)
                
                formatted_row.append(f"{formatted_value:15}")
            
            row_str = " | ".join(formatted_row)
            print(f"{i:2}. {row_str}")
        
        print("-" * 80)
        
    except sqlite3.Error as e:
        print(f"❌ Error reading table '{table_name}': {e}")

def print_database_summary(conn: sqlite3.Connection) -> None:
    """Print a summary of all tables and their row counts."""
    print_separator("DATABASE SUMMARY")
    
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("📋 Database Tables Summary:")
    print("-" * 50)
    
    total_rows = 0
    for table in tables:
        table_name = table[0]
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"📊 {table_name:20} : {count:5} rows")
            total_rows += count
        except sqlite3.Error as e:
            print(f"❌ {table_name:20} : Error - {e}")
    
    print("-" * 50)
    print(f"📈 Total rows across all tables: {total_rows}")

def main() -> None:
    """Main function to print all database tables."""
    print("🔍 Database Tables Viewer")
    print(f"📁 Database path: {DB_PATH}")
    print(f"⏰ Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if not DB_PATH.exists():
        print(f"❌ Database file not found at: {DB_PATH}")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Print summary first
        print_database_summary(conn)
        
        # Print each table in detail
        tables_to_print = [
            ("users", "משתמשים"),
            ("categories", "קטגוריות"),
            ("accounts", "חשבונות"),
            ("recurrences", "הוצאות קבועות"),
            ("transactions", "עסקאות"),
            ("challenges", "אתגרים"),
            ("user_challenges", "אתגרי משתמשים"),
            ("system_settings", "הגדרות מערכת")
        ]
        
        for table_name, hebrew_name in tables_to_print:
            print_table_data(conn, table_name, hebrew_name)
        
        conn.close()
        
        print_separator("FINISHED")
        print("✅ Database tables printed successfully!")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
