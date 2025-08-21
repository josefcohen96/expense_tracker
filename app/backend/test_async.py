#!/usr/bin/env python3
"""Async test to check if the page functions work correctly."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_page_functions():
    """Test the page functions with proper async/await."""
    try:
        print("Testing page functions with async/await...")
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
            result = await transactions_page(mock_request, db_conn, page=1, per_page=20)
            print("✅ transactions_page function works!")
            print(f"   Response type: {type(result)}")
        except Exception as e:
            print(f"❌ transactions_page failed: {e}")
            import traceback
            traceback.print_exc()
        
        print("\nTesting recurrences_page function...")
        try:
            result = await recurrences_page(mock_request, db_conn, page=1, per_page=20)
            print("✅ recurrences_page function works!")
            print(f"   Response type: {type(result)}")
        except Exception as e:
            print(f"❌ recurrences_page failed: {e}")
            import traceback
            traceback.print_exc()
        
        print("\nTesting income_page function...")
        try:
            result = await income_page(mock_request, db_conn, page=1, per_page=20)
            print("✅ income_page function works!")
            print(f"   Response type: {type(result)}")
        except Exception as e:
            print(f"❌ income_page failed: {e}")
            import traceback
            traceback.print_exc()
        
        db_conn.close()
        print("\n✅ All async function tests completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_page_functions())
