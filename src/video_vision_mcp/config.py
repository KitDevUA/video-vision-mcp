"""Configuration loaded from a `.env` file (format-compatible with mcp-atlassian).

Backend selection is decided here, once, at startup based on which API keys are
present. See `select_backend` for the precedence rules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def _load_env() -> None:
    """Load .env from VIDEO_MCP_ENV (if set), then the nearest .env up the tree.

    `override=False` means real environment variables always win over the file,
    which matches how mcp-atlassian is typically launched by Claude Code.
    """
    explicit = os.environ.get("VIDEO_MCP_ENV")
    if explicit and Path(explicit).expanduser().is_file():
        load_dotenv(Path(explicit).expanduser(), override=False)
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=False)


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    # Jira (shared with mcp-atlassian) — used only for the jira_issue_key input path.
    jira_url: str | None
    jira_username: str | None
    jira_api_token: str | None

    # Cloud backend keys (all optional).
    openai_api_key: str | None
    groq_api_key: str | None
    gemini_api_key: str | None

    # Tier 1 local transcription.
    whisper_model: str
    whisper_model_path: str | None

    # Tier 3 native.
    gemini_model: str
    disable_gemini: bool

    # Frame extraction budget.
    max_frames: int
    min_frames: int
    frame_max_px: int

    cache_dir: Path

    @classmethod
    def load(cls) -> "Config":
        _load_env()
        cache_dir = os.environ.get("VIDEO_MCP_CACHE_DIR")
        return cls(
            jira_url=os.environ.get("JIRA_URL"),
            jira_username=os.environ.get("JIRA_USERNAME"),
            jira_api_token=os.environ.get("JIRA_API_TOKEN"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            groq_api_key=os.environ.get("GROQ_API_KEY"),
            # Accept either name; GEMINI_API_KEY wins.
            gemini_api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
            whisper_model=os.environ.get("VIDEO_MCP_WHISPER_MODEL", "base"),
            whisper_model_path=os.environ.get("VIDEO_MCP_WHISPER_MODEL_PATH"),
            gemini_model=os.environ.get("VIDEO_MCP_GEMINI_MODEL", "gemini-2.5-flash"),
            disable_gemini=_bool(os.environ.get("VIDEO_MCP_DISABLE_GEMINI")),
            max_frames=_int(os.environ.get("VIDEO_MCP_MAX_FRAMES"), 60),
            min_frames=_int(os.environ.get("VIDEO_MCP_MIN_FRAMES"), 8),
            frame_max_px=_int(os.environ.get("VIDEO_MCP_FRAME_MAX_PX"), 1024),
            cache_dir=Path(cache_dir).expanduser()
            if cache_dir
            else Path.home() / ".cache" / "video-vision-mcp",
        )

    def select_backend(self, override: str | None = None) -> str:
        """Return the backend id to use. Tier 3 (Gemini) wins when usable.

        Precedence: Gemini (unless disabled) > OpenAI > Groq > local whisper.cpp.
        `override` lets a single tool call force a specific backend.
        """
        if override:
            return override
        if self.gemini_api_key and not self.disable_gemini:
            return "tier3-gemini"
        if self.openai_api_key:
            return "tier2-openai"
        if self.groq_api_key:
            return "tier2-groq"
        return "tier1-local"

    def available_backends(self) -> list[str]:
        backends = ["tier1-local"]
        if self.openai_api_key:
            backends.append("tier2-openai")
        if self.groq_api_key:
            backends.append("tier2-groq")
        if self.gemini_api_key:
            backends.append("tier3-gemini")
        return backends

    @staticmethod
    def is_cloud_backend(backend: str) -> bool:
        return backend != "tier1-local"
