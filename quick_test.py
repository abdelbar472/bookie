# quick_test.py - Test all endpoints and show logs
import requests
import time
import json

BASE_URL = "http://127.0.0.1:8001/api/v1"

print("\n" + "="*70)
print("🧪 TESTING ALL FASTAPI AUTH ENDPOINTS - WATCH YOUR UVICORN TERMINAL!")
print("="*70 + "\n")

def test_endpoint(name, method, url, data=None, headers=None):
    print(f"🔍 Testing {name}...")
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers)

        print(f"   Status: {response.status_code}")
        if response.status_code < 400:
            print("   ✅ SUCCESS")
        else:
            print("   ❌ FAILED")
            print(f"   Error: {response.text}")
        print()
        return response
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
        print()
        return None

# 1. Health Check
test_endpoint("Health Check", "GET", f"{BASE_URL}/health")

# 2. User Registration
user_data = {
    "email": "testuser@example.com",
    "username": "testuser",
    "password": "SecurePass123!",
    "full_name": "Test User"
}
response = test_endpoint("User Registration", "POST", f"{BASE_URL}/register", user_data)

# 3. Login
login_data = {
    "username": "testuser",
    "password": "SecurePass123!"
}
response = test_endpoint("User Login", "POST", f"{BASE_URL}/login", login_data)

# 4. Get Profile (if login successful)
if response and response.status_code == 200:
    tokens = response.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    headers = {"Authorization": f"Bearer {access_token}"}
    test_endpoint("Get User Profile", "GET", f"{BASE_URL}/me", headers=headers)

    # 5. Refresh Token
    refresh_data = {"refresh_token": refresh_token}
    test_endpoint("Refresh Token", "POST", f"{BASE_URL}/refresh", refresh_data)

    # 6. Logout
    test_endpoint("Logout", "POST", f"{BASE_URL}/logout", refresh_data)

print("="*70)
print("✅ ALL ENDPOINTS TESTED! Check your uvicorn terminal for detailed logs!")
print("="*70 + "\n")

print("📋 AVAILABLE ENDPOINTS:")
print("   GET  /api/v1/health          - Health check")
print("   POST /api/v1/register        - Register new user")
print("   POST /api/v1/login           - Login and get tokens")
print("   POST /api/v1/refresh         - Refresh access token")
print("   POST /api/v1/logout          - Logout (revoke refresh token)")
print("   GET  /api/v1/me              - Get current user profile")
print()
print("🌐 Interactive API Docs: http://127.0.0.1:8001/docs")
print("="*70 + "\n")
