"""Tier 3 — native Gemini video understanding (default when a Gemini key is set).

Gemini ingests the visual + audio stream in one call: no local frame cutting,
no whisper. Small videos go inline; larger ones via the Files API.

Documented constraints (verify against https://ai.google.dev/gemini-api/docs/files
and .../video-understanding as they change):
  - inline total request size cap ~20 MB → above that use the Files API
  - Files API: 2 GB per file, 20 GB per project, files auto-delete after 48h
  - formats: mp4, mpeg, mov, avi, x-flv, mpg, webm, wmv, 3gpp
"""

from __future__ import annotations

import mimetypes
import time
from pathlib import Path

from ..config import Config
from .base import AnalysisResult

# Inline only for clearly-small files; everything else uploads via Files API.
_INLINE_MAX = 18 * 1024 * 1024
_UPLOAD_POLL_TIMEOUT = 300  # seconds

_PROMPT = (
    "Analyze this video in detail. Respond in Markdown with these sections:\n"
    "1. **Summary** — what happens overall.\n"
    "2. **Timeline** — bullet list of key moments, each prefixed with an MM:SS "
    "timestamp so I can navigate to it.\n"
    "3. **Transcript** — spoken words with MM:SS timestamps; write '(no speech)' "
    "if there is no audible speech.\n"
    "4. **Visual details** — on-screen text, UI elements, errors, or anything "
    "relevant to debugging if this looks like a bug report."
)


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime if (mime and mime.startswith("video/")) else "video/mp4"


def _state_name(file_obj) -> str:
    state = getattr(file_obj, "state", None)
    return getattr(state, "name", str(state)) if state is not None else "UNKNOWN"


def build_contents(client, path: Path, prompt: str) -> tuple[list, str]:
    """Return (contents, upload_mode) for a generate_content call.

    Small files go inline; larger ones upload via the Files API and wait for the
    file to leave PROCESSING before it is referenced.
    """
    from google.genai import types

    if path.stat().st_size <= _INLINE_MAX:
        part = types.Part.from_bytes(data=path.read_bytes(), mime_type=_guess_mime(path))
        return [part, prompt], "inline"

    uploaded = client.files.upload(file=str(path))
    deadline = time.time() + _UPLOAD_POLL_TIMEOUT
    while _state_name(uploaded) == "PROCESSING" and time.time() < deadline:
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    if _state_name(uploaded) == "FAILED":
        raise RuntimeError("Gemini Files API reported FAILED while processing the video.")
    if _state_name(uploaded) == "PROCESSING":
        raise RuntimeError(f"Gemini file still PROCESSING after {_UPLOAD_POLL_TIMEOUT}s.")
    return [uploaded, prompt], "Files API (auto-deletes after ~48h)"


def analyze(path: Path, source: str, cfg: Config) -> AnalysisResult:
    from google import genai

    client = genai.Client(api_key=cfg.gemini_api_key)
    contents, upload_mode = build_contents(client, path, _PROMPT)
    notes = [f"analysis: native Gemini ({cfg.gemini_model})", f"upload mode: {upload_mode}"]

    response = client.models.generate_content(model=cfg.gemini_model, contents=contents)

    result = AnalysisResult(source=source, backend="tier3-gemini", notes=notes)
    result.gemini_summary = getattr(response, "text", "") or "(empty Gemini response)"
    return result
