import asyncio
import json
import uuid
from datetime import datetime

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from backend.config import ANTHROPIC_API_KEY, HAIKU_MODEL
from backend.agents.config import (
    AGENTS,
    ORCHESTRATOR,
    DEVILS_ADVOCATE_AGENTS,
)
from backend.agents.prompts import AGENT_PROMPTS, ORCHESTRATOR_PROMPT
from backend.graph.states import BoardState
from backend.sessions import save_session, get_recent_context
from backend.projects import get_project


def _llm(model: str) -> ChatAnthropic:
    return ChatAnthropic(
        model=model,
        api_key=ANTHROPIC_API_KEY,
        streaming=True,
        temperature=0.85,
        max_tokens=2048,
    )


async def _push(queue: asyncio.Queue, event: dict) -> None:
    await queue.put(event)


async def _stream_agent(
    agent_id: str,
    system_prompt: str,
    user_message: str,
    model: str,
    queue: asyncio.Queue,
    round_num: int,
) -> tuple[str, dict]:
    """Stream a single agent's response, pushing SSE events to queue."""
    agent_cfg = AGENTS.get(agent_id, {})
    name = agent_cfg.get("name", agent_id)

    await _push(queue, {
        "type": "agent_start",
        "agent_id": agent_id,
        "name": name,
        "round": round_num,
    })

    llm = _llm(model)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    full_text = ""
    usage_info = {"agent_id": agent_id, "model": model, "round": round_num}

    try:
        async for chunk in llm.astream(messages):
            token = chunk.content
            if token:
                full_text += token
                await _push(queue, {
                    "type": "token",
                    "agent_id": agent_id,
                    "content": token,
                    "round": round_num,
                })
    except Exception as e:
        await _push(queue, {
            "type": "error",
            "message": f"Ошибка агента {name}: {str(e)}",
        })
        full_text = f"[Ошибка: {str(e)}]"

    await _push(queue, {
        "type": "agent_done",
        "agent_id": agent_id,
        "round": round_num,
    })

    return full_text, usage_info


def _build_system_prompt(agent_id: str, context_memory: str, project_brief: str = "") -> str:
    """Build full system prompt with project brief and context memory appended."""
    base = AGENT_PROMPTS.get(agent_id, "You are a helpful advisor.")
    if project_brief:
        base += f"\n\n═══ БРИФ ПРОЕКТА ═══\n{project_brief}\n\nУчитывай этот контекст проекта при формулировке ответа."
    if context_memory:
        base += f"\n\n═══ КОНТЕКСТ ПРЕДЫДУЩИХ СЕССИЙ ═══\n{context_memory}"
    return base


async def run_solo(state: BoardState) -> None:
    """Solo mode: single agent, uses Haiku for speed/cost."""
    queue = state["queue"]
    agent_id = state["agents"][0]
    agent_cfg = AGENTS[agent_id]

    system_prompt = _build_system_prompt(agent_id, state["context_memory"], state.get("project_brief", ""))
    model = HAIKU_MODEL  # Solo = fast & cheap

    text, usage = await _stream_agent(
        agent_id, system_prompt, state["question"], model, queue, 1
    )

    state["round1_responses"][agent_id] = text
    state["usage"].append(usage)

    # Сохранить сессию
    session = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "mode": "solo",
        "question": state["question"],
        "agents": state["agents"],
        "project_id": state.get("project_id", ""),
        "user_id": state.get("user_id", ""),
        "responses": {agent_id: {"round1": text}},
        "synthesis": "",
    }
    await save_session(session)

    await _push(queue, {
        "type": "done",
        "session_id": session["id"],
        "usage": state["usage"],
    })


async def run_round1(state: BoardState) -> None:
    """Round 1: All agents answer in parallel."""
    queue = state["queue"]
    mode = state["mode"]

    async def process_agent(agent_id: str):
        agent_cfg = AGENTS[agent_id]
        system_prompt = _build_system_prompt(agent_id, state["context_memory"], state.get("project_brief", ""))
        model = agent_cfg["model"]

        user_msg = state["question"]

        if mode == "devils_advocate" and agent_id in DEVILS_ADVOCATE_AGENTS:
            user_msg += "\n\nПостарайся убить эту идею. Найди самые слабые места. Не щади."

        if mode == "premortem":
            user_msg += (
                "\n\nПредставь, что сейчас 2 года спустя и всё провалилось. "
                "Что пошло не так? Пиши как некролог проекту."
            )

        text, usage = await _stream_agent(
            agent_id, system_prompt, user_msg, model, queue, 1
        )
        state["round1_responses"][agent_id] = text
        state["usage"].append(usage)

    tasks = [process_agent(aid) for aid in state["agents"]]
    await asyncio.gather(*tasks)

    await _push(queue, {"type": "round_complete", "round": 1})


async def run_round2(state: BoardState) -> None:
    """Round 2: Agents react to each other's positions."""
    queue = state["queue"]

    # Build summary of round 1 responses
    others_summary = ""
    for aid, text in state["round1_responses"].items():
        name = AGENTS[aid]["name"]
        others_summary += f"\n{name}:\n{text}\n"

    async def process_agent(agent_id: str):
        agent_cfg = AGENTS[agent_id]
        system_prompt = _build_system_prompt(agent_id, state["context_memory"], state.get("project_brief", ""))
        model = agent_cfg["model"]

        my_round1 = state["round1_responses"].get(agent_id, "")
        user_msg = (
            f"Твоя позиция в раунде 1:\n{my_round1}\n\n"
            f"Вот что сказали другие члены борда:\n{others_summary}\n\n"
            "Отреагируй на их позиции. Где согласен, где нет, и почему. "
            "150-200 слов."
        )

        text, usage = await _stream_agent(
            agent_id, system_prompt, user_msg, model, queue, 2
        )
        state["round2_responses"][agent_id] = text
        state["usage"].append(usage)

    tasks = [process_agent(aid) for aid in state["agents"]]
    await asyncio.gather(*tasks)

    await _push(queue, {"type": "round_complete", "round": 2})


async def run_orchestrator(state: BoardState) -> None:
    """Orchestrator synthesizes all responses."""
    queue = state["queue"]

    # Build input for orchestrator
    agent_names = ", ".join(
        AGENTS[aid]["name"] for aid in state["agents"] if aid in AGENTS
    )

    responses_text = ""
    for aid in state["agents"]:
        name = AGENTS.get(aid, {}).get("name", aid)
        r1 = state["round1_responses"].get(aid, "")
        r2 = state["round2_responses"].get(aid, "")
        responses_text += f"\n── {name} ──\nПозиция: {r1}\n"
        if r2:
            responses_text += f"Реакция (раунд 2): {r2}\n"

    mode_label = {
        "panel": "Панель",
        "fullboard": "Полный борд",
        "devils_advocate": "Адвокат дьявола",
        "premortem": "Пре-мортем",
        "quarterly": "Квартальный ревью",
    }.get(state["mode"], state["mode"])

    system = ORCHESTRATOR_PROMPT.replace("{question}", state["question"]).replace(
        "{agent_names}", agent_names
    ).replace("{mode}", mode_label)

    user_msg = f"Вопрос борду: {state['question']}\n\nОтветы участников:\n{responses_text}"

    await _push(queue, {"type": "synthesis_start"})

    llm = _llm(ORCHESTRATOR["model"])
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=user_msg),
    ]

    synthesis = ""
    try:
        async for chunk in llm.astream(messages):
            token = chunk.content
            if token:
                synthesis += token
                await _push(queue, {
                    "type": "synthesis_token",
                    "content": token,
                })
    except Exception as e:
        await _push(queue, {
            "type": "error",
            "message": f"Ошибка оркестратора: {str(e)}",
        })
        synthesis = f"[Ошибка: {str(e)}]"

    state["synthesis"] = synthesis

    # Save session
    responses = {}
    for aid in state["agents"]:
        responses[aid] = {
            "round1": state["round1_responses"].get(aid, ""),
            "round2": state["round2_responses"].get(aid, ""),
        }

    session = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "mode": state["mode"],
        "question": state["question"],
        "agents": state["agents"],
        "project_id": state.get("project_id", ""),
        "user_id": state.get("user_id", ""),
        "responses": responses,
        "synthesis": synthesis,
    }
    await save_session(session)

    await _push(queue, {
        "type": "done",
        "session_id": session["id"],
        "usage": state["usage"],
    })


async def run_quarterly(state: BoardState) -> None:
    """Quarterly review: evaluators assess last 10 sessions."""
    queue = state["queue"]

    from backend.sessions import _load
    sessions = _load()[:10]

    if not sessions:
        await _push(queue, {
            "type": "error",
            "message": "Нет сохранённых сессий для квартального ревью.",
        })
        await _push(queue, {"type": "done", "session_id": "", "usage": []})
        return

    # Build sessions summary
    sessions_summary = ""
    for s in sessions:
        sessions_summary += (
            f"\n[{s['ts']}] Режим: {s['mode']}\n"
            f"Вопрос: {s['question']}\n"
        )
        if s.get("synthesis"):
            sessions_summary += f"Итог: {s['synthesis'][:300]}\n"

    evaluators = [
        "jobs", "graham", "buffett", "churchill", "karpathy",
        "torvalds", "andreessen", "naval", "goggins", "grove",
    ]
    # Only use evaluators that exist
    evaluators = [e for e in evaluators if e in AGENTS]

    eval_prompt_suffix = (
        f"\n\nПоследние сессии борда:\n{sessions_summary}\n\n"
        "Оцени качество решений и мышления за этот период. "
        "Формат: 🟢/🟡/🔴 + комментарий (2-3 предложения) + 1 вопрос.\n"
        "Goggins: оценивай дисциплину и выполнение обязательств.\n"
        "Grove: оценивай качество управленческих решений."
    )

    async def process_evaluator(agent_id: str):
        agent_cfg = AGENTS[agent_id]
        system_prompt = _build_system_prompt(agent_id, "")
        model = agent_cfg["model"]

        user_msg = state["question"] + eval_prompt_suffix

        text, usage = await _stream_agent(
            agent_id, system_prompt, user_msg, model, queue, 1
        )
        state["round1_responses"][agent_id] = text
        state["usage"].append(usage)

    tasks = [process_evaluator(aid) for aid in evaluators]
    state["agents"] = evaluators
    await asyncio.gather(*tasks)

    await _push(queue, {"type": "round_complete", "round": 1})

    # Orchestrator synthesis
    await run_orchestrator(state)


async def run_board(question: str, mode: str, agents: list[str], project_id: str = "", user_id: str = "") -> asyncio.Queue:
    """Главная точка входа: создаёт состояние и запускает граф."""
    queue: asyncio.Queue = asyncio.Queue()

    # Загрузить бриф проекта, если выбран
    project_brief = ""
    if project_id:
        project = await get_project(project_id)
        if project:
            project_brief = project.get("brief", "")

    context_memory = await get_recent_context(3, project_id=project_id or None, user_id=user_id)

    state: BoardState = {
        "question": question,
        "mode": mode,
        "agents": agents,
        "project_id": project_id,
        "project_brief": project_brief,
        "context_memory": context_memory,
        "user_id": user_id,
        "round1_responses": {},
        "round2_responses": {},
        "synthesis": "",
        "queue": queue,
        "usage": [],
    }

    async def execute():
        try:
            if mode == "solo":
                await run_solo(state)
            elif mode == "quarterly":
                await run_quarterly(state)
            elif mode == "premortem":
                await run_round1(state)
                await run_orchestrator(state)
            else:
                # panel, fullboard, devils_advocate
                await run_round1(state)
                if mode in ("panel", "fullboard", "devils_advocate") and len(agents) > 1:
                    await run_round2(state)
                await run_orchestrator(state)
        except Exception as e:
            await _push(queue, {
                "type": "error",
                "message": f"Критическая ошибка: {str(e)}",
            })
            await _push(queue, {"type": "done", "session_id": "", "usage": []})

    asyncio.create_task(execute())
    return queue
