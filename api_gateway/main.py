from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio

app = FastAPI(title="API Gateway", description="Unified access to microservices")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service port mapping
SERVICE_PORTS = {
    "auth": 8001,
    "user": 8002,
    "follow": 8003,
    "social": 8004,
    "rag": 8005,
    "recommendation": 8006,
    "book": 8007,
}

@app.get("/")
async def root():
    return {"message": "API Gateway", "services": list(SERVICE_PORTS.keys())}

@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(service: str, path: str, request: Request):
    if service not in SERVICE_PORTS:
        return Response(status_code=404, content="Service not found")
    
    port = SERVICE_PORTS[service]
    url = f"http://localhost:{port}/{path}"
    
    # Get request data
    body = await request.body()
    headers = dict(request.headers)
    # Remove host header to avoid conflicts
    headers.pop("host", None)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                params=request.query_params,
            )
            return Response(
                status_code=response.status_code,
                content=response.content,
                headers=dict(response.headers),
            )
        except httpx.RequestError as exc:
            return Response(status_code=503, content=f"Service {service} unavailable: {exc}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
