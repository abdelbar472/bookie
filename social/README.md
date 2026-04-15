# Social Service

Social interactions for books.

## Features

- Like/unlike books
- Rate books from 0.5 to 5.0 (step 0.5)
- Create/update/delete reviews
- Reply to reviews (nested reviews)
- Like/unlike individual reviews
- Create shelves (playlists) and add/remove books

## Auth and Integration

- Uses Auth gRPC for Bearer token validation
- Uses Book gRPC to ensure an ISBN exists before write operations
- Sends interaction events (`user_id`, `book_id`, `interaction_type`, `value`) to `rag_service` via gRPC
- `book_id` is the shared identifier Social sends so RAG can update user taste signals

## Run

```powershell
cd D:\codes\fastapi_auth
.\run_social.ps1
```

## Main Endpoints

- `POST /api/v1/social/likes/{isbn}`
- `PUT /api/v1/social/ratings/{isbn}`
- `POST /api/v1/social/reviews`
- `POST /api/v1/social/reviews/{review_id}/replies`
- `POST /api/v1/social/reviews/{review_id}/likes`
- `POST /api/v1/social/shelves`
- `POST /api/v1/social/shelves/{shelf_id}/items`

