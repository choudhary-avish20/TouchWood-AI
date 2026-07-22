"""
config.py — single source of truth for all project settings.

Every module imports from here instead of hardcoding values or reading
os.getenv() themselves. To override any default, set the corresponding
environment variable (e.g. in a .env file loaded by python-dotenv, or
directly in your shell / deployment environment).

Usage:
    from config import DB_PATH, OLLAMA_BASE_URL, ALLOWED_STYLE_TAGS
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# Paths

DB_PATH: str = os.getenv("DB_PATH", "data/catalog.db")

# Catalog ingestion
# Number of items fetched per API page during catalog refresh.
CATALOG_PAGE_SIZE: int = int(os.getenv("CATALOG_PAGE_SIZE", "100"))


ALLOWED_STYLE_TAGS: list[str] = [
    "minimalist", "scandinavian", "mid-century", "rustic", "bohemian",
    "industrial", "modern", "traditional", "coastal", "glam",
    "farmhouse", "japandi", "art-deco", "eclectic",
]

# Ollama (local extraction + tagging)

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_GENERATE_URL: str = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL: str = f"{OLLAMA_BASE_URL}/api/tags"

# Preferred local model for both tagging (catalog/tagger.py) and extraction
# (extraction/extractor.py). Falls back to auto-detecting the first available
# model from the Ollama /api/tags endpoint if unset.
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "")


OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_TIMEOUT_SECONDS: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30"))

# Sentence-transformers (local embeddings)

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Anthropic API (recommendation layer)

ANTHROPIC_MODEL: str = os.getenv(
    "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
)

ANTHROPIC_MAX_TOKENS: int = int(os.getenv("ANTHROPIC_MAX_TOKENS", "600"))

# Retrieval

RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "8"))

# State merge

# Jaccard similarity threshold for deduplicating item_requests across turns.
# 0.6 catches near-duplicates ("a lamp" / "some kind of lamp") while keeping
# genuinely different requests ("floor lamp" / "desk lamp") separate.
PHRASE_SIMILARITY_THRESHOLD: float = float(
    os.getenv("PHRASE_SIMILARITY_THRESHOLD", "0.6")
)

# App / API server

APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
APP_DEBUG: bool = os.getenv("APP_DEBUG", "false").lower() == "true"

_raw_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080"
)
CORS_ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL_SECONDS", "1800"))  # 30 min