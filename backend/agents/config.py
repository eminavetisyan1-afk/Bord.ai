from backend.config import OPUS_MODEL, SONNET_MODEL, HAIKU_MODEL

AGENTS: dict[str, dict] = {
    # ── Продукт и UX ─────────────────────────────────────────────────────
    "jobs": {
        "name": "Стив Джобс",
        "name_en": "Steve Jobs",
        "role": "Продуктовое видение и UX",
        "model": SONNET_MODEL,
        "emoji": "\U0001f34e",
        "color": "#FF6B6B",
        "bg": "#1a0d0d",
    },
    "chesky": {
        "name": "Брайан Чески",
        "name_en": "Brian Chesky",
        "role": "Культура и дизайн-мышление",
        "model": SONNET_MODEL,
        "emoji": "\U0001f3e0",
        "color": "#FB923C",
        "bg": "#1a0f08",
    },
    "collison": {
        "name": "Патрик Коллисон",
        "name_en": "Patrick Collison",
        "role": "Продуктовая инженерия",
        "model": SONNET_MODEL,
        "emoji": "\U0001f527",
        "color": "#F472B6",
        "bg": "#1a0d14",
    },
    # ── Стартап и стратегия ───────────────────────────────────────────────
    "graham": {
        "name": "Пол Грэм",
        "name_en": "Paul Graham",
        "role": "Стартап-философия",
        "model": OPUS_MODEL,
        "emoji": "\U0001f680",
        "color": "#4ECDC4",
        "bg": "#0d1a19",
    },
    "naval": {
        "name": "Навал Равикант",
        "name_en": "Naval Ravikant",
        "role": "Leverage и mental models",
        "model": OPUS_MODEL,
        "emoji": "\u2693",
        "color": "#A78BFA",
        "bg": "#100d1a",
    },
    "churchill": {
        "name": "Уинстон Черчилль",
        "name_en": "Winston Churchill",
        "role": "Стратегия и кризисное лидерство",
        "model": SONNET_MODEL,
        "emoji": "\U0001f396\ufe0f",
        "color": "#C39BD3",
        "bg": "#130d1a",
    },
    # ── Финансы и риски ───────────────────────────────────────────────────
    "buffett": {
        "name": "Уоррен Баффет",
        "name_en": "Warren Buffett",
        "role": "Риски и капитал",
        "model": OPUS_MODEL,
        "emoji": "\U0001f4b0",
        "color": "#F7DC6F",
        "bg": "#1a1a0d",
    },
    "andreessen": {
        "name": "Марк Андриссен",
        "name_en": "Marc Andreessen",
        "role": "Рынок и венчурное мышление",
        "model": SONNET_MODEL,
        "emoji": "\U0001f981",
        "color": "#F97316",
        "bg": "#1a0e07",
    },
    "altman": {
        "name": "Сэм Альтман",
        "name_en": "Sam Altman",
        "role": "Масштабирование и фандрейзинг",
        "model": SONNET_MODEL,
        "emoji": "\U0001f9ec",
        "color": "#34D399",
        "bg": "#0a1a12",
    },
    # ── AI и технологии ───────────────────────────────────────────────────
    "karpathy": {
        "name": "Андрей Карпатий",
        "name_en": "Andrej Karpathy",
        "role": "AI/ML стратегия",
        "model": OPUS_MODEL,
        "emoji": "\U0001f916",
        "color": "#5DADE2",
        "bg": "#0d1219",
    },
    "huang": {
        "name": "Дженсен Хуанг",
        "name_en": "Jensen Huang",
        "role": "Инфраструктура и технобеты",
        "model": SONNET_MODEL,
        "emoji": "\u26a1",
        "color": "#76C442",
        "bg": "#0d1a0a",
    },
    "hassabis": {
        "name": "Демис Хасабис",
        "name_en": "Demis Hassabis",
        "role": "AGI стратегия и исследования",
        "model": OPUS_MODEL,
        "emoji": "\U0001f9e0",
        "color": "#60A5FA",
        "bg": "#0a0f1a",
    },
    "torvalds": {
        "name": "Линус Торвальдс",
        "name_en": "Linus Torvalds",
        "role": "Инженерная культура",
        "model": SONNET_MODEL,
        "emoji": "\U0001f427",
        "color": "#94A3B8",
        "bg": "#0f1117",
    },
    # ── Личная эффективность ──────────────────────────────────────────────
    "goggins": {
        "name": "Дэвид Гоггинс",
        "name_en": "David Goggins",
        "role": "Дисциплина и ментальная стойкость",
        "model": SONNET_MODEL,
        "emoji": "\U0001f480",
        "color": "#EF4444",
        "bg": "#1a0808",
    },
    "grove": {
        "name": "Энди Гроув",
        "name_en": "Andy Grove",
        "role": "Менеджмент и OKR",
        "model": OPUS_MODEL,
        "emoji": "\U0001f4ca",
        "color": "#FCD34D",
        "bg": "#1a1508",
    },
}

ORCHESTRATOR = {
    "model": "claude-opus-4-5",
    "name": "Оркестратор",
}

DEVILS_ADVOCATE_AGENTS = ["buffett", "torvalds", "graham", "goggins"]

PANEL_PRESETS: dict[str, list[str]] = {
    "product": ["jobs", "graham", "chesky", "collison"],
    "tech": ["karpathy", "torvalds", "hassabis", "huang"],
    "fundraising": ["andreessen", "altman", "buffett", "naval"],
    "crisis": ["churchill", "chesky", "buffett", "graham"],
    "ai_strategy": ["karpathy", "hassabis", "altman", "huang"],
    "strategy": ["buffett", "naval", "hassabis", "huang", "churchill"],
    "discipline": ["goggins", "buffett", "grove", "churchill"],
    "management": ["grove", "chesky", "collison", "graham"],
    "personal": ["goggins", "grove", "naval", "buffett"],
    "default": ["jobs", "graham", "buffett"],
}
