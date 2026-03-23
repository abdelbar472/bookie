#!/usr/bin/env python3
"""
Book Recommendation System with Qdrant
WINDOWS DOCKER VERSION - Handles API key authentication properly
"""

import os
import json
import time
import requests
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
    ScoredPoint
)
from tqdm import tqdm

# ============================================================
# CONFIGURATION
# ============================================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
COLLECTION_NAME = "books"

# Qdrant Docker configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")  # For Docker with auth enabled

# Local fallback path (if Docker is not available)
QDRANT_LOCAL_PATH = os.getenv(
    "QDRANT_LOCAL_PATH",
    os.path.join(os.path.dirname(__file__), "qdrant_local")
)

print("🔧 Loading embedding model...")
encoder = SentenceTransformer('all-MiniLM-L6-v2')
VECTOR_SIZE = encoder.get_sentence_embedding_dimension()
print(f"✅ Model loaded. Vector size: {VECTOR_SIZE}")

# Global client
qdrant_client: Optional[QdrantClient] = None

# ============================================================
# QDRANT CLIENT - WINDOWS DOCKER SUPPORT
# ============================================================

def get_qdrant_client() -> QdrantClient:
    """
    Create Qdrant client with Windows Docker support.
    Tries Docker first, then falls back to local if needed.
    """
    global qdrant_client

    if qdrant_client is not None:
        return qdrant_client

    # Try Docker Qdrant first (with optional API key)
    try:
        print(f"🔌 Trying to connect to Docker Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")

        # If API key is set, use it; otherwise connect without auth
        if QDRANT_API_KEY:
            client = QdrantClient(
                host=QDRANT_HOST,
                port=QDRANT_PORT,
                api_key=QDRANT_API_KEY,
                timeout=10.0
            )
            print("   Using API key authentication")
        else:
            client = QdrantClient(
                host=QDRANT_HOST,
                port=QDRANT_PORT,
                timeout=10.0
            )
            print("   No API key set (connecting without authentication)")

        # Test connection
        client.get_collections()
        print(f"✅ Connected to Docker Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
        qdrant_client = client
        return client

    except Exception as exc:
        print(f"⚠️  Docker Qdrant unavailable: {exc}")
        print(f"   Make sure Docker is running and Qdrant container is started:")
        print(f"   docker run -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant")
        print(f"\n💾 Falling back to local Qdrant storage...")

    # Use local mode as fallback
    os.makedirs(QDRANT_LOCAL_PATH, exist_ok=True)
    client = QdrantClient(path=QDRANT_LOCAL_PATH)
    print(f"✅ Using local Qdrant at: {QDRANT_LOCAL_PATH}")
    qdrant_client = client
    return client


# ============================================================
# FALLBACK DATASET
# ============================================================

def get_fallback_books() -> List[Dict]:
    """Local dataset when APIs fail."""

    books = [
        {
            "id": "dune-001",
            "title": "Dune",
            "authors": "Frank Herbert",
            "description": "Epic science fiction about politics, prophecy, and ecology on the desert planet Arrakis.",
            "categories": ["Science Fiction", "Politics"],
            "published_date": "1965",
            "page_count": 412,
            "average_rating": 4.2,
        },
        {
            "id": "1984-001",
            "title": "1984",
            "authors": "George Orwell",
            "description": "A dystopian novel about surveillance, truth manipulation, and authoritarian power.",
            "categories": ["Dystopian", "Fiction"],
            "published_date": "1949",
            "page_count": 328,
            "average_rating": 4.1,
        },
        {
            "id": "neuro-001",
            "title": "Neuromancer",
            "authors": "William Gibson",
            "description": "Cyberpunk classic featuring AI, hackers, and corporate dystopia.",
            "categories": ["Science Fiction", "Cyberpunk"],
            "published_date": "1984",
            "page_count": 271,
            "average_rating": 3.9,
        },
        {
            "id": "foundation-001",
            "title": "Foundation",
            "authors": "Isaac Asimov",
            "description": "Mathematical sociology predicts the fall of galactic empires.",
            "categories": ["Science Fiction"],
            "published_date": "1951",
            "page_count": 244,
            "average_rating": 4.2,
        },
        {
            "id": "left-001",
            "title": "The Left Hand of Darkness",
            "authors": "Ursula K. Le Guin",
            "description": "A thought-provoking exploration of gender, society, and diplomacy.",
            "categories": ["Science Fiction", "Philosophy"],
            "published_date": "1969",
            "page_count": 304,
            "average_rating": 4.0,
        },
        {
            "id": "sapiens-001",
            "title": "Sapiens",
            "authors": "Yuval Noah Harari",
            "description": "A sweeping history of humankind, from evolution to modern society.",
            "categories": ["History", "Nonfiction"],
            "published_date": "2011",
            "page_count": 443,
            "average_rating": 4.4,
        },
    ]

    for book in books:
        book["embed_text"] = (
            f"Title: {book['title']}. "
            f"Author: {book['authors']}. "
            f"Description: {book['description']}. "
            f"Genres: {', '.join(book['categories'])}"
        )
        book["author_text"] = (
            f"Author: {book['authors']}. "
            f"Style: {get_author_style(book['authors'])}. "
            f"Genres: {', '.join(book['categories'])}"
        )

    return books


def get_author_style(author: str) -> str:
    """Get writing style description."""
    styles = {
        "Frank Herbert": "complex world-building, political intrigue, ecological themes",
        "George Orwell": "dystopian social commentary, clear direct prose",
        "William Gibson": "noir atmosphere, technological prophecy, cyberpunk aesthetics",
        "Isaac Asimov": "hard science, logical puzzle-solving, galactic scope",
        "Ursula K. Le Guin": "anthropological SF, philosophical exploration, gender themes",
        "Yuval Noah Harari": "interdisciplinary synthesis, big history, thought experiments",
    }
    return styles.get(author, "varied literary style")


# ============================================================
# GOOGLE BOOKS API
# ============================================================

def fetch_google_books(query: str, max_results: int = 5) -> List[Dict]:
    """Fetch from Google Books API."""

    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_api_key_here":
        return []

    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        'q': query,
        'key': GOOGLE_API_KEY,
        'maxResults': max_results,
        'printType': 'books'
    }

    try:
        time.sleep(0.5)
        response = requests.get(url, params=params, timeout=10)

        if response.status_code in [429, 403, 401]:
            return []

        response.raise_for_status()
        data = response.json()

        books = []
        for item in data.get('items', []):
            volume = item.get('volumeInfo', {})
            authors = volume.get('authors', ['Unknown'])

            book = {
                'id': item.get('id', f"gb_{len(books)}"),
                'title': volume.get('title', 'Unknown'),
                'authors': ', '.join(authors),
                'description': volume.get('description', '')[:500],
                'categories': volume.get('categories', []),
                'published_date': volume.get('publishedDate', 'Unknown'),
                'page_count': volume.get('pageCount', 0) or 0,
                'average_rating': volume.get('averageRating', 0) or 0,
            }

            book['embed_text'] = f"Title: {book['title']}. Author: {book['authors']}. Description: {book['description']}. Genres: {', '.join(book['categories'])}"
            book['author_text'] = f"Author: {book['authors']}. Style: {get_author_style(book['authors'])}. Genres: {', '.join(book['categories'])}"

            books.append(book)

        return books

    except Exception as e:
        return []


# ============================================================
# EMBEDDINGS
# ============================================================

def generate_embeddings(texts: List[str]) -> np.ndarray:
    """Generate embeddings."""
    if not texts:
        return np.empty((0, VECTOR_SIZE), dtype=np.float32)

    embeddings = []
    batch_size = 32

    for i in tqdm(range(0, len(texts), batch_size), desc="🔢 Generating embeddings"):
        batch = texts[i:i+batch_size]
        emb = encoder.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        embeddings.extend(emb)

    return np.array(embeddings)


# ============================================================
# QDRANT OPERATIONS
# ============================================================

def setup_collection():
    """Setup Qdrant collection."""

    client = get_qdrant_client()

    # Delete if exists
    try:
        collections = client.get_collections()
        existing = [c.name for c in collections.collections]

        if COLLECTION_NAME in existing:
            client.delete_collection(COLLECTION_NAME)
            print(f"🗑️  Deleted existing collection: {COLLECTION_NAME}")
    except Exception as e:
        pass

    # Create with named vectors
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "book_content": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            "author_style": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        }
    )
    print(f"✅ Created collection: {COLLECTION_NAME}")


def upload_books(books: List[Dict], book_vecs: np.ndarray, author_vecs: np.ndarray):
    """Upload books."""

    client = get_qdrant_client()

    points = []
    for i, (book, bv, av) in enumerate(zip(books, book_vecs, author_vecs)):
        primary_author = book['authors'].split(',')[0] if ',' in book['authors'] else book['authors']

        point = PointStruct(
            id=i,
            vector={
                "book_content": bv.tolist(),
                "author_style": av.tolist()
            },
            payload={
                'title': book['title'],
                'authors': book['authors'],
                'author_name': primary_author,
                'description': book['description'][:300] if book['description'] else '',
                'categories': book['categories'],
                'published_date': book['published_date'],
                'page_count': int(book['page_count']),
                'average_rating': float(book['average_rating']),
            }
        )
        points.append(point)

    # Upload
    batch_size = 100
    for i in tqdm(range(0, len(points), batch_size), desc="☁️  Uploading to Qdrant"):
        batch = points[i:i+batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)

    print(f"✅ Uploaded {len(points)} books")


# ============================================================
# SEARCH (FIXED for qdrant-client 1.10+)
# ============================================================

def search_content(query: str, limit: int = 5, filters: Optional[Dict] = None):
    """Search by book content."""

    client = get_qdrant_client()
    query_vec = encoder.encode(query).tolist()

    # Build filter
    search_filter = None
    if filters:
        conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]
        search_filter = Filter(must=conditions)

    # Use query_points (new API for qdrant-client 1.10+)
    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vec,
        using="book_content",
        query_filter=search_filter,
        limit=limit,
        with_payload=True
    )

    return result.points


def search_author_style(query: str, limit: int = 5, filters: Optional[Dict] = None):
    """Search by author style."""

    client = get_qdrant_client()
    query_vec = encoder.encode(query).tolist()

    search_filter = None
    if filters:
        conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]
        search_filter = Filter(must=conditions)

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vec,
        using="author_style",
        query_filter=search_filter,
        limit=limit,
        with_payload=True
    )

    return result.points


def find_similar_authors(author_name: str, limit: int = 5):
    """Find similar authors."""

    client = get_qdrant_client()

    # Get book by author
    scroll_result = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[FieldCondition(key="author_name", match=MatchValue(value=author_name))]
        ),
        limit=1,
        with_vectors=True
    )

    if not scroll_result[0]:
        print(f"   ⚠️  No books found by: {author_name}")
        return []

    book = scroll_result[0][0]
    author_vec = book.vector['author_style']

    # Search similar
    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=author_vec,
        using="author_style",
        query_filter=Filter(
            must_not=[FieldCondition(key="author_name", match=MatchValue(value=author_name))]
        ),
        limit=limit,
        with_payload=True
    )

    return result.points


def hybrid_search(query: str, content_weight: float = 0.7, author_weight: float = 0.3, limit: int = 5):
    """Hybrid search."""

    content_results = search_content(query, limit=limit*2)
    author_results = search_author_style(query, limit=limit*2)

    # Merge
    scored = {}
    for hit in content_results:
        scored[hit.id] = {'hit': hit, 'score': hit.score * content_weight}

    for hit in author_results:
        if hit.id in scored:
            scored[hit.id]['score'] += hit.score * author_weight
        else:
            scored[hit.id] = {'hit': hit, 'score': hit.score * author_weight}

    # Sort
    ranked = sorted(scored.values(), key=lambda x: x['score'], reverse=True)
    return [item['hit'] for item in ranked[:limit]]


# ============================================================
# OUTPUT
# ============================================================

def print_results(results, title):
    """Print results."""
    print(f"\n{'='*60}")
    print(f"📚 {title}")
    print('='*60)

    if not results:
        print("   No results found")
        return

    for i, hit in enumerate(results, 1):
        p = hit.payload
        print(f"\n{i}. {p['title']}")
        print(f"   👤 {p['authors']}")
        print(f"   📊 Score: {hit.score:.3f}")
        if p.get('categories'):
            print(f"   🏷️  {', '.join(p['categories'][:3])}")
        if p.get('average_rating'):
            print(f"   ⭐ {p['average_rating']}/5")


# ============================================================
# MAIN
# ============================================================

def main():
    """Main workflow."""

    print("\n" + "="*60)
    print("📖 BOOK RECOMMENDATION SYSTEM - WINDOWS DOCKER")
    print("="*60)

    # Check configuration
    print(f"\n⚙️  Configuration:")
    print(f"   QDRANT_HOST: {QDRANT_HOST}")
    print(f"   QDRANT_PORT: {QDRANT_PORT}")
    print(f"   QDRANT_API_KEY: {'Set' if QDRANT_API_KEY else 'Not set'}")

    # Get books
    print("\n📥 Step 1: Acquiring book data...")

    all_books = []

    if GOOGLE_API_KEY and GOOGLE_API_KEY != "your_api_key_here":
        print("   Trying Google Books API...")
        queries = ["science fiction classics", "dystopian novels"]
        for query in queries:
            books = fetch_google_books(query, max_results=3)
            all_books.extend(books)
            print(f"   ✓ Found {len(books)} books for '{query}'")
    else:
        print("   ℹ️  No Google API key set")

    if not all_books:
        print("\n   📚 Using fallback dataset...")
        all_books = get_fallback_books()

    # Deduplicate
    seen = set()
    books = [b for b in all_books if not (b['id'] in seen or seen.add(b['id']))]
    print(f"\n✅ Total unique books: {len(books)}")

    # Embeddings
    print("\n🔢 Step 2: Generating embeddings...")
    book_vecs = generate_embeddings([b['embed_text'] for b in books])
    author_vecs = generate_embeddings([b['author_text'] for b in books])

    # Setup Qdrant
    print("\n💾 Step 3: Setting up Qdrant...")
    setup_collection()

    # Upload
    print("\n☁️  Step 4: Uploading to Qdrant...")
    upload_books(books, book_vecs, author_vecs)

    # Demo
    print("\n🎯 Step 5: Running demos...")

    print_results(search_content("space exploration politics", limit=3),
                  "Content: 'space exploration politics'")

    print_results(search_author_style("philosophical dystopian", limit=3),
                  "Author Style: 'philosophical dystopian'")

    print_results(find_similar_authors("Frank Herbert", limit=3),
                  "Similar to 'Frank Herbert'")

    print_results(hybrid_search("complex world-building", 0.6, 0.4, 3),
                  "Hybrid: 'complex world-building'")

    print("\n" + "="*60)
    print("✅ COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()