import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.config import AGENTS, PANEL_PRESETS
from backend.sessions import list_sessions, get_session, delete_session
from backend.projects import (
    create_project, list_projects, get_project,
    update_project, delete_project,
)
from backend.graph.runner import run_board

app = FastAPI(title="Virtual AI Board", version="2.1")

# ── Rate limiting (simple in-memory) ──────────────────────────────────────

_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 10
RATE_WINDOW = 60


def _check_rate_limit(client_ip: str) -> bool:
    now = time.time()
    timestamps = _rate_limits[client_ip]
    _rate_limits[client_ip] = [t for t in timestamps if now - t < RATE_WINDOW]
    if len(_rate_limits[client_ip]) >= RATE_LIMIT:
        return False
    _rate_limits[client_ip].append(now)
    return True


# ── Models ────────────────────────────────────────────────────────────────

class BoardRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    mode: str = Field(..., pattern="^(solo|panel|fullboard|devils_advocate|premortem|quarterly)$")
    agents: list[str] = Field(default_factory=list)
    project_id: str = Field(default="")


class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=200)
    brief: str = Field(default="", max_length=10000)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    brief: Optional[str] = Field(default=None, max_length=10000)


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent.parent.parent / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/agents")
async def get_agents_list():
    result = []
    for aid, cfg in AGENTS.items():
        result.append({
            "id": aid,
            "name": cfg["name"],
            "name_en": cfg["name_en"],
            "role": cfg["role"],
            "emoji": cfg["emoji"],
            "color": cfg["color"],
            "bg": cfg["bg"],
        })
    return result


@app.get("/presets")
async def get_presets():
    return PANEL_PRESETS


# ── Projects ──────────────────────────────────────────────────────────────

@app.get("/projects")
async def projects_list():
    return list_projects()


@app.post("/projects")
async def project_create(req: ProjectCreate):
    return create_project(req.name, req.brief)


@app.get("/projects/{project_id}")
async def project_detail(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Проект не найден")
    return p


@app.put("/projects/{project_id}")
async def project_update(project_id: str, req: ProjectUpdate):
    p = update_project(project_id, req.name, req.brief)
    if not p:
        raise HTTPException(404, "Проект не найден")
    return p


@app.delete("/projects/{project_id}")
async def project_delete(project_id: str):
    if delete_project(project_id):
        return {"status": "deleted"}
    raise HTTPException(404, "Проект не найден")


# ── Sessions ──────────────────────────────────────────────────────────────

@app.get("/sessions")
async def sessions_list(project_id: Optional[str] = Query(default=None)):
    return list_sessions(20, project_id=project_id)


@app.get("/sessions/{session_id}")
async def session_detail(session_id: str):
    s = get_session(session_id)
    if not s:
        raise HTTPException(404, "Сессия не найдена")
    return s


@app.delete("/sessions/{session_id}")
async def session_delete(session_id: str):
    if delete_session(session_id):
        return {"status": "deleted"}
    raise HTTPException(404, "Сессия не найдена")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Board ─────────────────────────────────────────────────────────────────

@app.post("/board")
async def board_endpoint(req: BoardRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, "Превышен лимит запросов. Подождите минуту.")

    # Validate agents
    valid_agents = [a for a in req.agents if a in AGENTS]
    if req.mode == "solo":
        if not valid_agents:
            raise HTTPException(400, "Выберите хотя бы одного агента для режима Соло.")
        valid_agents = valid_agents[:1]
    elif req.mode == "quarterly":
        pass  # quarterly picks its own evaluators
    elif req.mode == "fullboard":
        valid_agents = list(AGENTS.keys())
    else:
        if not valid_agents:
            raise HTTPException(400, "Выберите хотя бы одного агента.")

    queue = await run_board(req.question, req.mode, valid_agents, project_id=req.project_id)

    async def event_stream():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=300)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Таймаут'}, ensure_ascii=False)}\n\n"
                break

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            if event.get("type") == "done":
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
