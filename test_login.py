import requests
import json

# Test login endpoint
url = "http://localhost:8001/login"
data = {
    "email": "ssharma636076@gmail.com",
    "password": "Shiva@123"
}

print("Testing login endpoint...")
print(f"URL: {url}")
print(f"Data: {json.dumps(data, indent=2)}")
print("-" * 60)

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
    print(f"Response text: {response.text if 'response' in locals() else 'No response'}")
