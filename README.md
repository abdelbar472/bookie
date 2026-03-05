# FastAPI Microservices — Auth + User

A production-ready microservice architecture using **FastAPI**, **SQLite (async)**, and **gRPC** for internal service communication.

Two independent services that work together: one owns identity, one owns profiles. They never share a database or a secret key.

---

## Why this design?

### 1. Separation of concerns
Most tutorials dump auth and user logic into one monolith. Here they are split intentionally:

- **Auth Service** — the single source of truth for identity. It is the only service that ever touches `SECRET_KEY`, creates JWTs, or stores passwords.
- **User Service** — owns profile data (bio, avatar, etc). It never sees the secret key. It cannot forge tokens. It simply asks Auth *"is this token valid?"* and gets a user back.

This means if you add a third service tomorrow (orders, payments, etc.) it does the same thing — calls Auth via gRPC to validate — and never needs the secret key distributed to it.

### 2. gRPC for internal communication — not HTTP
When the User service needs to validate a token, it does **not** make an HTTP call to Auth. It uses **gRPC**:

| | HTTP (internal) | gRPC |
|---|---|---|
| Protocol | Text (JSON) | Binary (Protobuf) |
| Speed | Slower | ~5–10× faster |
| Contract | Informal | Strict `.proto` schema |
| Code generation | Manual | Auto-generated stubs |
| Error handling | Status codes + JSON | Typed status codes |

The `.proto` file acts as a formal contract between services. If Auth changes what it returns, the proto file changes, the stubs are regenerated, and the compiler tells you immediately what broke.

### 3. Token validation without distributing the secret
A common bad pattern is copying `SECRET_KEY` into every service so each can decode JWTs itself. This creates N copies of your most sensitive secret.

Here, only Auth has `SECRET_KEY`. Every other service sends the raw token to Auth via gRPC and gets back a verified user object. The secret never leaves Auth.

```
User Service receives:  "Bearer eyJhbGci..."
                               ↓  gRPC ValidateToken()
Auth Service returns:   { valid: true, user: { id: 1, username: "alice", ... } }
```

### 4. Token rotation built in
Refresh tokens are stored in the database and rotated on every use — the old one is revoked, a new one is issued. This means:
- Stolen refresh tokens can only be used once
- You can log a user out from all devices by revoking all their tokens

### 5. Each service has its own database
Auth owns `auth_service.db` (users, refresh tokens).  
User owns `user_service.db` (profiles).

They share no tables. If you later move Auth to PostgreSQL, User is unaffected. If User's DB goes down, login still works.

---

## Architecture

```
┌─────────────────────────────────┐      ┌─────────────────────────────────┐
│        Auth Service             │      │        User Service              │
│  HTTP  http://localhost:8001    │      │  HTTP  http://localhost:8002     │
│  gRPC  localhost:50051          │      │                                  │
│                                 │      │  All token checks → gRPC        │
│  POST /api/v1/register          │◄─────│  User service has NO SECRET_KEY  │
│  POST /api/v1/login             │ gRPC │                                  │
│  POST /api/v1/refresh           │      │  GET    /api/v1/health           │
│  POST /api/v1/logout            │      │  GET    /api/v1/me               │
│  GET  /api/v1/verify            │      │  PATCH  /api/v1/me               │
│  GET  /api/v1/health            │      │  POST   /api/v1/refresh          │
│                                 │      │  GET    /api/v1/users/{id}       │
│  DB: auth_service.db            │      │  DB: user_service.db             │
└─────────────────────────────────┘      └─────────────────────────────────┘
```

### gRPC contract (`proto/auth.proto`)

| RPC           | Request               | Response                    | Used by              |
|---------------|-----------------------|-----------------------------|----------------------|
| ValidateToken | access_token: string  | valid, error, UserPayload   | User svc – every req |
| RefreshToken  | refresh_token: string | access_token, refresh_token | User svc /refresh    |
| GetUser       | user_id: int32        | UserPayload                 | User svc /users/{id} |

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | FastAPI | Async-native, auto OpenAPI docs, fast |
| ORM | SQLModel | Pydantic + SQLAlchemy in one, async support |
| Database | SQLite (aiosqlite) | Zero setup, swap to Postgres by changing `DATABASE_URL` |
| Auth | python-jose + passlib | JWT + bcrypt, industry standard |
| Internal comms | gRPC (grpcio) | Typed, fast, contract-first |
| Config | pydantic-settings | `.env` files with type validation |

---

## Quick start

**Terminal 1 – Auth service**
```powershell
cd D:\codes\fastapi_auth
.\run_auth.ps1
# or: python -m uvicorn auth.main:app --port 8001 --reload
```

**Terminal 2 – User service**
```powershell
cd D:\codes\fastapi_auth
.\run_user.ps1
# or: python -m uvicorn user.main:app --port 8002 --reload
```

Swagger UIs:
- Auth: http://localhost:8001/docs
- User: http://localhost:8002/docs

---

## Postman

Import `postman_collection.json`.

The **collection-level pre-request script** handles auth automatically for every request:
- Skips public paths (`/login`, `/register`, `/health`, `/refresh`)
- Attaches `Bearer <access_token>` to all other requests
- Auto-refreshes the access token via Auth `/refresh` when it is missing

**Run order:**
1. Auth → Register
2. Auth → Login ← tokens saved to collection variables automatically
3. User → Get My Profile ← token attached automatically
4. User → Update My Profile
5. User → Refresh Token (routes through User → Auth gRPC internally)
6. Auth → Logout

---

## E2E test

Starts both services as subprocesses, runs the full flow, tears everything down:

```powershell
cd D:\codes\fastapi_auth
$env:PYTHONUTF8 = "1"
python e2e_test.py
```

---

## File layout

```
fastapi_auth/
├── proto/
│   ├── auth.proto          # gRPC service definition (source of truth)
│   ├── auth_pb2.py         # generated — do not edit
│   └── auth_pb2_grpc.py    # generated — do not edit
│
├── auth/                   # ── Auth Service ──────────────────────
│   ├── .env                # SECRET_KEY, DATABASE_URL, GRPC_PORT
│   ├── config.py           # pydantic-settings
│   ├── models.py           # User, RefreshToken (SQLModel tables)
│   ├── schemas.py          # Pydantic request/response shapes
│   ├── database.py         # async engine + session factory
│   ├── services.py         # JWT encode/decode, bcrypt, DB queries
│   ├── routers.py          # HTTP: register, login, refresh, logout, verify
│   ├── grpc_server.py      # gRPC: ValidateToken, RefreshToken, GetUser
│   └── main.py             # FastAPI app — lifespan starts gRPC server
│
├── user/                   # ── User Service ──────────────────────
│   ├── .env                # AUTH_GRPC_HOST, AUTH_GRPC_PORT, DATABASE_URL
│   ├── config.py
│   ├── models.py           # UserProfile — bio, avatar_url
│   ├── schemas.py
│   ├── database.py
│   ├── services.py         # profile get/update
│   ├── routers.py          # HTTP: me, patch me, refresh, users/{id}
│   ├── grpc_client.py      # thin wrapper around gRPC stub
│   └── main.py             # FastAPI app
│
├── postman_collection.json # ready-to-import collection with auto-auth script
├── e2e_test.py             # full flow test — no manual steps needed
├── run_auth.ps1            # one-command start for Auth
├── run_user.ps1            # one-command start for User
└── requirements.txt
```

---

## Adding a third service

This is the whole point of the design. To add e.g. an Orders service:

1. Copy `user/grpc_client.py` into your new service
2. Call `validate_token(token)` in your auth dependency
3. Done — no secret key needed, no copy-paste of JWT logic

The Auth service becomes the central identity authority for your entire platform.

