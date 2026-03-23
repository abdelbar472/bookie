#!/usr/bin/env python3
"""
Book Recommendation System - V3 (Multi-language Support)
Searches database first, then Google API, supports Arabic/English/any language
"""

import os
import time
from typing import List, Dict, Optional

import requests
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

# ============================================================
# CONFIGURATION - Check API keys at startup
# ============================================================

GOOGLE_API_KEY = 'AIzaSyB7rhsd0u6qJv11Fe_9PDEynooRunq8Q4M'
COLLECTION_NAME = "books"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip()
QDRANT_LOCAL_PATH = os.getenv("QDRANT_LOCAL_PATH", "./qdrant_local")
GOOGLE_TIMEOUT_SECONDS = 15
GOOGLE_MAX_RETRIES = 3

# Validate API key
HAS_GOOGLE_API = bool(GOOGLE_API_KEY and GOOGLE_API_KEY not in ["", "your_key_here", "your_api_key_here", "AIzaSy..."])

print("🔧 Loading embedding model...")
encoder = SentenceTransformer('all-MiniLM-L6-v2')
VECTOR_SIZE = encoder.get_sentence_embedding_dimension()
print(f"✅ Ready! Vector size: {VECTOR_SIZE}")

if HAS_GOOGLE_API:
    print(f"✅ Google API Key: {GOOGLE_API_KEY[:10]}...")
else:
    print(f"⚠️  No Google API Key detected - external search disabled")
    print(f"   Set with: set GOOGLE_API_KEY=your_actual_key")

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
    except Exception as remote_error:
        print(f"⚠️  Remote Qdrant unavailable ({remote_error}). Falling back to local storage: {QDRANT_LOCAL_PATH}")
        try:
            os.makedirs(QDRANT_LOCAL_PATH, exist_ok=True)
            client = QdrantClient(path=QDRANT_LOCAL_PATH)
            print("✅ Using local Qdrant")
            qdrant_client = client
            return client
        except Exception as local_error:
            raise RuntimeError(f"Failed to initialize both remote and local Qdrant. Local error: {local_error}")


def close_client():
    """Close shared Qdrant client to avoid shutdown-time destructor errors."""
    global qdrant_client
    if qdrant_client is None:
        return
    try:
        qdrant_client.close()
    except Exception:
        pass
    finally:
        qdrant_client = None


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
# DATABASE SEARCH (Multi-language support)
# ============================================================

def search_database(client, query: str) -> List[Dict]:
    """Search database for books matching query (supports any language)."""
    try:
        all_books = client.scroll(collection_name=COLLECTION_NAME, limit=10000)[0]

        matches = []
        query_lower = query.lower().strip()

        for book in all_books:
            payload = book.payload or {}
            title = str(payload.get('title', '')).lower()
            authors = str(payload.get('authors', '')).lower()
            description = str(payload.get('description', '')).lower()

            # Exact match
            if query_lower == title:
                matches.append({'book': book, 'match_type': 'exact', 'score': 1.0})
            # Title contains query
            elif query_lower in title:
                matches.append({'book': book, 'match_type': 'title', 'score': 0.9})
            # Query contains title (partial)
            elif title in query_lower and len(title) > 3:
                matches.append({'book': book, 'match_type': 'partial', 'score': 0.8})
            # Author match
            elif query_lower in authors:
                matches.append({'book': book, 'match_type': 'author', 'score': 0.7})
            # Description contains query
            elif query_lower in description and len(query_lower) > 4:
                matches.append({'book': book, 'match_type': 'description', 'score': 0.6})

        # If no text matches, try semantic search
        if not matches and len(query) > 2:
            try:
                query_vec = encoder.encode(query).tolist()

                try:
                    semantic_results = client.query_points(
                        collection_name=COLLECTION_NAME,
                        query=query_vec,
                        using="book_content",
                        limit=5,
                        with_payload=True
                    ).points
                except Exception:
                    # Compatibility path for older single-vector collections.
                    semantic_results = client.query_points(
                        collection_name=COLLECTION_NAME,
                        query=query_vec,
                        limit=5,
                        with_payload=True
                    ).points

                for hit in semantic_results:
                    if hit.score > 0.65:
                        matches.append({
                            'book': hit,
                            'match_type': 'semantic',
                            'score': hit.score
                        })
            except Exception:
                pass

        # Sort by score
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches

    except Exception as e:
        print(f"   ⚠️  Database search error: {e}")
        return []


# ============================================================
# GOOGLE BOOKS API (Multi-language support)
# ============================================================

def search_google_books(query: str, max_results: int = 5) -> List[Dict]:
    """Search Google Books API - supports any language including Arabic."""

    if not HAS_GOOGLE_API:
        return []

    url = "https://www.googleapis.com/books/v1/volumes"

    # Try different search strategies
    search_queries = [
        query,  # Original query (Arabic, English, etc.)
        f'intitle:"{query}"',  # Exact title match
    ]

    # Add transliterated version if Arabic detected
    if any('؀' <= c <= 'ۿ' for c in query):  # Arabic range
        # Keep original, Google handles Arabic well
        pass

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
            'orderBy': 'relevance'
            # Note: NOT restricting language - allow any language
        }

        try:
            data = None
            for attempt in range(1, GOOGLE_MAX_RETRIES + 1):
                time.sleep(0.4)
                response = requests.get(url, params=params, timeout=GOOGLE_TIMEOUT_SECONDS)

                if response.status_code == 429:
                    wait_seconds = min(2 ** attempt, 8)
                    print(f"   ⏳ Rate limited for '{search_query}', retrying in {wait_seconds}s ({attempt}/{GOOGLE_MAX_RETRIES})...")
                    time.sleep(wait_seconds)
                    continue

                if response.status_code == 403:
                    print("   ❌ API key invalid or quota exceeded")
                    return []

                if response.status_code != 200:
                    break

                data = response.json()
                break

            if not data:
                continue

            for item in data.get('items', []):
                book_id = item.get('id')
                if book_id in seen_ids:
                    continue
                seen_ids.add(book_id)

                volume = item.get('volumeInfo', {})
                authors = volume.get('authors', ['Unknown'])
                categories = volume.get('categories', [])

                # Get language info
                language = volume.get('language', 'unknown')

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
                    'language': language,
                    'thumbnail': volume.get('imageLinks', {}).get('thumbnail', ''),
                    'preview_link': volume.get('previewLink', ''),
                    'publisher': volume.get('publisher', ''),
                    'source': 'google_books'
                }

                # Create embedding text (multilingual)
                book['embed_text'] = (
                    f"Title: {book['title']}. "
                    f"Author: {book['authors']}. "
                    f"Description: {book['description']}. "
                    f"Genres: {', '.join(categories)}."
                )
                book['author_text'] = (
                    f"Author: {book['authors']}. "
                    f"Genres: {', '.join(categories)}."
                )

                all_books.append(book)

                if len(all_books) >= max_results:
                    break

        except requests.RequestException:
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
            'language': book.get('language', 'unknown'),
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
        vector_data = target_book.vector or {}
        if isinstance(vector_data, dict):
            book_vec = vector_data.get('book_content')
            author_vec = vector_data.get('author_style')
        else:
            book_vec = vector_data
            author_vec = vector_data
        target_id = target_book.id
    else:
        book_vec = encoder.encode(target_book['embed_text']).tolist()
        author_vec = encoder.encode(target_book['author_text']).tolist()
        target_id = None

    if not book_vec:
        return []

    try:
        content_res = client.query_points(
            collection_name=COLLECTION_NAME,
            query=book_vec,
            using="book_content",
            limit=limit + 5,
            with_payload=True
        ).points
    except Exception:
        try:
            content_res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=book_vec,
                limit=limit + 5,
                with_payload=True
            ).points
        except Exception:
            return []

    try:
        author_res = client.query_points(
            collection_name=COLLECTION_NAME,
            query=author_vec or book_vec,
            using="author_style",
            limit=limit + 5,
            with_payload=True
        ).points
    except Exception:
        author_res = []

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

    ranked = sorted(merged.values(), key=lambda x: x['score'], reverse=True)

    results = []
    for item in ranked[:limit]:
        item['hit'].score = item['score']
        results.append(item['hit'])

    return results


def suggest_local_books_from_query(client, query: str, limit: int = 5):
    """Return best-effort local semantic suggestions for a free-text query."""
    try:
        query_vec = encoder.encode(query).tolist()
    except Exception:
        return []

    try:
        hits = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vec,
            using="book_content",
            limit=limit,
            with_payload=True
        ).points
    except Exception:
        try:
            hits = client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vec,
                limit=limit,
                with_payload=True
            ).points
        except Exception:
            return []

    return hits


# ============================================================
# INITIAL DATA (with some Arabic books)
# ============================================================

def setup_database(client):
    """Setup initial database."""
    try:
        cols = client.get_collections()
        if COLLECTION_NAME in [c.name for c in cols.collections]:
            # Backfill key offline seed so users don't need to recreate collection.
            existing = client.scroll(collection_name=COLLECTION_NAME, limit=10000, with_payload=True)[0]
            has_malek = any((p.payload or {}).get("title") == "مالك الحزين" for p in existing)
            if not has_malek:
                book = {
                    "title": "مالك الحزين",
                    "authors": "إبراهيم أصلان",
                    "description": "رواية مصرية واقعية تدور حول الحياة اليومية في حي شعبي في القاهرة.",
                    "categories": ["أدب عربي", "رواية واقعية"],
                    "published_date": "1983",
                    "page_count": 190,
                    "average_rating": 4.0,
                    "language": "ar",
                }
                book["embed_text"] = f"Title: {book['title']}. Author: {book['authors']}. {book['description']}"
                book["author_text"] = f"Author: {book['authors']}. Genres: {', '.join(book['categories'])}"
                add_book_to_database(client, book)
                print("   Added missing seed: مالك الحزين")
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

    # Seed books (English + Arabic examples)
    seed_books = [
        {"title": "Dune", "authors": "Frank Herbert", "description": "Epic sci-fi about politics and ecology on desert planet Arrakis.", "categories": ["Science Fiction"], "published_date": "1965", "page_count": 412, "average_rating": 4.3, "language": "en"},
        {"title": "1984", "authors": "George Orwell", "description": "Dystopian novel about surveillance and totalitarianism.", "categories": ["Dystopian"], "published_date": "1949", "page_count": 328, "average_rating": 4.2, "language": "en"},
        {"title": "Neuromancer", "authors": "William Gibson", "description": "Cyberpunk classic with AI and hackers.", "categories": ["Cyberpunk"], "published_date": "1984", "page_count": 271, "average_rating": 3.9, "language": "en"},
        {"title": "Foundation", "authors": "Isaac Asimov", "description": "Mathematical sociology predicts fall of galactic empires.", "categories": ["Science Fiction"], "published_date": "1951", "page_count": 244, "average_rating": 4.2, "language": "en"},
        {"title": "The Left Hand of Darkness", "authors": "Ursula K. Le Guin", "description": "Exploration of gender on alien world.", "categories": ["Science Fiction"], "published_date": "1969", "page_count": 304, "average_rating": 4.1, "language": "en"},
        # Arabic book example
        {"title": "أرض زيكولا", "authors": "عمرو عبدالحميد", "description": "رواية خيال علمي عربية عن عالم زيكولا المسحور", "categories": ["خيال علمي", "أدب عربي"], "published_date": "2016", "page_count": 320, "average_rating": 4.1, "language": "ar"},
        {"title": "مالك الحزين", "authors": "إبراهيم أصلان", "description": "رواية مصرية واقعية تدور حول الحياة اليومية في حي شعبي في القاهرة.", "categories": ["أدب عربي", "رواية واقعية"], "published_date": "1983", "page_count": 190, "average_rating": 4.0, "language": "ar"},
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
                'language': book.get('language', 'en'),
                'source': 'seed'
            }
        )
        client.upsert(collection_name=COLLECTION_NAME, points=[point])

    print(f"   Added {len(seed_books)} seed books (English + Arabic)")


# ============================================================
# MAIN RECOMMENDATION FLOW
# ============================================================

def get_recommendations(client, user_query: str):
    """Main recommendation flow."""

    print(f"\n🔍 STEP 1: Searching database for '{user_query}'...")

    # Search database first
    db_matches = search_database(client, user_query)

    if db_matches:
        best_match = db_matches[0]
        book = best_match['book']
        match_type = best_match['match_type']
        match_score = best_match['score']

        print(f"   ✅ FOUND in database!")
        print(f"   📖 Match: {book.payload['title']}")
        if book.payload.get('authors'):
            print(f"   ✍️  {book.payload['authors']}")
        print(f"   🔍 Match type: {match_type} (score: {match_score:.2f})")

        target_book = book
        is_new = False

    else:
        print(f"   ❌ NOT found in database")

        if not HAS_GOOGLE_API:
            print(f"\n❌ Cannot search external APIs - no Google API key")
            print(f"\n💡 To fix this:")
            print(f"   1. Get API key from: https://developers.google.com/books/docs/v1/using#APIKey")
            print(f"   2. Set it: set GOOGLE_API_KEY=your_actual_key_here")
            print(f"   3. Restart the program")

            # Keep the flow useful in offline mode by showing semantic local picks.
            fallback = suggest_local_books_from_query(client, user_query, limit=5)
            if fallback:
                print(f"\n📚 Closest books currently in local database:")
                print("=" * 60)
                for i, hit in enumerate(fallback, 1):
                    p = hit.payload or {}
                    print(f"\n{i}. 📖 {p.get('title', 'Unknown')}")
                    if p.get('authors'):
                        print(f"   ✍️  {p['authors']}")
                    print(f"   📊 Similarity: {hit.score:.3f}")
                    if p.get('categories'):
                        print(f"   🏷️  {', '.join(p['categories'][:2])}")
            return None

        print(f"\n🔍 STEP 2: Searching Google Books API...")
        api_results = search_google_books(user_query, max_results=5)

        if not api_results:
            print(f"   ❌ No results from Google Books API")
            print(f"\n💡 Try:")
            print(f"   - Different spelling")
            print(f"   - Shorter title")
            print(f"   - Author name + title")
            return None

        print(f"\n📚 Found {len(api_results)} book(s):")
        for i, book in enumerate(api_results[:5], 1):
            print(f"\n   {i}. {book['title']}")
            print(f"      Author: {book['authors']}")
            if book.get('average_rating'):
                print(f"      ⭐ {book['average_rating']}/5")
            if book.get('language') and book['language'] != 'unknown':
                print(f"      🌐 Language: {book['language']}")

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
                if idx >= len(api_results):
                    print("   Invalid selection, using first result")
                    idx = 0
                selected = api_results[idx]
            except Exception:
                print("   Invalid input, using first result")
                selected = api_results[0]

        # Add to database
        print(f"\n💾 STEP 3: Adding to database...")
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
    if p.get('authors'):
        print(f"   ✍️  {p['authors']}")
    if p.get('categories'):
        print(f"   🏷️  {', '.join(p['categories'][:3])}")
    if p.get('average_rating'):
        ratings = p.get('ratings_count', 0)
        print(f"   ⭐ {p['average_rating']}/5" + (f" ({ratings:,} ratings)" if ratings else ""))
    if p.get('language') and p['language'] != 'unknown':
        lang_map = {'en': 'English', 'ar': 'Arabic', 'fr': 'French', 'es': 'Spanish'}
        lang = lang_map.get(p['language'], p['language'])
        print(f"   🌐 {lang}")
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
            if p.get('authors'):
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
        print(f"   No recommendations found")

    return recommendations


# ============================================================
# MAIN
# ============================================================

def main():
    """Main loop."""

    print("\n" + "="*70)
    print("📚 SMART BOOK RECOMMENDER V3")
    print("   Multi-language support (English, Arabic, any language)")
    print("="*70)

    try:
        client = get_client()
    except Exception as err:
        print(f"\n❌ Startup failed: {err}")
        return

    setup_database(client)

    # Show count
    try:
        all_books = client.scroll(collection_name=COLLECTION_NAME, limit=10000)[0]
        print(f"\n📊 Database: {len(all_books)} books")
        if not HAS_GOOGLE_API:
            print(f"⚠️  External search disabled (no API key)")
    except:
        pass

    # Main loop
    try:
        while True:
            print("\n" + "=" * 70)
            print("Enter a book title (English, Arabic, or any language)")
            print("Examples: 'Dune', 'مالك الحزين', 'Le Petit Prince'")
            print("=" * 70)

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
            except Exception:
                pass
    except (KeyboardInterrupt, EOFError):
        print("\n\n👋 Stopped by user.")
    finally:
        close_client()


if __name__ == "__main__":
    main()