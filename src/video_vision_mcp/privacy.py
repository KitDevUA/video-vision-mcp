"""One-shot privacy notice for cloud backends, once per server process.

Tier 1 is fully local. The first time a cloud backend (OpenAI/Groq/Gemini) is
used in this process, `warn_once` returns a notice to surface in the result. A
stdio MCP server runs one process per Claude session, so this is effectively
per-session. It never blocks — the user opted in by supplying the key.
"""

from __future__ import annotations

_warned: set[str] = set()

_SERVICE_LABELS = {
    "tier2-openai": "OpenAI (Whisper API)",
    "tier2-groq": "Groq (whisper-large-v3)",
    "tier3-gemini": "Google Gemini (Files API)",
}


def warn_once(backend: str) -> str | None:
    if backend == "tier1-local" or backend in _warned:
        return None
    _warned.add(backend)
    label = _SERVICE_LABELS.get(backend, backend)
    return (
        f"PRIVACY: this video's content is being uploaded to {label}. "
        "Tier 1 (local) avoids any upload. Set VIDEO_MCP_DISABLE_GEMINI=true or "
        "remove the API key to stay local."
    )


def reset() -> None:
    _warned.clear()
