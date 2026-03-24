"""
RAG router adapter.

This wraps the legacy RAG route registrations into a standalone APIRouter
so the service can use the same `main.py + routers.py` layout as other services.
"""

from fastapi import APIRouter

from .service import app as legacy_app

router = APIRouter()
router.include_router(legacy_app.router)

