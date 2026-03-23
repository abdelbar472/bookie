# Frontend (Bookbox)

A clean, Letterboxd-inspired frontend for the microservices app.

Now organized as a multipage UI for cleaner workflows.

## What it includes

- Dark, minimal UI for books and social interactions
- Multipage layout with dedicated service pages:
  - `/auth` Auth service actions (register/login/verify/logout)
  - `/user` User service actions (`/me`, update profile, lookup user)
  - `/follow` Follow service actions (follow/unfollow/check/stats/lists)
  - `/book` Book service actions (search/list/get book + authors/publishers)
  - `/social` Social service actions (likes/ratings/reviews/stats)
  - `/reviews` threaded review browsing/replies
  - `/shelves` shelf creation and shelf item management
  - `/` quick home for discovery
- Login form (uses Auth service)
- Book browsing (Book service)
- Like/rate/review for books (Social service)
- Nested replies and likes on reviews (Social service)
- Expand/collapse review threads for cleaner reading
- My Shelves panel (create shelf, add/remove selected book)
- Search + filter books (all/title/author/year)
- Built-in API proxy (`/api/{service}/...`) so browser requests stay same-origin

## Run

Start backend services first (`auth`, `user`, `follow`, `book`, `social`).

```powershell
cd D:\codes\fastapi_auth
.\run_frontend.ps1
```

Open:

- http://127.0.0.1:8080
- http://127.0.0.1:8080/auth
- http://127.0.0.1:8080/user
- http://127.0.0.1:8080/follow
- http://127.0.0.1:8080/book
- http://127.0.0.1:8080/social
- http://127.0.0.1:8080/reviews
- http://127.0.0.1:8080/shelves

## Quick smoke test

```powershell
cd D:\codes\fastapi_auth
python frontend\smoke_test.py
```

## Proxy map

- `/api/auth/*` -> `http://127.0.0.1:8001/*`
- `/api/user/*` -> `http://127.0.0.1:8002/*`
- `/api/follow/*` -> `http://127.0.0.1:8003/*`
- `/api/book/*` -> `http://127.0.0.1:8004/*`
- `/api/social/*` -> `http://127.0.0.1:8005/*`

