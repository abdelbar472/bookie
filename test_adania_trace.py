import asyncio
from book.enrichment_engine import enrichment_engine
async def main():
    try:
        from unittest.mock import patch
        import traceback
        original = enrichment_engine._create_book_profile
        async def mock_create(work_data):
            try:
                return await original(work_data)
            except Exception as e:
                print(f"FAILED on {work_data.get('title')}")
                traceback.print_exc()
                raise
        enrichment_engine._create_book_profile = mock_create
        res = await enrichment_engine.enrich_books_from_query('Adania Shibli', include_arabic=False)
    except Exception as e:
        import traceback
        traceback.print_exc()
asyncio.run(main())
