"""ffmpeg / whisper.cpp resolution — never installs anything globally.

ffmpeg: system binary if on PATH, else bundled static-ffmpeg (fetched once to a
local cache). whisper.cpp = bundled pywhispercpp. No brew/apt/winget, no sudo.
Whisper model weights are downloaded from Hugging Face into the cache.
"""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

WHISPER_CLI_CANDIDATES = ("whisper-cli", "whisper-cpp", "main")
_HF_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin"


class DependencyError(RuntimeError):
    """A required external tool is missing and no usable fallback was found."""


def _has(binary: str) -> str | None:
    return shutil.which(binary)


# --------------------------------------------------------------------------- ffmpeg


def _bundled_ffmpeg() -> tuple[str, str]:
    """Resolve ffmpeg+ffprobe from the bundled static-ffmpeg package.

    Fetches the platform binaries once into static-ffmpeg's own cache — not a
    global/system install.
    """
    try:
        from static_ffmpeg import run
    except ImportError as exc:
        raise DependencyError(
            "ffmpeg/ffprobe not on PATH and the bundled fallback (static-ffmpeg) "
            "is missing. Install ffmpeg, or reinstall this package."
        ) from exc
    return run.get_or_fetch_platform_executables_else_raise()


def ensure_ffmpeg() -> tuple[str, str]:
    """Return (ffmpeg, ffprobe). System binaries first, else bundled fallback.

    Never installs anything globally on the user's machine.
    """
    ffmpeg, ffprobe = _has("ffmpeg"), _has("ffprobe")
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe
    return _bundled_ffmpeg()


# ----------------------------------------------------------------------- whisper.cpp


def find_whisper_cli() -> str | None:
    for candidate in WHISPER_CLI_CANDIDATES:
        path = _has(candidate)
        if path:
            return path
    return None


def has_pywhispercpp() -> bool:
    try:
        import pywhispercpp.model  # noqa: F401

        return True
    except Exception:
        return False


def ensure_whisper() -> dict:
    """Return how to run whisper.cpp. Never installs anything globally.

    {"mode": "python"} if the bundled pywhispercpp binding is importable, else
    {"mode": "cli", "path": ...} if a whisper-cli is already on PATH.
    """
    if has_pywhispercpp():
        return {"mode": "python"}
    cli = find_whisper_cli()
    if cli:
        return {"mode": "cli", "path": cli}
    raise DependencyError(
        "whisper.cpp unavailable. pywhispercpp ships with this package — "
        "reinstall it, put a whisper-cli on PATH, or set OPENAI_API_KEY / "
        "GROQ_API_KEY for cloud transcription."
    )


def ensure_whisper_model(model: str, explicit_path: str | None, cache_dir: Path) -> Path:
    """Return a local ggml model path, downloading from Hugging Face if needed.

    Only used by the subprocess (CLI) path; pywhispercpp manages its own models.
    """
    if explicit_path:
        p = Path(explicit_path).expanduser()
        if not p.is_file():
            raise DependencyError(f"Whisper model not found at VIDEO_MCP_WHISPER_MODEL_PATH: {p}")
        return p
    models_dir = cache_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    target = models_dir / f"ggml-{model}.bin"
    if target.is_file():
        return target
    url = _HF_MODEL_URL.format(model=model)
    tmp = target.with_suffix(".bin.part")
    urllib.request.urlretrieve(url, tmp)  # noqa: S310 - fixed trusted HF host
    os.replace(tmp, target)
    return target
