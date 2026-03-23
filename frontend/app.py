from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

SERVICE_BASE_URLS = {
    "auth": "http://127.0.0.1:8001",
    "user": "http://127.0.0.1:8002",
    "follow": "http://127.0.0.1:8003",
    "book": "http://127.0.0.1:8004",
    "social": "http://127.0.0.1:8005",

}

app = FastAPI(title="Books Frontend", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


PAGE_MAP = {
    "index": "index.html",
    "auth": "auth.html",
    "user": "user.html",
    "follow": "follow.html",
    "book": "book.html",
    "social": "social.html",
    "reviews": "reviews.html",
    "shelves": "shelves.html",
}


def _page_file(name: str) -> Path:
    filename = PAGE_MAP.get(name)
    if not filename:
        raise HTTPException(status_code=404, detail="Page not found")
    return STATIC_DIR / filename


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_page_file("index"))


@app.get("/{page}")
async def multipage(page: str) -> FileResponse:
    return FileResponse(_page_file(page))


@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(service: str, path: str, request: Request):
    base_url = SERVICE_BASE_URLS.get(service)
    if not base_url:
        raise HTTPException(status_code=404, detail="Unknown service")

    target_url = f"{base_url}/{path}"
    query = request.url.query
    if query:
        target_url = f"{target_url}?{query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    body = await request.body()
    timeout = httpx.Timeout(30.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.request(
                method=request.method,
                url=target_url,
                content=body if body else None,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": f"Upstream service unavailable: {exc}"},
        )

    excluded_headers = {"content-encoding", "transfer-encoding", "connection"}
    resp_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in excluded_headers
    }
    return Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers)

