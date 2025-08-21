import requests

print("Testing recurrence functionality...")

# Test GET endpoint
try:
    response = requests.get("http://127.0.0.1:8001/recurrences")
    print(f"GET /recurrences: {response.status_code}")
    if response.status_code == 200:
        print("✅ GET endpoint works!")
    else:
        print(f"❌ GET failed: {response.text}")
except Exception as e:
    print(f"❌ GET error: {e}")

# Test POST endpoint
try:
    data = {
        "name": "Test Monthly Expense",
        "amount": "150.00",
        "category_id": "1",
        "user_id": "1",
        "start_date": "2025-01-01",
        "frequency": "monthly",
        "day_of_month": "15"
    }
    
    response = requests.post(
        "http://127.0.0.1:8001/recurrences",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    print(f"POST /recurrences: {response.status_code}")
    if response.status_code in [200, 303]:
        print("✅ POST endpoint works!")
    else:
        print(f"❌ POST failed: {response.text}")
except Exception as e:
    print(f"❌ POST error: {e}")

print("Test completed!")
