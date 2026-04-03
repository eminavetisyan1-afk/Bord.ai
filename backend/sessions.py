from __future__ import annotations

import json
from datetime import datetime

from backend.database import get_pool


async def save_session(session: dict) -> None:
    pool = await get_pool()
    session.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    agents_json = json.dumps(session.get("agents", []), ensure_ascii=False)
    # Сохраняем полные данные сессии как JSONB
    data = {k: v for k, v in session.items() if k not in ("id", "project_id", "user_id", "ts", "mode", "question", "agents")}
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO sessions (id, project_id, user_id, ts, mode, question, agents, data)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (id) DO UPDATE SET data = $8""",
            session["id"], session.get("project_id", ""), session.get("user_id", ""),
            session["ts"], session["mode"], session["question"], agents_json,
            json.dumps(data, ensure_ascii=False),
        )


async def list_sessions(n: int = 20, project_id: str | None = None, user_id: str = "") -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if project_id is not None:
            rows = await conn.fetch(
                "SELECT id, ts, mode, question, agents, project_id FROM sessions WHERE project_id = $1 AND user_id = $2 ORDER BY ts DESC LIMIT $3",
                project_id, user_id, n,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, ts, mode, question, agents, project_id FROM sessions WHERE user_id = $1 ORDER BY ts DESC LIMIT $2",
                user_id, n,
            )
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "ts": r["ts"],
            "mode": r["mode"],
            "question": r["question"][:120],
            "agents": json.loads(r["agents"]) if r["agents"] else [],
            "project_id": r["project_id"],
        })
    return result


async def get_session(session_id: str, user_id: str | None = None) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id is not None:
            row = await conn.fetchrow(
                "SELECT * FROM sessions WHERE id = $1 AND user_id = $2",
                session_id, user_id,
            )
        else:
            row = await conn.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
    if not row:
        return None
    session = {
        "id": row["id"],
        "project_id": row["project_id"],
        "ts": row["ts"],
        "mode": row["mode"],
        "question": row["question"],
        "agents": json.loads(row["agents"]) if row["agents"] else [],
    }
    if row["data"]:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        session.update(data)
    return session


async def delete_session(session_id: str, user_id: str | None = None) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id is not None:
            result = await conn.execute(
                "DELETE FROM sessions WHERE id = $1 AND user_id = $2",
                session_id, user_id,
            )
        else:
            result = await conn.execute("DELETE FROM sessions WHERE id = $1", session_id)
    return result == "DELETE 1"


async def get_recent_context(n: int = 3, project_id: str | None = None, user_id: str = "") -> str:
    """Вернуть последние n сессий как контекст для памяти агентов."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if project_id:
            rows = await conn.fetch(
                "SELECT ts, question, data FROM sessions WHERE project_id = $1 AND user_id = $2 ORDER BY ts DESC LIMIT $3",
                project_id, user_id, n,
            )
        else:
            rows = await conn.fetch(
                "SELECT ts, question, data FROM sessions WHERE user_id = $1 ORDER BY ts DESC LIMIT $2",
                user_id, n,
            )
    if not rows:
        return ""
    parts = []
    for r in rows:
        parts.append(f"[{r['ts']}] Вопрос: {r['question']}")
        data = r["data"]
        if data:
            if isinstance(data, str):
                data = json.loads(data)
            if data.get("synthesis"):
                parts.append(f"Итог: {data['synthesis'][:500]}")
        parts.append("")
    return "\n".join(parts)
