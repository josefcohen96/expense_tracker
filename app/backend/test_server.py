#!/usr/bin/env python3
"""Test the server by making actual HTTP requests."""

import asyncio
import httpx
import time

async def test_server():
    """Test the server endpoints."""
    print("Testing server endpoints...")
    
    # Wait a bit for server to start
    await asyncio.sleep(2)
    
    async with httpx.AsyncClient() as client:
        try:
            # Test transactions page
            print("\nTesting /transactions...")
            response = await client.get("http://localhost:8000/transactions")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Transactions page works!")
            else:
                print(f"❌ Transactions page failed: {response.text}")
            
            # Test recurrences page
            print("\nTesting /recurrences...")
            response = await client.get("http://localhost:8000/recurrences")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Recurrences page works!")
            else:
                print(f"❌ Recurrences page failed: {response.text}")
            
            # Test income page
            print("\nTesting /income...")
            response = await client.get("http://localhost:8000/income")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Income page works!")
            else:
                print(f"❌ Income page failed: {response.text}")
                
        except Exception as e:
            print(f"❌ Error testing server: {e}")

if __name__ == "__main__":
    asyncio.run(test_server())
