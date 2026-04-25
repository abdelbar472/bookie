# frontend/server.py
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")

@app.get("/")
async def root():
    return FileResponse(str(BASE_DIR / "index.html"))


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    requested = BASE_DIR / full_path
    if requested.is_file():
        return FileResponse(str(requested))
    if full_path.startswith("static/"):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(BASE_DIR / "index.html"))

# Run: python -m uvicorn frontend.server:app --port 8080 --reload