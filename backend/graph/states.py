from typing import TypedDict, Any


class BoardState(TypedDict):
    question: str
    mode: str  # solo|panel|fullboard|devils_advocate|premortem|quarterly
    agents: list[str]
    project_id: str  # "" if no project
    project_brief: str  # injected into agent prompts
    context_memory: str
    round1_responses: dict  # {agent_id: text}
    round2_responses: dict  # {agent_id: text}
    synthesis: str
    queue: Any  # asyncio.Queue for SSE
    usage: list[dict]
