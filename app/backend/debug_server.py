#!/usr/bin/env python3
"""Debug script to test the server and see exact errors."""

import asyncio
import sys
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_transactions_page():
    """Test the transactions page function."""
    try:
        from app.routes.pages import transactions_page
        from fastapi import Request
        from fastapi.testclient import TestClient
        from app.main import app
        
        print("✅ Imported modules successfully")
        
        # Create a test client
        client = TestClient(app)
        
        print("✅ Created test client")
        
        # Test the transactions page
        response = client.get("/transactions")
        print(f"✅ Transactions page response: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Transactions page works!")
        else:
            print(f"❌ Transactions page failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing transactions page: {e}")
        import traceback
        traceback.print_exc()

async def test_recurrences_page():
    """Test the recurrences page function."""
    try:
        from app.routes.pages import recurrences_page
        from fastapi import Request
        from fastapi.testclient import TestClient
        from app.main import app
        
        print("✅ Imported modules successfully")
        
        # Create a test client
        client = TestClient(app)
        
        print("✅ Created test client")
        
        # Test the recurrences page
        response = client.get("/recurrences")
        print(f"✅ Recurrences page response: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Recurrences page works!")
        else:
            print(f"❌ Recurrences page failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing recurrences page: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Testing transactions page...")
    asyncio.run(test_transactions_page())
    
    print("\nTesting recurrences page...")
    asyncio.run(test_recurrences_page())
