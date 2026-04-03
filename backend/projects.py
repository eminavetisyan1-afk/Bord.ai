from __future__ import annotations

import uuid
from datetime import datetime

from backend.database import get_pool


async def create_project(name: str, brief: str = "", user_id: str = "") -> dict:
    pool = await get_pool()
    project = {
        "id": str(uuid.uuid4()),
        "name": name,
        "brief": brief,
        "user_id": user_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name, brief, user_id, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6)",
            project["id"], project["name"], project["brief"], project["user_id"],
            project["created_at"], project["updated_at"],
        )
    return project


async def list_projects(user_id: str = "") -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM projects WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
    return [dict(r) for r in rows]


async def get_project(project_id: str, user_id: str | None = None) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id is not None:
            row = await conn.fetchrow(
                "SELECT * FROM projects WHERE id = $1 AND user_id = $2",
                project_id, user_id,
            )
        else:
            row = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
    return dict(row) if row else None


async def update_project(project_id: str, name: str | None = None, brief: str | None = None, user_id: str | None = None) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id is not None:
            row = await conn.fetchrow(
                "SELECT * FROM projects WHERE id = $1 AND user_id = $2",
                project_id, user_id,
            )
        else:
            row = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        if not row:
            return None
        new_name = name if name is not None else row["name"]
        new_brief = brief if brief is not None else row["brief"]
        updated_at = datetime.now().isoformat(timespec="seconds")
        await conn.execute(
            "UPDATE projects SET name = $1, brief = $2, updated_at = $3 WHERE id = $4",
            new_name, new_brief, updated_at, project_id,
        )
        return {"id": project_id, "name": new_name, "brief": new_brief,
                "user_id": row["user_id"], "created_at": row["created_at"], "updated_at": updated_at}


async def delete_project(project_id: str, user_id: str | None = None) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id is not None:
            result = await conn.execute(
                "DELETE FROM projects WHERE id = $1 AND user_id = $2",
                project_id, user_id,
            )
        else:
            result = await conn.execute("DELETE FROM projects WHERE id = $1", project_id)
    return result == "DELETE 1"
