"""
db/session.py
Async SQLAlchemy engine and session factory.
FastAPI dependency `get_db` yields a session per request.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Create async engine — pool_pre_ping recycles stale connections
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,         # Log SQL in debug mode
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Session factory — expire_on_commit=False prevents lazy-load issues in async
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async DB session.
    Automatically commits on success and rolls back on exception.

    Usage:
        async def endpoint(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Create all tables on startup (development only).
    In production, use Alembic migrations instead.
    """
    from app.db.base import Base
    # Import all models so Base knows about them
    import app.models.user       # noqa: F401
    import app.models.role       # noqa: F401
    import app.models.document   # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
