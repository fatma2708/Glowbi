"""Central settings, loaded from .env."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Windows defaults to cp1252 when output is piped, and printing an emoji there crashes the feeder
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "glowbi.db"
PET_STATE_PATH = DATA_DIR / "pet_state.json"
SEED_DIR = DATA_DIR / "seed"
SOURCES_PATH = ROOT / "config" / "sources.yaml"
FRONTEND_DIR = ROOT / "frontend"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "openai/gpt-oss-20b")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen/qwen3.8-27b")  # preview model: change it here if Groq retires it
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
USE_EMBEDDINGS = os.getenv("USE_EMBEDDINGS", "auto").lower()

USER_AGENT = os.getenv("SCRAPER_USER_AGENT", "GlowbiBot/0.1 (personal beauty assistant; non-commercial)")
SCRAPER_DELAY = float(os.getenv("SCRAPER_DELAY_SECONDS", "2.0"))
