"""
Book Service V3 - Complete Implementation
Rich Data Enrichment + MongoDB Catalog + gRPC
"""
__version__ = "3.0.0"
__author__ = "Bookie Team"

from .schemas import (
    AuthorProfile,
    AuthorSearchResponse,
    BookProfile,
    BookSearchResponse,
    SeriesProfile,
    SeriesSearchResponse,
)
from .enrichment_engine import enrichment_engine

__all__ = [
    "BookProfile",
    "AuthorProfile",
    "SeriesProfile",
    "BookSearchResponse",
    "AuthorSearchResponse",
    "SeriesSearchResponse",
    "enrichment_engine",
]