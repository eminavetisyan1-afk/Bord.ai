from __future__ import annotations

import asyncpg
import json
import os
from backend.config import DATA_DIR

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def init_db():
    """Create tables if they don't exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                brief TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT DEFAULT '',
                ts TEXT NOT NULL,
                mode TEXT NOT NULL,
                question TEXT NOT NULL,
                agents TEXT DEFAULT '[]',
                data JSONB DEFAULT '{}'
            )
        """)


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
