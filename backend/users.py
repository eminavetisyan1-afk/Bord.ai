"""Модуль управления пользователями."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from backend.database import get_pool


def hash_password(password: str) -> str:
    """Хешировать пароль через SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Проверить пароль по хешу."""
    return hash_password(password) == password_hash


async def create_user(username: str, password: str, display_name: str = "", role: str = "user") -> dict:
    """Создать нового пользователя."""
    pool = await get_pool()
    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hash_password(password),
        "display_name": display_name or username,
        "role": role,
        "is_active": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            user["id"], user["username"], user["password_hash"],
            user["display_name"], user["role"], user["is_active"], user["created_at"],
        )
    # Не возвращаем password_hash наружу
    return {k: v for k, v in user.items() if k != "password_hash"}


async def get_user_by_username(username: str) -> dict | None:
    """Получить пользователя по username (включая password_hash для проверки)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", username)
    return dict(row) if row else None


async def get_user_by_id(user_id: str) -> dict | None:
    """Получить пользователя по ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return dict(row) if row else None


async def list_users() -> list[dict]:
    """Список всех пользователей (без password_hash)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, username, display_name, role, is_active, created_at FROM users ORDER BY created_at")
    return [dict(r) for r in rows]


async def update_user(
    user_id: str,
    display_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> dict | None:
    """Обновить данные пользователя."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        if not row:
            return None
        new_display = display_name if display_name is not None else row["display_name"]
        new_role = role if role is not None else row["role"]
        new_active = is_active if is_active is not None else row["is_active"]
        new_hash = hash_password(password) if password else row["password_hash"]
        await conn.execute(
            """UPDATE users SET display_name = $1, role = $2, is_active = $3, password_hash = $4
               WHERE id = $5""",
            new_display, new_role, new_active, new_hash, user_id,
        )
        return {
            "id": user_id,
            "username": row["username"],
            "display_name": new_display,
            "role": new_role,
            "is_active": new_active,
            "created_at": row["created_at"],
        }


async def delete_user(user_id: str) -> bool:
    """Удалить пользователя и все его данные."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Удаляем сессии и проекты пользователя
        await conn.execute("DELETE FROM sessions WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM projects WHERE user_id = $1", user_id)
        result = await conn.execute("DELETE FROM users WHERE id = $1", user_id)
    return result == "DELETE 1"
