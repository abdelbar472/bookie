# Book Service V2

Book Service V2 ingests books from Google Books, enriches authors from Wikipedia, stores normalized documents in MongoDB, and pushes books to RAG for embedding.

## Data sources
- Google Books API (`/volumes`) for books and author discovery
- Wikipedia API (`/w/api.php` + `/api/rest_v1/page/summary/*`) for author bio/style

## Environment
Create or update `bookv2/.env`:

```env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=book_service_v2
GOOGLE_BOOKS_API_KEY=your_key_optional
WIKIPEDIA_LANG_FALLBACK=en,ar
RAG_GRPC_HOST=127.0.0.1
RAG_GRPC_PORT=50056
RAG_SYNC_ENABLED=true
# Backward-compatible alternative:
# GOOGLE_API_KEY=your_key_optional
```

## Run
```powershell
cd D:\codes\fastapi_auth
.\run_bookv2.ps1
```

Swagger:
- http://127.0.0.1:8007/docs

## Main endpoints
- `GET /api/v2/health`
- `POST /api/v2/import/books`
- `GET /api/v2/books`
- `GET /api/v2/books/{book_id}`
- `GET /api/v2/writers`
- `GET /api/v2/writers/{author_id}`
- `GET /api/v2/authors`
- `GET /api/v2/authors/{author_id}`
- `POST /api/v2/resolve`

## Notes
- Each newly discovered author is enriched from Wikipedia and expanded with up to 5 additional books via Google Books (`inauthor:"<name>"`).
- `POST /api/v2/resolve` checks MongoDB first; if a book/writer is missing it tries Wikipedia, stores the result, and forwards newly created books to recommendation.
- Imported books include `author_style` text used by RAG named vectors (`book_content` + `author_style`).
- BookV2 pushes imported books to RAG via gRPC `RagService.IndexBooks` (no internal HTTP hop).

