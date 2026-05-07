import asyncio
from book.enrichment_engine import enrichment_engine
async def main():
    try:
        res = await enrichment_engine.enrich_books_from_query('Adania Shibli', include_arabic=False)
        print([r.title for r in res])
    except Exception as e:
        import traceback
        traceback.print_exc()
asyncio.run(main())
