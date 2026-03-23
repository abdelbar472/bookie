#!/usr/bin/env python3
"""
Book Recommendation System with Qdrant
ENHANCED VERSION with Google Books API + Open Library author enrichment
"""

import os
import sys
import json
import time
import requests
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)
from tqdm import tqdm

# ============================================================
# CONFIGURATION
# ============================================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
COLLECTION_NAME = "books"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_LOCAL_PATH = os.getenv(
    "QDRANT_LOCAL_PATH",
    os.path.join(os.path.dirname(__file__), "qdrant_local")
)

print("🔧 Loading embedding model...")
encoder = SentenceTransformer('all-MiniLM-L6-v2')
VECTOR_SIZE = encoder.get_sentence_embedding_dimension()
print(f"✅ Model loaded. Vector size: {VECTOR_SIZE}")

qdrant_client: Optional[QdrantClient] = None

# ============================================================
# QDRANT CLIENT
# ============================================================

def get_qdrant_client():
    """Create Qdrant client with Docker/Windows support."""
    global qdrant_client

    if qdrant_client is not None:
        return qdrant_client

    # Try Docker first
    try:
        print(f"🔌 Connecting to Docker Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")

        if QDRANT_API_KEY:
            client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY, timeout=10.0)
        else:
            client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10.0)

        client.get_collections()
        print("✅ Connected to Docker Qdrant")
        qdrant_client = client
        return client

    except Exception as exc:
        print(f"⚠️  Docker Qdrant unavailable: {exc}")
        print(f"💾 Falling back to local Qdrant...")

    # Local fallback
    os.makedirs(QDRANT_LOCAL_PATH, exist_ok=True)
    client = QdrantClient(path=QDRANT_LOCAL_PATH)
    print(f"✅ Using local Qdrant")
    qdrant_client = client
    return client


# ============================================================
# AUTHOR ENRICHMENT (Open Library API)
# ============================================================

def fetch_author_from_openlibrary(author_name: str) -> Dict:
    """
    Fetch author biography and works from Open Library API.
    Returns enriched author data.
    """
    try:
        # Search for author
        search_url = f"https://openlibrary.org/search/authors.json?q={requests.utils.quote(author_name)}"
        response = requests.get(search_url, timeout=10)

        if response.status_code != 200:
            return {}

        data = response.json()
        if not data.get('docs'):
            return {}

        # Get first matching author
        author_doc = data['docs'][0]
        author_key = author_doc.get('key', '')

        if not author_key:
            return {}

        # Fetch detailed author info
        detail_url = f"https://openlibrary.org/authors/{author_key}.json"
        detail_resp = requests.get(detail_url, timeout=10)

        if detail_resp.status_code != 200:
            return {}

        detail_data = detail_resp.json()

        # Extract bio (can be string or dict)
        bio = detail_data.get('bio', '')
        if isinstance(bio, dict):
            bio = bio.get('value', '')

        # Get top work and work count
        return {
            'bio': bio[:500] if bio else '',
            'work_count': author_doc.get('work_count', 0),
            'top_work': author_doc.get('top_work', ''),
            'birth_date': detail_data.get('birth_date', ''),
            'death_date': detail_data.get('death_date', ''),
            'wikipedia': detail_data.get('wikipedia', ''),
            'alternate_names': detail_data.get('alternate_names', [])[:3],
        }

    except Exception as e:
        print(f"   ⚠️  Could not fetch author data for {author_name}: {e}")
        return {}


def enrich_author_data(book: Dict) -> Dict:
    """Enrich book with author data from Open Library."""

    author_name = book.get('authors', '').split(',')[0]  # Get first author
    if not author_name or author_name == 'Unknown':
        return book

    print(f"   🔍 Enriching: {author_name}")

    # Fetch from Open Library
    author_data = fetch_author_from_openlibrary(author_name)

    if author_data:
        # Create rich author text for embedding
        bio = author_data.get('bio', '')
        top_work = author_data.get('top_work', '')
        work_count = author_data.get('work_count', 0)

        # Enhanced author embedding text
        book['author_text'] = (
            f"Author: {book['authors']}. "
            f"Bio: {bio}. "
            f"Known for: {top_work}. "
            f"Works: {work_count} books. "
            f"Genres: {', '.join(book.get('categories', []))}"
        )

        # Store additional metadata
        book['author_bio'] = bio
        book['author_top_work'] = top_work
        book['author_work_count'] = work_count
        book['author_birth_date'] = author_data.get('birth_date', '')

        print(f"      ✓ Bio: {bio[:60]}..." if len(bio) > 60 else f"      ✓ Bio: {bio}")
    else:
        # Fallback to basic author text
        book['author_text'] = (
            f"Author: {book['authors']}. "
            f"Genres: {', '.join(book.get('categories', []))}"
        )
        book['author_bio'] = ''

    return book


# ============================================================
# GOOGLE BOOKS API (Enhanced)
# ============================================================

def fetch_google_books(query: str, max_results: int = 10) -> List[Dict]:
    """
    Fetch books from Google Books API with full metadata.
    """
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_api_key_here":
        print("   ⚠️  No GOOGLE_API_KEY set")
        return []

    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        'q': query,
        'key': GOOGLE_API_KEY,
        'maxResults': max_results,
        'printType': 'books',
        'langRestrict': 'en'
    }

    try:
        # Rate limiting - be nice to API
        time.sleep(0.3)

        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 429:
            print(f"   ⏳ Rate limited. Waiting...")
            time.sleep(2)
            return fetch_google_books(query, max_results)  # Retry once

        if response.status_code in [403, 401]:
            print(f"   ❌ API key invalid or quota exceeded")
            return []

        response.raise_for_status()
        data = response.json()

        books = []
        for item in data.get('items', []):
            volume = item.get('volumeInfo', {})

            # Extract all available metadata
            authors = volume.get('authors', ['Unknown'])
            categories = volume.get('categories', [])

            book = {
                'id': item.get('id'),
                'title': volume.get('title', 'Unknown'),
                'subtitle': volume.get('subtitle', ''),
                'authors': ', '.join(authors),
                'description': volume.get('description', '')[:800],  # Limit but keep substantial
                'categories': categories,
                'published_date': volume.get('publishedDate', 'Unknown'),
                'page_count': volume.get('pageCount', 0) or 0,
                'average_rating': volume.get('averageRating', 0) or 0,
                'ratings_count': volume.get('ratingsCount', 0) or 0,
                'maturity_rating': volume.get('maturityRating', ''),
                'language': volume.get('language', ''),
                'preview_link': volume.get('previewLink', ''),
                'info_link': volume.get('infoLink', ''),
                'thumbnail': volume.get('imageLinks', {}).get('thumbnail', ''),
                'publisher': volume.get('publisher', ''),
                'industry_identifiers': [
                    f"{id.get('type')}: {id.get('identifier')}"
                    for id in volume.get('industryIdentifiers', [])
                ],
            }

            # Create embedding text
            book['embed_text'] = (
                f"Title: {book['title']}. "
                f"Author: {book['authors']}. "
                f"Description: {book['description']}. "
                f"Genres: {', '.join(categories)}. "
                f"Publisher: {book['publisher']}."
            )

            # Initial author text (will be enriched)
            book['author_text'] = f"Author: {book['authors']}. Genres: {', '.join(categories)}"

            books.append(book)

        return books

    except requests.exceptions.RequestException as e:
        print(f"   ❌ Network error: {e}")
        return []
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return []


def fetch_multiple_queries(queries: List[str], max_per_query: int = 5) -> List[Dict]:
    """Fetch books from multiple queries with deduplication."""

    all_books = []
    seen_ids = set()

    for query in queries:
        print(f"\n📚 Fetching: '{query}'")
        books = fetch_google_books(query, max_results=max_per_query)

        for book in books:
            if book['id'] not in seen_ids:
                seen_ids.add(book['id'])
                all_books.append(book)

        print(f"   ✓ Added {len([b for b in books if b['id'] in seen_ids])} new books")

    return all_books


# ============================================================
# FALLBACK DATA
# ============================================================

def get_fallback_books():
    """Classic books as fallback."""
    books = [
        {
            "id": "dune-001", "title": "Dune", "authors": "Frank Herbert",
            "description": "Epic science fiction about politics and ecology on Arrakis.",
            "categories": ["Science Fiction"], "published_date": "1965",
            "page_count": 412, "average_rating": 4.2,
        },
        {
            "id": "1984-001", "title": "1984", "authors": "George Orwell",
            "description": "Dystopian novel about surveillance and authoritarian power.",
            "categories": ["Dystopian"], "published_date": "1949",
            "page_count": 328, "average_rating": 4.1,
        },
        {
            "id": "neuro-001", "title": "Neuromancer", "authors": "William Gibson",
            "description": "Cyberpunk classic with AI and hackers.",
            "categories": ["Cyberpunk"], "published_date": "1984",
            "page_count": 271, "average_rating": 3.9,
        },
        {
            "id": "foundation-001", "title": "Foundation", "authors": "Isaac Asimov",
            "description": "Mathematical sociology predicts fall of galactic empires.",
            "categories": ["Science Fiction"], "published_date": "1951",
            "page_count": 244, "average_rating": 4.2,
        },
        {
            "id": "left-001", "title": "The Left Hand of Darkness", "authors": "Ursula K. Le Guin",
            "description": "Exploration of gender, society, and diplomacy.",
            "categories": ["Science Fiction"], "published_date": "1969",
            "page_count": 304, "average_rating": 4.0,
        },
    ]

    for book in books:
        book["embed_text"] = f"Title: {book['title']}. Author: {book['authors']}. {book['description']}"
        book["author_text"] = f"Author: {book['authors']}. Genres: {', '.join(book['categories'])}"

    return books


# ============================================================
# EMBEDDINGS & QDRANT
# ============================================================

def generate_embeddings(texts: List[str]) -> np.ndarray:
    """Generate embeddings in batches."""
    if not texts:
        return np.empty((0, VECTOR_SIZE), dtype=np.float32)

    embeddings = []
    batch_size = 32

    for i in tqdm(range(0, len(texts), batch_size), desc="🔢 Embeddings"):
        batch = texts[i:i+batch_size]
        emb = encoder.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        embeddings.extend(emb)

    return np.array(embeddings)


def setup_collection(client):
    """Setup Qdrant collection."""
    try:
        collections = client.get_collections()
        existing = [c.name for c in collections.collections]
        if COLLECTION_NAME in existing:
            client.delete_collection(COLLECTION_NAME)
            print(f"🗑️  Deleted old collection")
    except:
        pass

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "book_content": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            "author_style": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        }
    )
    print(f"✅ Created collection: {COLLECTION_NAME}")


def upload_books(client, books, book_vecs, author_vecs):
    """Upload books to Qdrant."""
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
                'subtitle': book.get('subtitle', ''),
                'authors': book['authors'],
                'author_name': primary_author,
                'description': book['description'][:500] if book['description'] else '',
                'categories': book['categories'],
                'published_date': book['published_date'],
                'page_count': int(book['page_count']),
                'average_rating': float(book['average_rating']),
                'ratings_count': int(book.get('ratings_count', 0)),
                'publisher': book.get('publisher', ''),
                'thumbnail': book.get('thumbnail', ''),
                'preview_link': book.get('preview_link', ''),
                'language': book.get('language', ''),
                # Author enrichment data
                'author_bio': book.get('author_bio', '')[:300],
                'author_top_work': book.get('author_top_work', ''),
                'author_work_count': int(book.get('author_work_count', 0)),
                'author_birth_date': book.get('author_birth_date', ''),
            }
        )
        points.append(point)

    # Upload in batches
    batch_size = 100
    for i in tqdm(range(0, len(points), batch_size), desc="☁️  Uploading"):
        batch = points[i:i+batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)

    print(f"✅ Uploaded {len(points)} books")


# ============================================================
# SEARCH FUNCTIONS
# ============================================================

def search_content(client, query, limit=5, filters=None):
    """Search by book content."""
    query_vec = encoder.encode(query).tolist()

    search_filter = None
    if filters:
        conditions = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]
        search_filter = Filter(must=conditions)

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vec,
        using="book_content",
        query_filter=search_filter,
        limit=limit,
        with_payload=True
    )
    return result.points


def search_author_style(client, query, limit=5):
    """Search by author style."""
    query_vec = encoder.encode(query).tolist()

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vec,
        using="author_style",
        limit=limit,
        with_payload=True
    )
    return result.points


def find_similar_authors(client, author_name, limit=5):
    """Find books by authors with similar style."""
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


def hybrid_search(client, query, content_weight=0.7, author_weight=0.3, limit=5):
    """Hybrid search combining content and author style."""
    content_results = search_content(client, query, limit=limit*2)
    author_results = search_author_style(client, query, limit=limit*2)

    # Merge scores
    scored = {}
    for hit in content_results:
        scored[hit.id] = {'hit': hit, 'score': hit.score * content_weight}

    for hit in author_results:
        if hit.id in scored:
            scored[hit.id]['score'] += hit.score * author_weight
        else:
            scored[hit.id] = {'hit': hit, 'score': hit.score * author_weight}

    # Sort by combined score
    ranked = sorted(scored.values(), key=lambda x: x['score'], reverse=True)
    return [item['hit'] for item in ranked[:limit]]


# ============================================================
# OUTPUT
# ============================================================

def print_results(results, title):
    """Pretty print search results."""
    print(f"\n{'='*70}")
    print(f"📚 {title}")
    print('='*70)

    if not results:
        print("   No results found")
        return

    for i, hit in enumerate(results, 1):
        p = hit.payload
        print(f"\n{i}. {p['title']}")
        if p.get('subtitle'):
            print(f"   📖 {p['subtitle']}")
        print(f"   👤 {p['authors']}")
        print(f"   📊 Score: {hit.score:.3f}")
        if p.get('categories'):
            print(f"   🏷️  {', '.join(p['categories'][:3])}")
        if p.get('average_rating'):
            print(f"   ⭐ {p['average_rating']}/5 ({p.get('ratings_count', 0)} ratings)")
        if p.get('author_bio'):
            bio = p['author_bio'][:80] + "..." if len(p['author_bio']) > 80 else p['author_bio']
            print(f"   📝 Author Bio: {bio}")
        if p.get('author_work_count'):
            print(f"   📚 Author Works: {p['author_work_count']} books")


# ============================================================
# MAIN
# ============================================================

def main():
    """Complete workflow."""

    print("\n" + "="*70)
    print("📖 BOOK RECOMMENDATION SYSTEM - ENHANCED")
    print("   Google Books API + Open Library Author Enrichment")
    print("="*70)

    # Connect to Qdrant
    client = get_qdrant_client()
    if client is None:
        print("❌ Cannot connect to Qdrant")
        sys.exit(1)

    # Fetch books
    print("\n📥 Step 1: Fetching book data...")

    books = []

    if GOOGLE_API_KEY and GOOGLE_API_KEY != "your_api_key_here":
        # Multiple search queries for variety
        queries = [
            "science fiction classics",
            "dystopian novels",
            "cyberpunk fiction",
            "space opera",
            "philosophical fiction"
        ]

        books = fetch_multiple_queries(queries, max_per_query=3)

        if books:
            print(f"\n📊 Fetched {len(books)} unique books from Google Books API")

            # Enrich with author data
            print("\n🔍 Step 2: Enriching author data from Open Library...")
            for i, book in enumerate(books):
                print(f"   [{i+1}/{len(books)}] {book['title'][:40]}...")
                enrich_author_data(book)
                time.sleep(0.2)  # Be nice to Open Library API
        else:
            print("   ⚠️  No books from API, using fallback")
            books = get_fallback_books()
    else:
        print("   ℹ️  No Google API key, using fallback dataset")
        books = get_fallback_books()

    print(f"\n✅ Total books to index: {len(books)}")

    # Generate embeddings
    print("\n🔢 Step 3: Generating embeddings...")
    book_texts = [b['embed_text'] for b in books]
    author_texts = [b['author_text'] for b in books]

    book_vecs = generate_embeddings(book_texts)
    author_vecs = generate_embeddings(author_texts)

    # Setup Qdrant
    print("\n💾 Step 4: Setting up Qdrant...")
    setup_collection(client)

    # Upload
    print("\n☁️  Step 5: Uploading to Qdrant...")
    upload_books(client, books, book_vecs, author_vecs)

    # Demo searches
    print("\n🎯 Step 6: Running search demonstrations...")

    print_results(
        search_content(client, "space exploration and politics", 3),
        "Content Search: 'space exploration and politics'"
    )

    print_results(
        search_author_style(client, "philosophical dystopian writer", 3),
        "Author Style Search: 'philosophical dystopian writer'"
    )

    print_results(
        find_similar_authors(client, "Frank Herbert", 3),
        "Authors Similar to 'Frank Herbert' (by style)"
    )

    print_results(
        hybrid_search(client, "complex world-building with political intrigue", 0.6, 0.4, 3),
        "Hybrid Search: 'complex world-building with political intrigue'"
    )

    print_results(
        search_content(client, "artificial intelligence", 3, filters={"author_name": "Isaac Asimov"}),
        "Filtered: 'AI' by Isaac Asimov"
    )

    print("\n" + "="*70)
    print("✅ SYSTEM READY")
    print("="*70)
    print(f"\n📊 Indexed {len(books)} books with:")
    print("   • Dual-vector embeddings (content + author style)")
    print("   • Open Library author biographies")
    print("   • Full metadata (ratings, categories, covers)")
    print("\n💡 Set GOOGLE_API_KEY env var to fetch more books!")


if __name__ == "__main__":
    main()