#!/usr/bin/env python3
"""
Book Recommendation System - SMART SEARCH EDITION
Checks database first → if no match, searches Google API → adds → recommends
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

# ============================================================
# CONFIGURATION
# ============================================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
COLLECTION_NAME = "books"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_LOCAL_PATH = os.getenv("QDRANT_LOCAL_PATH", "./qdrant_local")

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


def get_next_id(client):
    """Get next available ID."""
    try:
        all_books = client.scroll(collection_name=COLLECTION_NAME, limit=10000)[0]
        if not all_books:
            return 0
        return max([b.id for b in all_books]) + 1
    except:
        return 0


# ============================================================
# DATABASE SEARCH
# ============================================================

def search_database(client, query: str) -> List[Dict]:
    """
    Search database for books matching query.
    Returns list of matching books with similarity scores.
    """
    try:
        # First try exact/partial title match
        all_books = client.scroll(collection_name=COLLECTION_NAME, limit=10000)[0]

        matches = []
        query_lower = query.lower()

        for book in all_books:
            title = book.payload.get('title', '').lower()
            authors = book.payload.get('authors', '').lower()

            # Check for exact or partial match
            if query_lower in title or title in query_lower:
                matches.append({
                    'book': book,
                    'match_type': 'title',
                    'score': 1.0 if query_lower == title else 0.8
                })
            elif query_lower in authors:
                matches.append({
                    'book': book,
                    'match_type': 'author',
                    'score': 0.6
                })

        # If no text matches, try semantic search
        if not matches:
            query_vec = encoder.encode(query).tolist()

            semantic_results = client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vec,
                using="book_content",
                limit=5,
                with_payload=True
            ).points

            for hit in semantic_results:
                if hit.score > 0.7:  # Only high confidence matches
                    matches.append({
                        'book': hit,
                        'match_type': 'semantic',
                        'score': hit.score
                    })

        return matches

    except Exception as e:
        print(f"   ⚠️  Database search error: {e}")
        return []


# ============================================================
# GOOGLE BOOKS API SEARCH
# ============================================================

def search_google_books(query: str, max_results: int = 5) -> List[Dict]:
    """Search Google Books API."""
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_api_key_here":
        return []

    url = "https://www.googleapis.com/books/v1/volumes"

    # Try different search strategies
    search_queries = [
        f'intitle:"{query}"',
        query,
        f'{query} book'
    ]

    all_books = []
    seen_ids = set()

    for search_query in search_queries:
        if len(all_books) >= max_results:
            break

        params = {
            'q': search_query,
            'key': GOOGLE_API_KEY,
            'maxResults': max_results,
            'printType': 'books',
            'langRestrict': 'en',
            'orderBy': 'relevance'
        }

        try:
            time.sleep(0.5)
            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 429:
                print("   ⏳ Rate limited, waiting...")
                time.sleep(2)
                continue

            if response.status_code != 200:
                continue

            data = response.json()

            for item in data.get('items', []):
                book_id = item.get('id')
                if book_id in seen_ids:
                    continue
                seen_ids.add(book_id)

                volume = item.get('volumeInfo', {})
                authors = volume.get('authors', ['Unknown'])
                categories = volume.get('categories', [])

                book = {
                    'id': book_id,
                    'title': volume.get('title', 'Unknown'),
                    'authors': ', '.join(authors),
                    'description': volume.get('description', '')[:800],
                    'categories': categories,
                    'published_date': volume.get('publishedDate', 'Unknown'),
                    'page_count': volume.get('pageCount', 0) or 0,
                    'average_rating': volume.get('averageRating', 0) or 0,
                    'ratings_count': volume.get('ratingsCount', 0) or 0,
                    'thumbnail': volume.get('imageLinks', {}).get('thumbnail', ''),
                    'preview_link': volume.get('previewLink', ''),
                    'publisher': volume.get('publisher', ''),
                }

                book['embed_text'] = (
                    f"Title: {book['title']}. "
                    f"Author: {book['authors']}. "
                    f"Description: {book['description']}. "
                    f"Genres: {', '.join(categories)}."
                )
                book['author_text'] = (
                    f"Author: {book['authors']}. "
                    f"Genres: {', '.join(categories)}. "
                    f"Style: {book['description'][:200]}"
                )

                all_books.append(book)

                if len(all_books) >= max_results:
                    break

        except Exception as e:
            continue

    return all_books


# ============================================================
# ADD BOOK TO DATABASE
# ============================================================

def add_book_to_database(client, book: Dict) -> int:
    """Add new book to database."""
    new_id = get_next_id(client)

    # Generate embeddings
    book_vec = encoder.encode(book['embed_text']).tolist()
    author_vec = encoder.encode(book['author_text']).tolist()

    point = PointStruct(
        id=new_id,
        vector={
            "book_content": book_vec,
            "author_style": author_vec
        },
        payload={
            'title': book['title'],
            'authors': book['authors'],
            'author_name': book['authors'].split(',')[0] if ',' in book['authors'] else book['authors'],
            'description': book['description'][:500],
            'categories': book['categories'],
            'published_date': book['published_date'],
            'page_count': int(book['page_count']),
            'average_rating': float(book['average_rating']),
            'ratings_count': int(book.get('ratings_count', 0)),
            'thumbnail': book.get('thumbnail', ''),
            'preview_link': book.get('preview_link', ''),
            'source': 'google_books'
        }
    )

    client.upsert(collection_name=COLLECTION_NAME, points=[point])
    return new_id


# ============================================================
# FIND SIMILAR BOOKS
# ============================================================

def find_similar_books(client, target_book, limit=5):
    """Find similar books using both vectors."""

    if hasattr(target_book, 'vector'):
        # Database record
        book_vec = target_book.vector['book_content']
        author_vec = target_book.vector['author_style']
        target_id = target_book.id
    else:
        # New book dict
        book_vec = encoder.encode(target_book['embed_text']).tolist()
        author_vec = encoder.encode(target_book['author_text']).tolist()
        target_id = None

    # Search both vectors
    content_res = client.query_points(
        collection_name=COLLECTION_NAME,
        query=book_vec,
        using="book_content",
        limit=limit+5,
        with_payload=True
    ).points

    author_res = client.query_points(
        collection_name=COLLECTION_NAME,
        query=author_vec,
        using="author_style",
        limit=limit+5,
        with_payload=True
    ).points

    # Merge (60% content + 40% author style)
    merged = {}

    for h in content_res:
        if target_id is None or h.id != target_id:
            merged[h.id] = {'hit': h, 'score': h.score * 0.6}

    for h in author_res:
        if target_id is None or h.id != target_id:
            if h.id in merged:
                merged[h.id]['score'] += h.score * 0.4
            else:
                merged[h.id] = {'hit': h, 'score': h.score * 0.4}

    # Sort and return top
    ranked = sorted(merged.values(), key=lambda x: x['score'], reverse=True)

    results = []
    for item in ranked[:limit]:
        item['hit'].score = item['score']
        results.append(item['hit'])

    return results


# ============================================================
# INITIAL DATA
# ============================================================

def setup_database(client):
    """Setup initial database with seed books."""
    try:
        cols = client.get_collections()
        if COLLECTION_NAME in [c.name for c in cols.collections]:
            return
    except:
        pass

    print("   Creating database...")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "book_content": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            "author_style": VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        }
    )

    # Seed books
    seed_books = [
        {"title": "Dune", "authors": "Frank Herbert", "description": "Epic sci-fi about politics and ecology on desert planet Arrakis.", "categories": ["Science Fiction"], "published_date": "1965", "page_count": 412, "average_rating": 4.3},
        {"title": "1984", "authors": "George Orwell", "description": "Dystopian novel about surveillance and totalitarianism.", "categories": ["Dystopian"], "published_date": "1949", "page_count": 328, "average_rating": 4.2},
        {"title": "Neuromancer", "authors": "William Gibson", "description": "Cyberpunk classic with AI and hackers in a dystopian future.", "categories": ["Cyberpunk"], "published_date": "1984", "page_count": 271, "average_rating": 3.9},
        {"title": "Foundation", "authors": "Isaac Asimov", "description": "Mathematical sociology predicts fall of galactic empires.", "categories": ["Science Fiction"], "published_date": "1951", "page_count": 244, "average_rating": 4.2},
        {"title": "The Left Hand of Darkness", "authors": "Ursula K. Le Guin", "description": "Exploration of gender and sexuality on alien world.", "categories": ["Science Fiction"], "published_date": "1969", "page_count": 304, "average_rating": 4.1},
    ]

    for i, book in enumerate(seed_books):
        book['embed_text'] = f"Title: {book['title']}. Author: {book['authors']}. {book['description']}"
        book['author_text'] = f"Author: {book['authors']}. Genres: {', '.join(book['categories'])}"

        book_vec = encoder.encode(book['embed_text']).tolist()
        author_vec = encoder.encode(book['author_text']).tolist()

        point = PointStruct(
            id=i,
            vector={"book_content": book_vec, "author_style": author_vec},
            payload={
                'title': book['title'],
                'authors': book['authors'],
                'author_name': book['authors'],
                'description': book['description'],
                'categories': book['categories'],
                'published_date': book['published_date'],
                'page_count': book['page_count'],
                'average_rating': book['average_rating'],
                'source': 'seed'
            }
        )
        client.upsert(collection_name=COLLECTION_NAME, points=[point])

    print(f"   Added {len(seed_books)} seed books")


# ============================================================
# MAIN RECOMMENDATION FLOW
# ============================================================

def get_recommendations(client, user_query: str):
    """
    Main flow:
    1. Search database
    2. If match found → use it
    3. If no match → search Google API → add to DB → use it
    4. Find similar books
    """

    print(f"\n🔍 STEP 1: Searching database for '{user_query}'...")

    # Search database first
    db_matches = search_database(client, user_query)

    if db_matches:
        # Found in database!
        best_match = db_matches[0]
        book = best_match['book']
        match_type = best_match['match_type']
        match_score = best_match['score']

        print(f"   ✅ FOUND in database!")
        print(f"   📖 Match: {book.payload['title']} by {book.payload['authors']}")
        print(f"   🔍 Match type: {match_type} (score: {match_score:.2f})")

        target_book = book
        is_new = False

    else:
        # Not in database - search Google API
        print(f"   ❌ NOT found in database")
        print(f"\n🔍 STEP 2: Searching Google Books API...")

        if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_api_key_here":
            print(f"   ❌ No GOOGLE_API_KEY set - cannot search external APIs")
            print(f"\n💡 To enable external search, set your API key:")
            print(f"   set GOOGLE_API_KEY=your_key_here")
            return None

        api_results = search_google_books(user_query, max_results=5)

        if not api_results:
            print(f"   ❌ Book not found in Google Books API")
            print(f"\n💡 Suggestions:")
            print(f"   - Check spelling")
            print(f"   - Try a shorter title")
            print(f"   - Try author name + title")
            return None

        # Show results and let user pick
        print(f"\n📚 Found {len(api_results)} book(s) from Google API:")
        for i, book in enumerate(api_results[:5], 1):
            print(f"\n   {i}. {book['title']}")
            print(f"      Author: {book['authors']}")
            if book.get('average_rating'):
                print(f"      Rating: {book['average_rating']}/5")
            if book.get('published_date'):
                print(f"      Year: {book['published_date'][:4]}")

        # Select book
        if len(api_results) == 1:
            selected = api_results[0]
            print(f"\n✨ Auto-selected: {selected['title']}")
        else:
            try:
                choice = input(f"\nSelect (1-{len(api_results)}) or 0 to skip: ").strip()
                idx = int(choice) - 1
                if idx < 0:
                    print("   Skipped")
                    return None
                selected = api_results[idx]
            except:
                print(f"   Invalid choice, using first result")
                selected = api_results[0]

        # Add to database
        print(f"\n💾 STEP 3: Adding '{selected['title']}' to database...")
        new_id = add_book_to_database(client, selected)
        print(f"   ✅ Added with ID: {new_id}")

        target_book = selected
        is_new = True

    # Show target book
    print(f"\n" + "="*60)
    if is_new:
        print(f"✨ NEW BOOK ADDED")
    else:
        print(f"📚 FROM DATABASE")
    print("="*60)

    p = target_book.payload if hasattr(target_book, 'payload') else target_book
    print(f"\n📖 {p['title']}")
    print(f"   ✍️  {p['authors']}")
    if p.get('categories'):
        print(f"   🏷️  {', '.join(p['categories'][:3])}")
    if p.get('average_rating'):
        print(f"   ⭐ {p['average_rating']}/5")
    if p.get('description'):
        desc = p['description'][:150] + "..." if len(p['description']) > 150 else p['description']
        print(f"   📝 {desc}")

    # Find recommendations
    print(f"\n🔍 STEP 4: Finding similar books...")
    recommendations = find_similar_books(client, target_book, limit=5)

    if recommendations:
        print(f"\n📚 TOP 5 RECOMMENDATIONS:")
        print("="*60)
        for i, hit in enumerate(recommendations, 1):
            p = hit.payload
            print(f"\n{i}. 📖 {p['title']}")
            print(f"   ✍️  {p['authors']}")
            print(f"   📊 Match Score: {hit.score:.3f}")
            if p.get('categories'):
                print(f"   🏷️  {', '.join(p['categories'][:2])}")
            if p.get('average_rating'):
                print(f"   ⭐ {p['average_rating']}/5")
            if p.get('description'):
                desc = p['description'][:100] + "..." if len(p['description']) > 100 else p['description']
                print(f"   📝 {desc}")
    else:
        print(f"   No recommendations found (database growing...)")

    return recommendations


# ============================================================
# MAIN
# ============================================================

def main():
    """Main loop."""

    print("\n" + "="*70)
    print("📚 SMART BOOK RECOMMENDER")
    print("   Searches database first, then Google API if not found")
    print("="*70)

    # Setup
    client = get_client()
    setup_database(client)

    # Show count
    try:
        all_books = client.scroll(collection_name=COLLECTION_NAME, limit=10000)[0]
        print(f"\n📊 Database: {len(all_books)} books")
    except:
        pass

    # Main loop
    while True:
        print("\n" + "="*70)
        print("Enter a book title to get recommendations")
        print("(I'll check database first, then search Google if needed)")
        print("="*70)

        query = input("\n📖 Book title (or 'quit'): ").strip()

        if not query:
            continue

        if query.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Goodbye!")
            break

        # Get recommendations
        get_recommendations(client, query)

        # Show updated count
        try:
            all_books = client.scroll(collection_name=COLLECTION_NAME, limit=10000)[0]
            print(f"\n📊 Database now has {len(all_books)} books")
        except:
            pass


if __name__ == "__main__":
    main()