from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _migrate_user_profiles_table() -> None:
    """Best-effort SQLite migration for legacy user_profiles schema."""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(user_profiles)"))
        columns = {row[1] for row in result.fetchall()}

        if not columns:
            # Table does not exist yet; create_all will create it.
            return

        if "profile_picture" not in columns:
            await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN profile_picture VARCHAR(255)"))

        if "location" not in columns:
            await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN location VARCHAR(255)"))

        if "website" not in columns:
            await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN website VARCHAR(255)"))

        # Backfill from legacy avatar_url if present.
        if "avatar_url" in columns:
            await conn.execute(
                text(
                    """
                    UPDATE user_profiles
                    SET profile_picture = avatar_url
                    WHERE profile_picture IS NULL
                      AND avatar_url IS NOT NULL
                    """
                )
            )


async def create_db_and_tables():
    # Create tables first if they do not exist.
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Then patch older schemas in-place.
    await _migrate_user_profiles_table()


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session

