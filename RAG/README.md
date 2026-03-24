# RAG Service

Template-aligned RAG service entrypoint:
- `RAG/main.py` (FastAPI app + lifespan + middleware)
- `RAG/routers.py` (router module)
- `RAG/service.py` (legacy route/function implementation reused by adapter)

## Dependencies

- Qdrant (vector store)
- MongoDB (reading list + taste profiles)
- Book service gRPC (metadata enrichment)

## Run

```powershell
Set-Location "D:\codes\fastapi_auth"
.\run_rag.ps1
```

## Quick checks

```powershell
Set-Location "D:\codes\fastapi_auth"
.\.venv\Scripts\python.exe -m py_compile RAG\main.py RAG\routers.py RAG\service.py RAG\mongo_service.py
```

```powershell
Set-Location "D:\codes\fastapi_auth"
.\.venv\Scripts\python.exe -u -c "from RAG.main import app; print(len(app.routes))"
```

