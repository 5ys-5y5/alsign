"""Database connection pool management using asyncpg."""

import asyncpg
from typing import Optional
from ..config import settings


class DatabasePool:
    """Manages asyncpg connection pool lifecycle."""

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> asyncpg.Pool:
        """Create and return connection pool."""
        if self._pool is None:
            if not settings.DATABASE_URL:
                raise RuntimeError("DATABASE_URL is not configured; cannot create database pool.")
            # Supabase requires SSL for connections
            # asyncpg will automatically use SSL when connecting to Supabase
            # statement_cache_size=0 is required for Supabase connection pooler compatibility
            self._pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
                command_timeout=300,  # Increased from 60s to 300s for large queries
                statement_cache_size=0,
                server_settings={
                    'application_name': 'alsign_api'
                }
            )
        return self._pool

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def get_pool(self) -> asyncpg.Pool:
        """Get the connection pool, creating it if necessary."""
        if self._pool is None:
            await self.connect()
        return self._pool

    def acquire(self):
        """
        Acquire a connection from the pool.

        This is a pass-through to the underlying asyncpg.Pool.acquire() method.
        Can be used with async context manager:
            async with db_pool.acquire() as conn:
                ...
        """
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first or use get_pool().")
        return self._pool.acquire()


# Global database pool instance
db_pool = DatabasePool()
