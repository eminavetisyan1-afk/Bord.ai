from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SESSIONS_FILE = Path(__file__).parent.parent / "sessions.json"


def _load() -> list[dict]:
    if not SESSIONS_FILE.exists():
        return []
    try:
        data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(sessions: list[dict]) -> None:
    SESSIONS_FILE.write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_session(session: dict) -> None:
    sessions = _load()
    session.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    sessions.insert(0, session)
    _save(sessions)


def list_sessions(n: int = 20, project_id: str | None = None) -> list[dict]:
    sessions = _load()
    if project_id is not None:
        sessions = [s for s in sessions if s.get("project_id") == project_id]
    result = []
    for s in sessions[:n]:
        result.append({
            "id": s["id"],
            "ts": s["ts"],
            "mode": s["mode"],
            "question": s["question"][:120],
            "agents": s.get("agents", []),
            "project_id": s.get("project_id"),
        })
    return result


def get_session(session_id: str) -> dict | None:
    for s in _load():
        if s["id"] == session_id:
            return s
    return None


def delete_session(session_id: str) -> bool:
    sessions = _load()
    original_len = len(sessions)
    sessions = [s for s in sessions if s["id"] != session_id]
    if len(sessions) < original_len:
        _save(sessions)
        return True
    return False


def get_recent_context(n: int = 3, project_id: str | None = None) -> str:
    """Return last n sessions as context string for agent memory."""
    sessions = _load()
    if project_id:
        sessions = [s for s in sessions if s.get("project_id") == project_id]
    sessions = sessions[:n]
    if not sessions:
        return ""
    parts = []
    for s in sessions:
        parts.append(f"[{s['ts']}] Вопрос: {s['question']}")
        if s.get("synthesis"):
            parts.append(f"Итог: {s['synthesis'][:500]}")
        parts.append("")
    return "\n".join(parts)
