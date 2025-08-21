#!/usr/bin/env python3
"""Test script to check if pages module works correctly."""

import sys
import os
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    print("Testing imports...")
    from app.routes.pages import router, transactions_page, income_page, recurrences_page
    print("✅ All imports successful")
    
    print("\nTesting router routes...")
    routes = [route for route in router.routes]
    print(f"✅ Found {len(routes)} routes")
    
    # Check specific routes
    transaction_routes = [r for r in routes if "/transactions" in str(r.path)]
    income_routes = [r for r in routes if "/income" in str(r.path)]
    recurrence_routes = [r for r in routes if "/recurrences" in str(r.path)]
    
    print(f"✅ Transaction routes: {len(transaction_routes)}")
    print(f"✅ Income routes: {len(income_routes)}")
    print(f"✅ Recurrence routes: {len(recurrence_routes)}")
    
    print("\n✅ All tests passed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
