"""Settings loaded from environment variables (or a .env file next to pyproject.toml)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
CAPTION_FONT = "Inter Display Black"

load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    anthropic_api_key: str | None
    claude_model: str
    whisper_model: str
    access_token: str
    max_clips: int
    host: str
    port: int

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


def _load_or_create_token(data_dir: Path) -> str:
    """Use CLIPPY_TOKEN if set, otherwise a random token persisted in the data dir.

    Persisting it means the phone only has to be set up once.
    """
    env_token = os.environ.get("CLIPPY_TOKEN", "").strip()
    if env_token:
        return env_token
    token_file = data_dir / "access_token.txt"
    if token_file.exists():
        token = token_file.read_text().strip()
        if token:
            return token
    token = secrets.token_hex(3).upper()  # short enough to type on a phone
    token_file.write_text(token)
    return token


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.environ.get("CLIPPY_DATA_DIR", BACKEND_DIR / "data")).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=data_dir,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        claude_model=os.environ.get("CLAUDE_MODEL", "claude-opus-5-5"),
        whisper_model=os.environ.get("WHISPER_MODEL", "small"),
        access_token=_load_or_create_token(data_dir),
        max_clips=int(os.environ.get("CLIPPY_MAX_CLIPS", "8")),
        host=os.environ.get("CLIPPY_HOST", "0.0.0.0"),
        port=int(os.environ.get("CLIPPY_PORT", "8000")),
    )
