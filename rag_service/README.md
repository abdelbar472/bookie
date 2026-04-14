# RAG Service

This service provides:

- HTTP API for semantic search and recommendations (`/api/v1/rag/*`)
- gRPC API for indexing/search (`RAGService` in `proto/rag.proto`)
- Qdrant-backed vector search with OpenAI embeddings

## Quick start

```powershell
python -m pip install -r rag_service/requirements.txt
python -m grpc_tools.protoc -I rag_service/proto --python_out=rag_service/proto --grpc_python_out=rag_service/proto rag_service/proto/rag.proto
python -m uvicorn rag_service.main:app --host 0.0.0.0 --port 8001 --reload
```

## Health check

- HTTP: `GET http://127.0.0.1:8001/api/v1/rag/health`
- gRPC: `HealthCheck` RPC on port `50055`

