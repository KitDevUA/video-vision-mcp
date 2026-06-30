"""Cross-platform auto-installation of ffmpeg and whisper.cpp.

Strategy: detect the OS, try its native package manager, and on failure raise
`DependencyError` with a precise manual-install instruction instead of a bare
"command not found". Whisper model weights are downloaded from Hugging Face.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import urllib.request
from pathlib import Path

WHISPER_CLI_CANDIDATES = ("whisper-cli", "whisper-cpp", "main")
_HF_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin"


class DependencyError(RuntimeError):
    """A required external tool is missing and could not be auto-installed."""


def _run(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _has(binary: str) -> str | None:
    return shutil.which(binary)


def _system() -> str:
    return platform.system().lower()  # "darwin" | "linux" | "windows"


# --------------------------------------------------------------------------- ffmpeg


def _install_ffmpeg() -> None:
    sysname = _system()
    if sysname == "darwin":
        if _has("brew"):
            _run(["brew", "install", "ffmpeg"])
            return
        raise DependencyError(
            "ffmpeg not found and Homebrew is missing. Install Homebrew "
            "(https://brew.sh) then run: brew install ffmpeg"
        )
    if sysname == "linux":
        if _has("apt-get"):
            _run(["sudo", "apt-get", "update"])
            _run(["sudo", "apt-get", "install", "-y", "ffmpeg"])
            return
        if _has("dnf"):
            _run(["sudo", "dnf", "install", "-y", "ffmpeg"])
            return
        raise DependencyError(
            "ffmpeg not found. Install it with your package manager, e.g. "
            "`sudo apt-get install ffmpeg` or `sudo dnf install ffmpeg`."
        )
    if sysname == "windows":
        if _has("winget"):
            _run(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-source-agreements",
                  "--accept-package-agreements"])
            return
        if _has("choco"):
            _run(["choco", "install", "-y", "ffmpeg"])
            return
        raise DependencyError(
            "ffmpeg not found. Install winget or Chocolatey, then run "
            "`winget install Gyan.FFmpeg` or `choco install ffmpeg`."
        )
    raise DependencyError(f"Unsupported OS for auto-install: {sysname}")


def ensure_ffmpeg() -> tuple[str, str]:
    """Return (ffmpeg, ffprobe) paths, installing ffmpeg if absent."""
    if not (_has("ffmpeg") and _has("ffprobe")):
        _install_ffmpeg()
    ffmpeg, ffprobe = _has("ffmpeg"), _has("ffprobe")
    if not (ffmpeg and ffprobe):
        raise DependencyError(
            "ffmpeg/ffprobe still not on PATH after install attempt. "
            "Open a new shell or add the install location to PATH."
        )
    return ffmpeg, ffprobe


# ----------------------------------------------------------------------- whisper.cpp


def _install_whisper_cpp() -> None:
    sysname = _system()
    if sysname == "darwin" and _has("brew"):
        # Homebrew's formula installs the `whisper-cli` binary (Metal-enabled).
        _run(["brew", "install", "whisper-cpp"])
        return
    raise DependencyError(
        "whisper.cpp not found. Install options:\n"
        "  - pip install 'video-vision-mcp[whisper]'  (Python binding, no system build)\n"
        "  - macOS: brew install whisper-cpp\n"
        "  - source: https://github.com/ggerganov/whisper.cpp (build whisper-cli)\n"
        "Or add an OPENAI_API_KEY / GROQ_API_KEY to use cloud transcription instead."
    )


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
    """Ensure some whisper.cpp path is usable.

    Returns {"mode": "python"} when the pywhispercpp binding is importable,
    otherwise {"mode": "cli", "path": <whisper-cli>}. Raises DependencyError if
    neither is available after the install attempt.
    """
    if has_pywhispercpp():
        return {"mode": "python"}
    cli = find_whisper_cli()
    if cli:
        return {"mode": "cli", "path": cli}
    _install_whisper_cpp()
    cli = find_whisper_cli()
    if cli:
        return {"mode": "cli", "path": cli}
    if has_pywhispercpp():
        return {"mode": "python"}
    raise DependencyError("whisper.cpp unavailable after install attempt.")


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
