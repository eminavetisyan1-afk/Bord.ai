from __future__ import annotations

import asyncpg
import hashlib
import os

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def init_db():
    """Создать таблицы и выполнить миграции."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Таблица пользователей
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'user',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TEXT NOT NULL
            )
        """)

        # Таблица проектов
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                brief TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Таблица сессий
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

        # Миграция: добавить user_id в projects и sessions (если ещё нет)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'projects' AND column_name = 'user_id'
                ) THEN
                    ALTER TABLE projects ADD COLUMN user_id TEXT DEFAULT '';
                END IF;
            END $$;
        """)

        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'sessions' AND column_name = 'user_id'
                ) THEN
                    ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT '';
                END IF;
            END $$;
        """)

        # Создать администратора по умолчанию (если ещё нет)
        existing = await conn.fetchrow("SELECT id FROM users WHERE username = 'admin'")
        if not existing:
            from datetime import datetime
            import uuid
            admin_hash = hashlib.sha256("grachik".encode()).hexdigest()
            await conn.execute(
                """INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                str(uuid.uuid4()), "admin", admin_hash,
                "Администратор", "admin", True,
                datetime.now().isoformat(timespec="seconds"),
            )


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
