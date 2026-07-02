"""Tier 1 — fully local: ffmpeg frames + whisper.cpp transcription. Always works."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from ..config import Config
from ..media import ffmpeg_tools
from ..media.installer import (
    ensure_whisper,
    ensure_whisper_model,
    has_pywhispercpp,
)
from .base import AnalysisResult, Frame, TranscriptSegment


def build_frames(path: Path, meta: dict, cfg: Config, interval: float) -> list[Frame]:
    """Extract frames every `interval` seconds (shared by tier 1 and tier 2)."""
    count = ffmpeg_tools.frame_count_for_interval(meta["duration"], interval, cfg.max_frames)
    raw = ffmpeg_tools.extract_frames(path, count, cfg.frame_max_px, meta["duration"])
    return [Frame(timestamp=ts, image_bytes=img) for ts, img in raw]


def _transcribe_pywhispercpp(wav: Path, cfg: Config) -> list[TranscriptSegment]:
    from pywhispercpp.model import Model

    model = Model(cfg.whisper_model)
    segments = model.transcribe(str(wav))
    out: list[TranscriptSegment] = []
    for seg in segments:
        # pywhispercpp reports t0/t1 in centiseconds (1/100 s).
        out.append(TranscriptSegment(start=seg.t0 / 100.0, end=seg.t1 / 100.0, text=seg.text))
    return out


def _transcribe_cli(wav: Path, cli_path: str, cfg: Config) -> list[TranscriptSegment]:
    model_path = ensure_whisper_model(cfg.whisper_model, cfg.whisper_model_path, cfg.cache_dir)
    with tempfile.TemporaryDirectory(prefix="vvmcp-asr-") as tmp:
        prefix = str(Path(tmp) / "out")
        proc = subprocess.run(
            [cli_path, "-m", str(model_path), "-f", str(wav), "-oj", "-of", prefix],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"whisper-cli failed: {proc.stderr.strip()}")
        data = json.loads(Path(prefix + ".json").read_text(encoding="utf-8"))
    out: list[TranscriptSegment] = []
    for item in data.get("transcription", []):
        off = item.get("offsets", {})
        out.append(
            TranscriptSegment(
                start=off.get("from", 0) / 1000.0,
                end=off.get("to", 0) / 1000.0,
                text=item.get("text", ""),
            )
        )
    return out


# whisper.cpp emits these markers for non-speech audio; they are not a transcript.
_SILENCE_MARKERS = {"[blank_audio]", "[silence]", "(silence)", "[ silence ]", "[music]", "[ music ]"}


def _is_silence(text: str) -> bool:
    return text.strip().lower() in _SILENCE_MARKERS or not text.strip()


def transcribe(wav: Path, cfg: Config) -> list[TranscriptSegment]:
    runtime = ensure_whisper()
    if runtime["mode"] == "python" and has_pywhispercpp():
        segments = _transcribe_pywhispercpp(wav, cfg)
    else:
        segments = _transcribe_cli(wav, runtime["path"], cfg)
    return [s for s in segments if not _is_silence(s.text)]


def analyze(path: Path, source: str, cfg: Config, frame_interval: float | None = None) -> AnalysisResult:
    interval = frame_interval if frame_interval and frame_interval > 0 else cfg.frame_interval_sec
    meta = ffmpeg_tools.probe(path)
    result = AnalysisResult(
        source=source,
        backend="tier1-local",
        duration=meta["duration"],
        width=meta["width"],
        height=meta["height"],
        has_audio=meta["has_audio"],
    )
    result.frames = build_frames(path, meta, cfg, interval)
    result.notes.append(f"frame sampling: every {interval:g}s")
    result.notes.append("transcription: whisper.cpp (local)")

    if not meta["has_audio"]:
        result.notes.append("no audio track — transcription skipped")
        return result

    with tempfile.TemporaryDirectory(prefix="vvmcp-aud-") as tmp:
        wav = ffmpeg_tools.extract_audio_wav(path, Path(tmp))
        if wav is None:
            result.notes.append("empty audio track — transcription skipped")
            return result
        result.segments = transcribe(wav, cfg)
    result.transcript_text = " ".join(s.text.strip() for s in result.segments).strip()
    if not result.transcript_text:
        result.notes.append("audio track present but no speech detected")
    return result
