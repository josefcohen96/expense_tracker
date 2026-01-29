import sqlite3
import os

DB_FILE = "budget.db"

def inspect_db():
    if not os.path.exists(DB_FILE):
        print(f"❌ Error: {DB_FILE} not found.")
        return

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"📦 Database Analysis: {DB_FILE}")
        print(f"Found {len(tables)} tables.")
        print("-" * 30)

        for table in tables:
            table_name = table[0]
            print(f"\n📋 Table: {table_name}")
            
            # Count rows
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"   Rows: {count}")
            
            # Show sample data (first 3 rows)
            if count > 0:
                print("   Sample Data:")
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                rows = cursor.fetchall()
                
                # Get column names
                col_names = [description[0] for description in cursor.description]
                print(f"   Columns: {', '.join(col_names)}")
                
                for row in rows:
                    print(f"   - {row}")
            else:
                print("   (Table is empty)")
                
        conn.close()
        print("\n✅ Verification Complete.")
        
    except Exception as e:
        print(f"❌ Error reading database: {e}")

if __name__ == "__main__":
    inspect_db()
