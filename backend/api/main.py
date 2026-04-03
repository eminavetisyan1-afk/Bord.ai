import asyncio
import hashlib
import json
import os
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.config import AGENTS, PANEL_PRESETS
from backend.database import init_db, close_db, get_pool
from backend.sessions import list_sessions, get_session, delete_session
from backend.projects import (
    create_project, list_projects, get_project,
    update_project, delete_project,
)
from backend.graph.runner import run_board
from backend.users import (
    create_user, get_user_by_username, get_user_by_id,
    list_users, update_user, delete_user,
    hash_password, verify_password,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(title="Virtual AI Board", version="3.0", lifespan=lifespan)

# ── Директория загрузок ──────────────────────────────────────────────────

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".py", ".js", ".ts", ".html", ".css",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# ── Rate limiting (простой in-memory) ────────────────────────────────────

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


# ── Модели ───────────────────────────────────────────────────────────────

class BoardRequest(BaseModel):
    question: str = Field(..., max_length=10000)
    mode: str = Field(..., pattern="^(solo|panel|fullboard|devils_advocate|premortem|quarterly)$")
    agents: list[str] = Field(default_factory=list)
    project_id: str = Field(default="")


class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=200)
    brief: str = Field(default="", max_length=50000)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    brief: Optional[str] = Field(default=None, max_length=50000)


class UserCreate(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., min_length=3, max_length=200)
    display_name: str = Field(default="", max_length=200)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=3, max_length=200)


# ── Аутентификация ───────────────────────────────────────────────────────

def _make_token(user_id: str, password_hash: str) -> str:
    """Генерировать дневной токен для пользователя."""
    day = int(time.time() // 86400)
    return hashlib.sha256(f"{user_id}:{password_hash}:{day}".encode()).hexdigest()


@app.post("/auth")
async def auth(request: Request):
    """Авторизация по логину и паролю."""
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    if not username or not password:
        raise HTTPException(401, "Введите логин и пароль")

    user = await get_user_by_username(username)
    if not user:
        raise HTTPException(401, "Неверный логин или пароль")

    if not verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Неверный логин или пароль")

    if not user["is_active"]:
        raise HTTPException(403, "Аккаунт деактивирован")

    token = _make_token(user["id"], user["password_hash"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        },
    }


@app.get("/auth/check")
async def auth_check(request: Request):
    """Проверить валидность токена, вернуть данные пользователя."""
    user = await _verify_token(request)
    return {
        "valid": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        },
    }


async def _verify_token(request: Request) -> dict:
    """Проверить токен из заголовка Authorization. Возвращает dict пользователя или кидает 401."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Требуется авторизация")

    # Перебираем всех активных пользователей и ищем совпадение токена
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, username, password_hash, display_name, role, is_active FROM users WHERE is_active = TRUE")

    for row in rows:
        expected = _make_token(row["id"], row["password_hash"])
        if token == expected:
            return dict(row)

    raise HTTPException(401, "Требуется авторизация")


async def _require_admin(request: Request) -> dict:
    """Проверить токен и убедиться что пользователь — админ."""
    user = await _verify_token(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Требуются права администратора")
    return user


# ── Маршруты ─────────────────────────────────────────────────────────────

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


# ── Проекты ──────────────────────────────────────────────────────────────

@app.get("/projects")
async def projects_list(request: Request):
    user = await _verify_token(request)
    return await list_projects(user_id=user["id"])


@app.post("/projects")
async def project_create(req: ProjectCreate, request: Request):
    user = await _verify_token(request)
    return await create_project(req.name, req.brief, user_id=user["id"])


@app.get("/projects/{project_id}")
async def project_detail(project_id: str, request: Request):
    user = await _verify_token(request)
    p = await get_project(project_id, user_id=user["id"])
    if not p:
        raise HTTPException(404, "Проект не найден")
    return p


@app.put("/projects/{project_id}")
async def project_update(project_id: str, req: ProjectUpdate, request: Request):
    user = await _verify_token(request)
    p = await update_project(project_id, req.name, req.brief, user_id=user["id"])
    if not p:
        raise HTTPException(404, "Проект не найден")
    return p


@app.delete("/projects/{project_id}")
async def project_delete(project_id: str, request: Request):
    user = await _verify_token(request)
    if await delete_project(project_id, user_id=user["id"]):
        return {"status": "deleted"}
    raise HTTPException(404, "Проект не найден")


# ── Сессии ───────────────────────────────────────────────────────────────

@app.get("/sessions")
async def sessions_list(request: Request, project_id: Optional[str] = Query(default=None)):
    user = await _verify_token(request)
    return await list_sessions(20, project_id=project_id, user_id=user["id"])


@app.get("/sessions/{session_id}")
async def session_detail(session_id: str, request: Request):
    user = await _verify_token(request)
    s = await get_session(session_id, user_id=user["id"])
    if not s:
        raise HTTPException(404, "Сессия не найдена")
    return s


@app.delete("/sessions/{session_id}")
async def session_delete(session_id: str, request: Request):
    user = await _verify_token(request)
    if await delete_session(session_id, user_id=user["id"]):
        return {"status": "deleted"}
    raise HTTPException(404, "Сессия не найдена")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Загрузка файлов ──────────────────────────────────────────────────────

@app.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    await _verify_token(request)

    if not file.filename:
        raise HTTPException(400, "Нет файла")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Тип файла {ext} не поддерживается")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "Файл слишком большой (макс. 10MB)")

    # Извлечь текст из файла
    text_content = ""
    if ext in {".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
               ".py", ".js", ".ts", ".html", ".css"}:
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_content = content.decode("latin-1")
            except Exception:
                text_content = "[Не удалось прочитать файл]"
    elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        text_content = f"[Изображение: {file.filename}]"
    else:
        text_content = f"[Файл: {file.filename}, {len(content)} байт]"

    # Обрезать слишком длинные файлы
    if len(text_content) > 50000:
        text_content = text_content[:50000] + f"\n\n[...обрезано, всего {len(text_content)} символов]"

    return {
        "filename": file.filename,
        "size": len(content),
        "text": text_content,
    }


# ── Борд ─────────────────────────────────────────────────────────────────

@app.post("/board")
async def board_endpoint(req: BoardRequest, request: Request):
    user = await _verify_token(request)

    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(429, "Превышен лимит запросов. Подождите минуту.")

    # Валидация агентов
    valid_agents = [a for a in req.agents if a in AGENTS]
    if req.mode == "solo":
        if not valid_agents:
            raise HTTPException(400, "Выберите хотя бы одного агента для режима Соло.")
        valid_agents = valid_agents[:1]
    elif req.mode == "quarterly":
        pass  # quarterly сам выбирает оценщиков
    elif req.mode == "fullboard":
        valid_agents = list(AGENTS.keys())
    else:
        if not valid_agents:
            raise HTTPException(400, "Выберите хотя бы одного агента.")

    queue = await run_board(
        req.question, req.mode, valid_agents,
        project_id=req.project_id, user_id=user["id"],
    )

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


# ── Админ-панель ─────────────────────────────────────────────────────────

@app.get("/admin/users")
async def admin_users_list(request: Request):
    """Список всех пользователей (только для админа)."""
    await _require_admin(request)
    return await list_users()


@app.post("/admin/users")
async def admin_user_create(req: UserCreate, request: Request):
    """Создать нового пользователя (только для админа)."""
    await _require_admin(request)

    # Проверить уникальность username
    existing = await get_user_by_username(req.username)
    if existing:
        raise HTTPException(400, f"Пользователь '{req.username}' уже существует")

    user = await create_user(
        username=req.username,
        password=req.password,
        display_name=req.display_name,
        role=req.role,
    )
    return user


@app.put("/admin/users/{user_id}")
async def admin_user_update(user_id: str, req: UserUpdate, request: Request):
    """Обновить пользователя (только для админа)."""
    await _require_admin(request)

    updated = await update_user(
        user_id=user_id,
        display_name=req.display_name,
        role=req.role,
        is_active=req.is_active,
        password=req.password,
    )
    if not updated:
        raise HTTPException(404, "Пользователь не найден")
    return updated


@app.delete("/admin/users/{user_id}")
async def admin_user_delete(user_id: str, request: Request):
    """Удалить пользователя и все его данные (только для админа)."""
    admin = await _require_admin(request)

    # Нельзя удалить самого себя
    if user_id == admin["id"]:
        raise HTTPException(400, "Нельзя удалить свой аккаунт")

    if await delete_user(user_id):
        return {"status": "deleted"}
    raise HTTPException(404, "Пользователь не найден")


@app.get("/admin/stats")
async def admin_stats(request: Request):
    """Статистика платформы (только для админа)."""
    await _require_admin(request)

    pool = await get_pool()
    async with pool.acquire() as conn:
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        projects_count = await conn.fetchval("SELECT COUNT(*) FROM projects")
        sessions_count = await conn.fetchval("SELECT COUNT(*) FROM sessions")

    return {
        "users": users_count,
        "projects": projects_count,
        "sessions": sessions_count,
    }
