import requests
import json

# Test the GET endpoint
print("Testing GET /recurrences...")
try:
    response = requests.get("http://localhost:8001/recurrences")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ GET /recurrences works!")
    else:
        print(f"❌ GET /recurrences failed: {response.text}")
except Exception as e:
    print(f"❌ Error testing GET /recurrences: {e}")

# Test the POST endpoint
print("\nTesting POST /recurrences...")
try:
    data = {
        "name": "Test Recurrence",
        "amount": "100.00",
        "category_id": "1",
        "user_id": "1",
        "start_date": "2025-01-01",
        "frequency": "monthly",
        "day_of_month": "15"
    }
    
    response = requests.post(
        "http://localhost:8001/recurrences",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    print(f"Status: {response.status_code}")
    if response.status_code in [200, 303]:
        print("✅ POST /recurrences works!")
    else:
        print(f"❌ POST /recurrences failed: {response.text}")
except Exception as e:
    print(f"❌ Error testing POST /recurrences: {e}")

print("\nTest completed!")
