# test_api.py - Simple API test script
import requests
import json

BASE_URL = "http://127.0.0.1:8001/api/v1"


def test_health():
    """Test health endpoint"""
    response = requests.get(f"{BASE_URL}/health")
    print(f"Health Check: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    return response.status_code == 200


def test_register():
    """Test user registration"""
    user_data = {
        "email": "testuser@example.com",
        "username": "testuser",
        "password": "SecurePassword123!",
        "full_name": "Test User"
    }
    response = requests.post(f"{BASE_URL}/register", json=user_data)
    print(f"\nRegister: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    return response.status_code == 201


def test_login():
    """Test user login"""
    login_data = {
        "username": "testuser",
        "password": "SecurePassword123!"
    }
    response = requests.post(f"{BASE_URL}/login", json=login_data)
    print(f"\nLogin: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))

    if response.status_code == 200:
        return data.get("access_token"), data.get("refresh_token")
    return None, None


def test_get_profile(access_token):
    """Test getting user profile"""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{BASE_URL}/me", headers=headers)
    print(f"\nGet Profile: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    return response.status_code == 200


def test_refresh_token(refresh_token):
    """Test token refresh"""
    refresh_data = {"refresh_token": refresh_token}
    response = requests.post(f"{BASE_URL}/refresh", json=refresh_data)
    print(f"\nRefresh Token: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    return response.status_code == 200


if __name__ == "__main__":
    print("=" * 50)
    print("Testing FastAPI Auth Microservice")
    print("=" * 50)

    # Test health
    test_health()

    # Test registration
    test_register()

    # Test login
    access_token, refresh_token = test_login()

    if access_token:
        # Test profile
        test_get_profile(access_token)

        # Test refresh
        if refresh_token:
            test_refresh_token(refresh_token)

    print("\n" + "=" * 50)
    print("Tests completed!")
    print("=" * 50)

