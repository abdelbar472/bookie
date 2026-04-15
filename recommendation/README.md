# Recommendation Service

Standalone recommendation microservice.

- Owns user profile shaping and ranking logic.
- Uses `rag_service` as retrieval backend (`/api/v1/rag/similar/{work_id}`).
- Exposes gRPC `RecommendationService` for `rag_service` on port `50058`.

## Run

```powershell
cd D:\codes\fastapi_auth
.\run_recommendation.ps1
```

## Endpoints

- `POST /api/v1/recommend`
- `GET /api/v1/health`
- gRPC: `GetRecommendations` (`proto/recommendation.proto`)

