"""
E2E test – starts both services as subprocesses, runs full flow, tears down.
Run from D:\\codes\\fastapi_auth:
    python e2e_test.py
"""
import subprocess
import sys
import time
import requests
import os

BASE = "http://localhost"
AUTH = f"{BASE}:8001/api/v1"
USER = f"{BASE}:8002/api/v1"

def start(module, port):
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"{module}:app", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

def wait_up(url, retries=15, delay=1):
    for _ in range(retries):
        try:
            requests.get(url, timeout=2)
            return True
        except Exception:
            time.sleep(delay)
    return False

def ok(label, r, expected=200):
    assert r.status_code == expected, f"{label}: got {r.status_code} - {r.text}"
    print(f"  OK  {label}: {r.status_code}")
    return r.json()

auth_proc = start("auth.main", 8001)
user_proc = start("user.main", 8002)

print(">> Waiting for services...")
assert wait_up(f"{AUTH}/health"), "Auth service did not start!"
assert wait_up(f"{USER}/health"), "User service did not start!"
print(">> Both services up\n")

try:
    # 1. Health
    ok("Auth health", requests.get(f"{AUTH}/health"))
    ok("User health", requests.get(f"{USER}/health"))

    # 2. Register
    r = requests.post(f"{AUTH}/register", json={
        "email": "e2e@test.com", "username": "e2euser",
        "full_name": "E2E Tester", "password": "pass1234"
    })
    if r.status_code == 201:
        ok("Register", r, 201)
    else:
        print(f"  INFO  Register: {r.status_code} (user probably exists already)")

    # 3. Login
    body = ok("Login", requests.post(f"{AUTH}/login", json={
        "username": "e2euser", "password": "pass1234"
    }))
    access  = body["access_token"]
    refresh = body["refresh_token"]
    hdrs    = {"Authorization": f"Bearer {access}"}
    print(f"     access_token : {access[:40]}…")
    print(f"     refresh_token: {refresh[:20]}…")

    # 4. Verify token (Auth service)
    v = ok("Verify token (Auth)", requests.get(f"{AUTH}/verify", headers=hdrs))
    print(f"     verified as  : {v['username']}")

    # 5. GET /me (User service – gRPC validation)
    me = ok("GET /me (User svc)", requests.get(f"{USER}/me", headers=hdrs))
    print(f"     username: {me['username']} | bio: {me['bio']!r}")

    # 6. PATCH /me
    patched = ok("PATCH /me", requests.patch(f"{USER}/me", headers=hdrs, json={
        "bio": "Hello from E2E!", "avatar_url": "https://example.com/a.png"
    }))
    print(f"     bio updated to: {patched['bio']!r}")

    # 7. Refresh via User service (delegates to Auth via gRPC)
    ref = ok("Refresh (User→Auth gRPC)", requests.post(f"{USER}/refresh", json={
        "refresh_token": refresh
    }))
    new_access  = ref["access_token"]
    new_refresh = ref["refresh_token"]
    print(f"     new access_token : {new_access[:40]}…")

    # 8. GET /me with new token
    me2 = ok("GET /me (new token)", requests.get(f"{USER}/me", headers={
        "Authorization": f"Bearer {new_access}"
    }))
    print(f"     bio still:  {me2['bio']!r}")

    # 9. Logout
    lo = ok("Logout", requests.post(f"{AUTH}/logout",
        headers={"Authorization": f"Bearer {new_access}"},
        json={"refresh_token": new_refresh}
    ))
    print(f"     {lo['message']}")

    print("\n*** ALL E2E TESTS PASSED! ***")

finally:
    auth_proc.terminate()
    user_proc.terminate()
    print("\n-- Services stopped.")

