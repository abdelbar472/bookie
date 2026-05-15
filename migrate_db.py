#!/usr/bin/env python3
"""
Data Migration Script: Migrate from old book_service DB to new book_db_v3
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OLD_DB_NAME = "book_service"
NEW_DB_NAME = "book_db_v3"
MONGODB_URL = "mongodb://localhost:27017"

COLLECTIONS = ["books", "authors", "series"]

async def migrate_collection(client, collection_name):
    old_db = client[OLD_DB_NAME]
    new_db = client[NEW_DB_NAME]

    old_collection = old_db[collection_name]
    new_collection = new_db[collection_name]

    # Get all documents
    documents = await old_collection.find().to_list(length=None)
    logger.info(f"Found {len(documents)} documents in {collection_name}")

    if documents:
        # Insert into new db
        await new_collection.insert_many(documents)
        logger.info(f"Migrated {len(documents)} documents to {collection_name} in {NEW_DB_NAME}")

    # Optionally, create text index for books
    if collection_name == "books":
        await new_collection.create_index([("$**", "text")])
        logger.info("Created text index on books collection")

async def main():
    client = AsyncIOMotorClient(MONGODB_URL)
    try:
        for collection in COLLECTIONS:
            await migrate_collection(client, collection)
        logger.info("Migration completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(main())
