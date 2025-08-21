#!/usr/bin/env python3
"""Test the recurrences page specifically."""

import asyncio
import httpx

async def test_recurrences():
    """Test the recurrences page."""
    print("Testing /recurrences specifically...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/recurrences")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("✅ Recurrences page works!")
            else:
                print(f"❌ Recurrences page failed: {response.text}")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_recurrences())
