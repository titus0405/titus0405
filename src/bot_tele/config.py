"""Configuration loading for the Telegram + AI model bot."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import override

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration loaded from .env (if present) then the environment.

    The model backend is any OpenAI-compatible endpoint. ``openrouter_base_url``
    selects where requests go (OpenRouter by default, or a local server such as
    Ollama or LM Studio). The API key and OpenRouter-only headers are optional
    so local servers that need no auth work unchanged.
    """

    telegram_token: str
    openrouter_api_key: str
    openrouter_base_url: str
    openrouter_model: str
    openrouter_referer: str
    openrouter_title: str
    history_dir: Path
    max_history: int
    max_file_chars: int
    admin_ids: frozenset[int]


@dataclass(frozen=True, slots=True)
class MissingConfigError(Exception):
    """Raised when a required environment variable is absent."""

    key: str

    @override
    def __str__(self) -> str:
        return f"Missing required environment variable: {self.key}"


def _require(name: str) -> str:
    """Return a non-empty env var, or raise MissingConfigError."""
    value = os.environ.get(name)
    if not value:
        raise MissingConfigError(key=name)
    return value


def _require_int(name: str, default: int) -> int:
    """Return an integer env var, or fall back to default when unset."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _parse_admin_ids(name: str) -> frozenset[int]:
    """Parse a comma-separated list of Telegram user IDs into a set.

    Empty/missing resolves to an empty set, which fail-closed means no one
    may upload until admins are configured.
    """
    raw = os.environ.get(name)
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for piece in raw.split(","):
        stripped = piece.strip()
        if not stripped:
            continue
        ids.add(int(stripped))
    return frozenset(ids)


def load_settings() -> Settings:
    """Load configuration from .env (if present) then the environment."""
    _ = load_dotenv()
    return Settings(
        telegram_token=_require("TELEGRAM_BOT_TOKEN"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        openrouter_base_url=os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ),
        openrouter_model=os.environ.get(
            "OPENROUTER_MODEL", "openai/gpt-oss-120b:free"
        ),
        openrouter_referer=os.environ.get("OPENROUTER_REFERER", ""),
        openrouter_title=os.environ.get("OPENROUTER_TITLE", ""),
        history_dir=Path(os.environ.get("HISTORY_DIR", "data")),
        max_history=_require_int("MAX_HISTORY", 20),
        max_file_chars=_require_int("MAX_FILE_CHARS", 50_000),
        admin_ids=_parse_admin_ids("ADMIN_IDS"),
    )
