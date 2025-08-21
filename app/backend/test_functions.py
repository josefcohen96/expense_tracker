#!/usr/bin/env python3
"""Test the page functions directly."""

import sys
from pathlib import Path
from unittest.mock import Mock

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    print("Testing page functions...")
    from app.routes.pages import transactions_page, recurrences_page, income_page
    from app.db import get_connection
    
    print("✅ Imported functions successfully")
    
    # Get a real database connection
    db_conn = get_connection()
    print("✅ Got database connection")
    
    # Create a mock request
    mock_request = Mock()
    mock_request.url = "http://localhost:8000/transactions"
    
    print("\nTesting transactions_page function...")
    try:
        # This should work since we have real data
        result = transactions_page(mock_request, db_conn, page=1, per_page=20)
        print("✅ transactions_page function works!")
    except Exception as e:
        print(f"❌ transactions_page failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nTesting recurrences_page function...")
    try:
        result = recurrences_page(mock_request, db_conn, page=1, per_page=20)
        print("✅ recurrences_page function works!")
    except Exception as e:
        print(f"❌ recurrences_page failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nTesting income_page function...")
    try:
        result = income_page(mock_request, db_conn, page=1, per_page=20)
        print("✅ income_page function works!")
    except Exception as e:
        print(f"❌ income_page failed: {e}")
        import traceback
        traceback.print_exc()
    
    db_conn.close()
    print("\n✅ All function tests completed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
