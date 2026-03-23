#!/usr/bin/env python3
"""
Book Recommendation System - INTERACTIVE STANDALONE
User inputs a book name, gets personalized recommendations
"""

import os
import sys
import time
import requests
import numpy as np
from typing import List, Dict, Optional
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
QDRANT_LOCAL_PATH = os.getenv("QDRANT_LOCAL_PATH", "./qdrant_local")

# Initialize
print("🔧 Loading embedding model...")
encoder = SentenceTransformer('all-MiniLM-L6-v2')
VECTOR_SIZE = encoder.get_sentence_embedding_dimension()
print(f"✅ Ready! Vector size: {VECTOR_SIZE}")

qdrant_client: Optional[QdrantClient] = None

# ============================================================
# QDRANT CONNECTION
# ============================================================

def get_client():
    """Get Qdrant client."""
    global qdrant_client
    if qdrant_client:
        return qdrant_client

    try:
        if QDRANT_API_KEY:
            client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY)
        else:
            client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        client.get_collections()
        print("✅ Connected to Qdrant")
        qdrant_client = client
        return client
    except:
        os.makedirs(QDRANT_LOCAL_PATH, exist_ok=True)
        client = QdrantClient(path=QDRANT_LOCAL_PATH)
        print("✅ Using local Qdrant")
        qdrant_client = client
        return client


# ============================================================
# DATA LOADING
# ============================================================

def fetch_google_books(query, max_results=5):
    """Fetch from Google Books API."""
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_api_key_here":
        return []

    url = "https://www.googleapis.com/books/v1/volumes"
    params = {'q': query, 'key': GOOGLE_API_KEY, 'maxResults': max_results, 'printType': 'books'}

    try:
        time.sleep(0.3)
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return []

        data = response.json()
        books = []
        for item in data.get('items', []):
            volume = item.get('volumeInfo', {})
            authors = volume.get('authors', ['Unknown'])
            categories = volume.get('categories', [])

            books.append({
                'id': item.get('id'),
                'title': volume.get('title', 'Unknown'),
                'authors': ', '.join(authors),
                'description': volume.get('description', '')[:500],
                'categories': categories,
                'published_date': volume.get('publishedDate', 'Unknown'),
                'page_count': volume.get('pageCount', 0) or 0,
                'average_rating': volume.get('averageRating', 0) or 0,
                'embed_text': f"Title: {volume.get('title')}. Author: {', '.join(authors)}. {volume.get('description', '')}",
                'author_text': f"Author: {', '.join(authors)}. Genres: {', '.join(categories)}"
            })
        return books
    except:
        return []


def get_books():
    """Get initial book dataset."""
    books = []

    if GOOGLE_API_KEY and GOOGLE_API_KEY != "your_api_key_here":
        queries = ["sci-fi classics", "dystopian novels", "cyberpunk"]
        seen = set()
        for q in queries:
            for b in fetch_google_books(q, 3):
                if b['id'] not in seen:
                    seen.add(b['id'])
                    books.append(b)

    if not books:
        # Fallback classics
        books = [
            {"id": "1", "title": "Dune", "authors": "Frank Herbert", "description": "Epic sci-fi about politics and ecology on Arrakis.", "categories": ["Science Fiction"], "published_date": "1965", "page_count": 412, "average_rating": 4.2, "embed_text": "Title: Dune. Author: Frank Herbert. Epic sci-fi about politics and ecology on Arrakis.", "author_text": "Author: Frank Herbert. Genres: Science Fiction"},
            {"id": "2", "title": "1984", "authors": "George Orwell", "description": "Dystopian novel about surveillance and authoritarian power.", "categories": ["Dystopian"], "published_date": "1949", "page_count": 328, "average_rating": 4.1, "embed_text": "Title: 1984. Author: George Orwell. Dystopian novel about surveillance and authoritarian power.", "author_text": "Author: George Orwell. Genres: Dystopian"},
            {"id": "3", "title": "Neuromancer", "authors": "William Gibson", "description": "Cyberpunk classic with AI and hackers.", "categories": ["Cyberpunk"], "published_date": "1984", "page_count": 271, "average_rating": 3.9, "embed_text": "Title: Neuromancer. Author: William Gibson. Cyberpunk classic with AI and hackers.", "author_text": "Author: William Gibson. Genres: Cyberpunk"},
            {"id": "4", "title": "Foundation", "authors": "Isaac Asimov", "description": "Mathematical sociology predicts fall of galactic empires.", "categories": ["Science Fiction"], "published_date": "1951", "page_count": 244, "average_rating": 4.2, "embed_text": "Title: Foundation. Author: Isaac Asimov. Mathematical sociology predicts fall of galactic empires.", "author_text": "Author: Isaac Asimov. Genres: Science Fiction"},
            {"id": "5", "title": "The Left Hand of Darkness", "authors": "Ursula K. Le Guin", "description": "Exploration of gender and society on an alien world.", "categories": ["Science Fiction"], "published_date": "1969", "page_count": 304, "average_rating": 4.0, "embed_text": "Title: The Left Hand of Darkness. Author: Ursula K. Le Guin. Exploration of gender and society on an alien world.", "author_text": "Author: Ursula K. Le Guin. Genres: Science Fiction"},
            {"id": "6", "title": "Snow Crash", "authors": "Neal Stephenson", "description": "Cyberpunk adventure with virtual reality and ancient myths.", "categories": ["Cyberpunk"], "published_date": "1992", "page_count": 470, "average_rating": 3.9, "embed_text": "Title: Snow Crash. Author: Neal Stephenson. Cyberpunk adventure with virtual reality and ancient myths.", "author_text": "Author: Neal Stephenson. Genres: Cyberpunk"},
            {"id": "7", "title": "The Martian", "authors": "Andy Weir", "description": "An astronaut stranded on Mars must survive.", "categories": ["Science Fiction"], "published_date": "2011", "page_count": 369, "average_rating": 4.4, "embed_text": "Title: The Martian. Author: Andy Weir. An astronaut stranded on Mars must survive.", "author_text": "Author: Andy Weir. Genres: Science Fiction"},
            {"id": "8", "title": "Ready Player One", "authors": "Ernest Cline", "description": "Virtual reality treasure hunt in a dystopian future.", "categories": ["Science Fiction"], "published_date": "2011", "page_count": 374, "average_rating": 4.2, "embed_text": "Title: Ready Player One. Author: Ernest Cline. Virtual reality treasure hunt in a dystopian future.", "author_text": "Author: Ernest Cline. Genres: Science Fiction"},
        ]

    return books


# ============================================================
# EMBEDDINGS & DATABASE
# ============================================================

def generate_embeddings(texts):
    """Generate embeddings."""
    if not texts:
        return np.empty((0, VECTOR_SIZE), dtype=np.float32)
    embeddings = []
    for i in range(0, len(texts), 32):
        batch = texts[i:i+32]
        emb = encoder.encode(batch, convert_to_numpy=True, show_progress_bar=False)
        embeddings.extend(emb)
    return np.array(embeddings)


def setup_db(client, books):
    """Setup database with books."""
    try:
        cols = client.get_collections()
        if COLLECTION_NAME in [c.name for c in cols.collections]:
            client.delete_collection(COLLECTION_NAME)
    except:
        pass

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "book_content": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            "author_style": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        }
    )

    # Upload
    book_vecs = generate_embeddings([b['embed_text'] for b in books])
    author_vecs = generate_embeddings([b['author_text'] for b in books])

    points = []
    for i, (book, bv, av) in enumerate(zip(books, book_vecs, author_vecs)):
        points.append(PointStruct(
            id=i,
            vector={"book_content": bv.tolist(), "author_style": av.tolist()},
            payload={
                'title': book['title'],
                'authors': book['authors'],
                'author_name': book['authors'].split(',')[0] if ',' in book['authors'] else book['authors'],
                'description': book['description'][:300],
                'categories': book['categories'],
                'published_date': book['published_date'],
                'page_count': int(book['page_count']),
                'average_rating': float(book['average_rating']),
            }
        ))

    for i in range(0, len(points), 100):
        client.upsert(collection_name=COLLECTION_NAME, points=points[i:i+100])

    print(f"✅ Database ready with {len(points)} books")


# ============================================================
# RECOMMENDATION ENGINE
# ============================================================

def find_similar_books(client, book_title, limit=5):
    """Find books similar to given title."""
    # Find the book
    all_books = client.scroll(collection_name=COLLECTION_NAME, limit=1000)[0]

    target = None
    for b in all_books:
        if book_title.lower() in b.payload['title'].lower():
            target = b
            break

    if not target:
        # Search by text
        vec = encoder.encode(book_title).tolist()
        result = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vec,
            using="book_content",
            limit=limit,
            with_payload=True
        )
        return result.points

    print(f"   📚 Found: '{target.payload['title']}' by {target.payload['authors']}")

    # Get recommendations by both vectors
    book_vec = target.vector['book_content']
    author_vec = target.vector['author_style']

    content_res = client.query_points(
        collection_name=COLLECTION_NAME,
        query=book_vec,
        using="book_content",
        limit=limit+1,
        with_payload=True
    ).points

    author_res = client.query_points(
        collection_name=COLLECTION_NAME,
        query=author_vec,
        using="author_style",
        limit=limit+1,
        with_payload=True
    ).points

    # Merge scores
    merged = {}
    for h in content_res:
        if h.id != target.id:
            merged[h.id] = {'hit': h, 'score': h.score * 0.6}

    for h in author_res:
        if h.id != target.id:
            if h.id in merged:
                merged[h.id]['score'] += h.score * 0.4
            else:
                merged[h.id] = {'hit': h, 'score': h.score * 0.4}

    ranked = sorted(merged.values(), key=lambda x: x['score'], reverse=True)
    return [item['hit'] for item in ranked[:limit]]


def search_by_keywords(client, keywords, limit=5):
    """Search by keywords."""
    vec = encoder.encode(keywords).tolist()
    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vec,
        using="book_content",
        limit=limit,
        with_payload=True
    )
    return result.points


# ============================================================
# USER INTERFACE
# ============================================================

def print_book(hit, idx=None):
    """Print book info."""
    p = hit.payload
    prefix = f"{idx}. " if idx else ""
    print(f"\n{prefix}📖 {p['title']}")
    print(f"   ✍️  {p['authors']}")
    if hasattr(hit, 'score') and hit.score:
        print(f"   📊 Match: {hit.score:.3f}")
    if p.get('categories'):
        print(f"   🏷️  {', '.join(p['categories'][:2])}")
    if p.get('average_rating'):
        print(f"   ⭐ {p['average_rating']}/5")
    if p.get('description'):
        desc = p['description'][:100] + "..." if len(p['description']) > 100 else p['description']
        print(f"   📝 {desc}")


def main_menu(client):
    """Interactive menu."""
    while True:
        print("\n" + "="*60)
        print("🎯 BOOK RECOMMENDATION SYSTEM")
        print("="*60)
        print("1. Get recommendations for a book")
        print("2. Search by keywords")
        print("3. Exit")

        choice = input("\nChoice (1-3): ").strip()

        if choice == "1":
            book_name = input("\nEnter book title: ").strip()
            if book_name:
                print(f"\n🔍 Finding books similar to '{book_name}'...")
                results = find_similar_books(client, book_name, 5)

                if results:
                    print(f"\n📚 Top 5 recommendations:")
                    print("="*60)
                    for i, hit in enumerate(results, 1):
                        print_book(hit, i)
                else:
                    print("   No recommendations found.")

        elif choice == "2":
            keywords = input("\nEnter keywords: ").strip()
            if keywords:
                print(f"\n🔍 Searching for '{keywords}'...")
                results = search_by_keywords(client, keywords, 5)

                if results:
                    print(f"\n📚 Results:")
                    print("="*60)
                    for i, hit in enumerate(results, 1):
                        print_book(hit, i)
                else:
                    print("   No books found.")

        elif choice == "3":
            print("\n👋 Goodbye!")
            break

        else:
            print("\n❌ Invalid choice.")


# ============================================================
# MAIN
# ============================================================

def main():
    """Main."""
    print("\n" + "="*60)
    print("📚 INITIALIZING BOOK RECOMMENDATIONS")
    print("="*60)

    client = get_client()

    # Load data
    print("\n📥 Loading books...")
    books = get_books()

    if not books:
        print("❌ No books available")
        return

    print(f"   Loaded {len(books)} books")

    # Setup
    print("\n💾 Building database...")
    setup_db(client, books)

    print("\n" + "="*60)
    print("✅ READY!")
    print("="*60)

    # Run menu
    main_menu(client)


if __name__ == "__main__":
    main()