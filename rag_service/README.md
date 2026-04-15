# RAG Service

This service is responsible for:

- Embedding and indexing **books** and **authors** into Qdrant
- Building user preference/taste signals from social interaction events
- HTTP API for semantic search/indexing (`/api/v1/rag/*`)
- Compatibility proxy for `/api/v1/rag/recommend` to the standalone `recommendation` service (via gRPC)
- gRPC API consumed by internal services (`RagService` in shared `proto/rag.proto`)

## Quick start

```powershell
python -m pip install -r rag_service/requirements.txt
python -m uvicorn rag_service.main:app --host 127.0.0.1 --port 8006 --reload
```

## Health check

- HTTP: `GET http://127.0.0.1:8006/api/v1/rag/health`
- HTTP alias: `GET http://127.0.0.1:8006/health`
- gRPC: `RagService` on port `50056`

