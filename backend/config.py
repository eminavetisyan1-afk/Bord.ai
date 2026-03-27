import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "grachik")

# Persistent data directory (set to /data on Render with persistent disk)
DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent)))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Два уровня моделей для баланса качества и стоимости
OPUS_MODEL = "claude-opus-4-5"
SONNET_MODEL = "claude-sonnet-4-5"
HAIKU_MODEL = "claude-haiku-4-5-20251001"
