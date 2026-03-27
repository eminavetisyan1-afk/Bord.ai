from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

PROJECTS_FILE = Path(__file__).parent.parent / "projects.json"


def _load() -> list[dict]:
    if not PROJECTS_FILE.exists():
        return []
    try:
        data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(projects: list[dict]) -> None:
    PROJECTS_FILE.write_text(
        json.dumps(projects, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_project(name: str, brief: str = "") -> dict:
    projects = _load()
    project = {
        "id": str(uuid.uuid4()),
        "name": name,
        "brief": brief,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    projects.insert(0, project)
    _save(projects)
    return project


def list_projects() -> list[dict]:
    return _load()


def get_project(project_id: str) -> dict | None:
    for p in _load():
        if p["id"] == project_id:
            return p
    return None


def update_project(project_id: str, name: str | None = None, brief: str | None = None) -> dict | None:
    projects = _load()
    for p in projects:
        if p["id"] == project_id:
            if name is not None:
                p["name"] = name
            if brief is not None:
                p["brief"] = brief
            p["updated_at"] = datetime.now().isoformat(timespec="seconds")
            _save(projects)
            return p
    return None


def delete_project(project_id: str) -> bool:
    projects = _load()
    original_len = len(projects)
    projects = [p for p in projects if p["id"] != project_id]
    if len(projects) < original_len:
        _save(projects)
        return True
    return False
