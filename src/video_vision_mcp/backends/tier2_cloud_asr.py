"""Tier 2 — local ffmpeg frames + cloud ASR (OpenAI Whisper or Groq).

Frames are identical to tier 1; only the transcription step changes. Used when
an OpenAI or Groq key is present but Gemini is not (or is disabled).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from ..config import Config
from ..media import ffmpeg_tools
from ..media.installer import ensure_ffmpeg
from .base import AnalysisResult, TranscriptSegment
from .tier1_local import build_frames

# Both providers cap upload at 25 MB; re-encode to compact mp3 if the wav is larger.
_MAX_UPLOAD = 24 * 1024 * 1024


def _shrink_audio(wav: Path) -> Path:
    if wav.stat().st_size <= _MAX_UPLOAD:
        return wav
    ffmpeg, _ = ensure_ffmpeg()
    mp3 = wav.with_suffix(".mp3")
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(wav),
         "-ac", "1", "-ar", "16000", "-b:a", "32k", str(mp3)],
        capture_output=True, text=True, check=False,
    )
    return mp3 if mp3.is_file() and mp3.stat().st_size > 0 else wav


def _segments_from_verbose(verbose) -> list[TranscriptSegment]:
    segs = getattr(verbose, "segments", None) or []
    out: list[TranscriptSegment] = []
    for s in segs:
        start = getattr(s, "start", None)
        end = getattr(s, "end", None)
        text = getattr(s, "text", "")
        if start is None and isinstance(s, dict):
            start, end, text = s.get("start", 0), s.get("end", 0), s.get("text", "")
        out.append(TranscriptSegment(start=float(start or 0), end=float(end or 0), text=text))
    return out


def _transcribe_openai(audio: Path, cfg: Config) -> tuple[list[TranscriptSegment], str]:
    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key)
    with open(audio, "rb") as fh:
        resp = client.audio.transcriptions.create(
            model="whisper-1", file=fh, response_format="verbose_json"
        )
    return _segments_from_verbose(resp), getattr(resp, "text", "")


def _transcribe_groq(audio: Path, cfg: Config) -> tuple[list[TranscriptSegment], str]:
    from groq import Groq

    client = Groq(api_key=cfg.groq_api_key)
    with open(audio, "rb") as fh:
        resp = client.audio.transcriptions.create(
            model="whisper-large-v3", file=fh, response_format="verbose_json"
        )
    return _segments_from_verbose(resp), getattr(resp, "text", "")


def analyze(path: Path, source: str, cfg: Config, backend: str, frame_interval: float | None = None) -> AnalysisResult:
    provider = "openai" if backend == "tier2-openai" else "groq"
    interval = frame_interval if frame_interval and frame_interval > 0 else cfg.frame_interval_sec
    meta = ffmpeg_tools.probe(path)
    result = AnalysisResult(
        source=source,
        backend=backend,
        duration=meta["duration"],
        width=meta["width"],
        height=meta["height"],
        has_audio=meta["has_audio"],
    )
    result.frames = build_frames(path, meta, cfg, interval)
    label = "OpenAI Whisper API" if provider == "openai" else "Groq whisper-large-v3"
    result.notes.append(f"frame sampling: every {interval:g}s")
    result.notes.append(f"transcription: {label}")

    if not meta["has_audio"]:
        result.notes.append("no audio track — transcription skipped")
        return result

    with tempfile.TemporaryDirectory(prefix="vvmcp-aud-") as tmp:
        wav = ffmpeg_tools.extract_audio_wav(path, Path(tmp))
        if wav is None:
            result.notes.append("empty audio track — transcription skipped")
            return result
        audio = _shrink_audio(wav)
        if provider == "openai":
            result.segments, result.transcript_text = _transcribe_openai(audio, cfg)
        else:
            result.segments, result.transcript_text = _transcribe_groq(audio, cfg)
    if not result.transcript_text and result.segments:
        result.transcript_text = " ".join(s.text.strip() for s in result.segments).strip()
    return result
