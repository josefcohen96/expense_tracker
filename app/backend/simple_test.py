#!/usr/bin/env python3
"""Simple test to check database connection and basic queries."""

import sys
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    print("Testing database connection...")
    from app.db import get_connection
    
    conn = get_connection()
    print("✅ Database connection successful")
    
    # Test basic queries
    print("\nTesting basic queries...")
    
    # Test transactions count
    result = conn.execute("SELECT COUNT(*) as total FROM transactions t WHERE t.recurrence_id IS NULL AND t.amount < 0").fetchone()
    print(f"✅ Transactions count: {result['total']}")
    
    # Test recurrences count
    result = conn.execute("SELECT COUNT(*) as total FROM recurrences r").fetchone()
    print(f"✅ Recurrences count: {result['total']}")
    
    # Test categories
    result = conn.execute("SELECT id, name FROM categories ORDER BY name").fetchall()
    print(f"✅ Categories: {len(result)} found")
    
    # Test users
    result = conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    print(f"✅ Users: {len(result)} found")
    
    conn.close()
    print("\n✅ All database tests passed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
