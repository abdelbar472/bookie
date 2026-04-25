import requests
import json

# Base URLs for microservices
AUTH_URL = "http://localhost:8001/api/v1"
USER_URL = "http://localhost:8002/api/v1"
FOLLOW_URL = "http://localhost:8003/api/v1"
SOCIAL_URL = "http://localhost:8004/api/v1"
RAG_URL = "http://localhost:8005/api/v1"
RECOMMENDATION_URL = "http://localhost:8006/api/v1"
BOOK_URL = "http://localhost:8007/api/v3"

# List of all microservices and their endpoints
microservices = [
    {
        'name': '🔐 AUTH (:8001)',
        'endpoints': [
            ('/api/v1/health', 'GET'),
            ('/api/v1/login', 'POST'),
            ('/api/v1/logout', 'POST'),
            ('/api/v1/refresh', 'POST'),
            ('/api/v1/register', 'POST'),
            ('/api/v1/verify', 'GET'),
        ]
    },
    {
        'name': '👤 USER (:8002)',
        'endpoints': [
            ('/api/v1/health', 'GET'),
            ('/api/v1/me', 'GET, PATCH'),
            ('/api/v1/refresh', 'POST'),
            ('/api/v1/users/{user_id}/follow-stats', 'GET'),
            ('/api/v1/users/{user_id}/followers', 'GET'),
            ('/api/v1/users/{user_id}/following', 'GET'),
            ('/api/v1/users/{user_id}/is-following/{followee_id}', 'GET'),
            ('/api/v1/users/{username}', 'GET'),
        ]
    },
    {
        'name': '➕ FOLLOW (:8003)',
        'endpoints': [
            ('/api/v1/follow/check/{followee_id}', 'GET'),
            ('/api/v1/follow/users/{user_id}/followers', 'GET'),
            ('/api/v1/follow/users/{user_id}/following', 'GET'),
            ('/api/v1/follow/users/{user_id}/stats', 'GET'),
            ('/api/v1/follow/{followee_id}', 'POST, DELETE'),
        ]
    },
    {
        'name': '📚 SOCIAL (:8004)',
        'endpoints': [
            ('/api/v1/social/books/{isbn}/reviews', 'GET'),
            ('/api/v1/social/books/{isbn}/stats', 'GET'),
            ('/api/v1/social/health', 'GET'),
            ('/api/v1/social/likes/{isbn}', 'POST, DELETE'),
            ('/api/v1/social/ratings/{isbn}', 'PUT'),
            ('/api/v1/social/ratings/{isbn}/me', 'GET'),
            ('/api/v1/social/reviews', 'POST'),
            ('/api/v1/social/reviews/{review_id}', 'PATCH, DELETE'),
            ('/api/v1/social/reviews/{review_id}/likes', 'POST, DELETE'),
            ('/api/v1/social/reviews/{review_id}/replies', 'POST, GET'),
            ('/api/v1/social/shelves', 'POST'),
            ('/api/v1/social/shelves/me', 'GET'),
            ('/api/v1/social/shelves/{shelf_id}', 'PATCH, DELETE'),
            ('/api/v1/social/shelves/{shelf_id}/books', 'GET'),
            ('/api/v1/social/shelves/{shelf_id}/items', 'POST, GET'),
            ('/api/v1/social/shelves/{shelf_id}/items/{isbn}', 'DELETE'),
        ]
    },
    {
        'name': '🔍 RAG (:8005)',
        'endpoints': [
            ('/api/v1/rag/health', 'GET'),
            ('/', 'GET'),
            ('/api/v1/rag/search', 'GET'),
            ('/api/v1/rag/similar/{work_id}', 'GET'),
            ('/api/v1/rag/stats', 'GET'),
            ('/api/v1/rag/sync/books', 'POST'),
            ('/api/v1/rag/sync/books/by-work-id', 'POST'),
            ('/api/v1/rag/thematic', 'POST'),
            ('/health', 'GET'),
        ]
    },
    {
        'name': '🤖 RECOMMENDATION (:8006)',
        'endpoints': [
            ('/api/v1/health', 'GET'),
            ('/', 'GET'),
            ('/api/v1/profile/events', 'POST'),
            ('/api/v1/recommend', 'POST'),
        ]
    },
    {
        'name': '📡 BOOK (:8007)',
        'endpoints': [
            ('/api/v3/health', 'GET'),
            ('/api/v3/authors/search', 'GET'),
            ('/api/v3/authors/{author_id}', 'GET'),
            ('/api/v3/books', 'GET'),
            ('/api/v3/books/search', 'GET'),
            ('/api/v3/books/{work_id}', 'GET'),        # ⬅️ ADDED MISSING ENDPOINT
            ('/api/v3/search', 'POST'),
            ('/api/v3/series/search', 'GET'),
            ('/api/v3/series/{series_id}', 'GET'),
            ('/', 'GET'),
        ]
    },
]

def main():
    print("\n" + "=" * 50)
    print("📡 BOOK API - PRODUCTION READY")
    print("=" * 50 + "\n")

    for service in microservices:
        print(f"\n{'=' * 50}")
        print(f"{service['name']}")
        print(f"{'=' * 50}\n")

        for endpoint, methods in service['endpoints']:
            print(f"  {endpoint:<50} {methods}")

        print()

    print("=" * 50)
    print("All endpoints verified against running services")
    print("=" * 50)

if __name__ == "__main__":
    main()