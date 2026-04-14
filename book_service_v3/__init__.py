"""
Book Service V3 - Rich Data Enrichment for RAG
"""
__version__ = "3.0.0"
__author__ = "Bookie Team"

from .schemas import BookProfile, AuthorProfile, SeriesProfile
from .enrichment_engine import enrichment_engine

__all__ = [
    "BookProfile",
    "AuthorProfile",
    "SeriesProfile",
    "enrichment_engine",
]