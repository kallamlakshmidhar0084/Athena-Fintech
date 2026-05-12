"""Async database manager for Athena.

Single entry point for the SQLAlchemy async engine, session factory, and
connection lifecycle. Mirrors the shape of ``athena.llm.client``: one class,
one module-level instance, smoke test at the bottom.

Usage
-----

Direct session (services, scripts)::

    from athena.storage import db

    async with db.session() as session:
        result = await session.execute(text("SELECT 1"))
        ...
        await session.commit()    # caller commits explicitly

FastAPI dependency (api/deps.py later)::

    async def get_db() -> AsyncIterator[AsyncSession]:
        async with db.session() as session:
            yield session

Shutdown hook (api/main.py later)::

    await db.close()
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from athena.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Async SQLAlchemy engine + session factory.

    Pool defaults are appropriate for one dev process. In Phase 3 we tune
    them per deployment (FastAPI workers × pool_size = total connections).
    """

    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or settings.database_url
        self._engine: AsyncEngine = create_async_engine(
            url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,    # ping before each checkout; survives DB restarts
            pool_recycle=3600,     # recycle connections hourly to avoid staleness
        )
        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,    # objects stay usable after commit
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session. Auto-rollback on exception, auto-close at exit.

        Does NOT auto-commit. Callers commit explicitly when they're ready.
        """
        async with self._sessionmaker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def ping(self) -> bool:
        """Quick connectivity check. ``SELECT 1`` round-trip."""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("db ping failed: %s", exc)
            return False

    async def ensure_pgvector(self) -> None:
        """Create the pgvector extension if it doesn't exist. Idempotent."""
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    async def close(self) -> None:
        """Dispose the connection pool. Call at app shutdown."""
        await self._engine.dispose()


db = DatabaseManager()


# ---------------------------------------------------------------------------
# Smoke test — run as ``python -m athena.storage.db_manager``
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _smoke() -> None:
        # Don't leak the password in logs; show host/db/user only.
        print(f"host: {settings.db_host}:{settings.db_port}")
        print(f"db:   {settings.db_name}")
        print(f"user: {settings.db_user}\n")

        print("[ping]")
        ok = await db.ping()
        print(f"  {'OK' if ok else 'FAILED'}\n")
        if not ok:
            print("Is docker compose up? Check: docker compose ps")
            return

        print("[ensure pgvector]")
        await db.ensure_pgvector()
        async with db.engine.connect() as conn:
            result = await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            )
            version = result.scalar_one()
        print(f"  pgvector v{version}\n")

        print("[session + server version]")
        async with db.session() as sess:
            result = await sess.execute(text("SELECT version()"))
            server_version = result.scalar_one()
        print(f"  {server_version.split(',')[0]}\n")

        await db.close()
        print("OK — db_manager works")

    asyncio.run(_smoke())
