import os
import requests
import time

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001")

# Test root endpoint
print("\n" + "="*70)
print("Testing Backend Integration")
print("="*70)

try:
    response = requests.get(f"{BASE_URL}/")
    print(f"\n✅ Backend is running!")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"\n❌ Backend not accessible: {e}")
    print("Make sure backend is running on port 8001")
    exit(1)

# Note: Actual validation requires authentication
print("\n📝 To test email validation:")
print("1. Open frontend at http://localhost:5173")
print("2. Login with your credentials")
print("3. Try validating an email")
print("4. Check the backend console logs for:")
print("   'INFO: Using ASYNC PRODUCTION validator'")
print("   'PERF: Validated X emails in Y.YYs'")

print("\n" + "="*70)
print("Integration complete! Backend should now use async validator.")
print("="*70 + "\n")
