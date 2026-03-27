from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

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


def list_sessions(n: int = 20) -> list[dict]:
    sessions = _load()
    result = []
    for s in sessions[:n]:
        result.append({
            "id": s["id"],
            "ts": s["ts"],
            "mode": s["mode"],
            "question": s["question"][:120],
            "agents": s.get("agents", []),
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


def get_recent_context(n: int = 3) -> str:
    """Return last n sessions as context string for agent memory."""
    sessions = _load()[:n]
    if not sessions:
        return ""
    parts = []
    for s in sessions:
        parts.append(f"[{s['ts']}] Вопрос: {s['question']}")
        if s.get("synthesis"):
            parts.append(f"Итог: {s['synthesis'][:500]}")
        parts.append("")
    return "\n".join(parts)
