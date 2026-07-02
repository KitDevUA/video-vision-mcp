"""Orchestration: resolve source → hash → cache lookup → backend → cache save.

Keeps the tool layer (server.py) thin; all caching and backend dispatch lives here.
"""

from __future__ import annotations

from pathlib import Path

from . import privacy
from .backends import tier1_local, tier2_cloud_asr, tier3_gemini
from .backends.base import AnalysisResult, Frame
from .cache import Cache, file_hash
from .config import Config
from .media import ffmpeg_tools
from .sources import resolver
from .sources.resolver import ResolvedSource


def parse_timestamp(value: str | float | int) -> float:
    """Accept seconds (number/str) or 'MM:SS' / 'HH:MM:SS' and return seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        seconds = 0.0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds
    return float(text)


def _dispatch(backend: str, path: Path, source: str, cfg: Config, frame_interval: float | None) -> AnalysisResult:
    if backend == "tier3-gemini":
        return tier3_gemini.analyze(path, source, cfg)  # native — no local frame sampling
    if backend in ("tier2-openai", "tier2-groq"):
        return tier2_cloud_asr.analyze(path, source, cfg, backend, frame_interval)
    return tier1_local.analyze(path, source, cfg, frame_interval)


def analyze(
    cfg: Config,
    cache: Cache,
    *,
    file_path: str | None = None,
    url: str | None = None,
    frame_interval: float | None = None,
    force_refresh: bool = False,
) -> AnalysisResult:
    resolved = resolver.resolve(cfg, file_path, url)
    backend = cfg.select_backend()
    digest = file_hash(resolved.path)

    # Frame interval changes the sampled frames, so it must be part of the cache
    # key (tier 3 has no local frames, so its cache is interval-independent).
    effective = frame_interval if frame_interval and frame_interval > 0 else cfg.frame_interval_sec
    variant = "" if backend == "tier3-gemini" else f"i{effective:g}"

    if not force_refresh:
        cached = cache.load(digest, backend, variant)
        if cached is not None:
            cached.notes.append("served from cache")
            return cached

    warning = privacy.warn_once(backend)
    result = _dispatch(backend, resolved.path, resolved.label, cfg, frame_interval)
    if warning:
        result.notes.insert(0, warning)
    cache.save(digest, result, variant)
    return result


def frames_at(
    cfg: Config,
    *,
    timestamps: list[float],
    file_path: str | None = None,
    url: str | None = None,
) -> tuple[ResolvedSource, list[Frame], str | None]:
    """Extract frames at specific timestamps.

    Tier 1/2: real ffmpeg frames. Tier 3 (no local ffmpeg path): returns a Gemini
    description of those moments instead, as the third tuple element.
    """
    resolved = resolver.resolve(cfg, file_path, url)
    backend = cfg.select_backend()
    if backend == "tier3-gemini":
        from google import genai

        from .backends import tier3_gemini as t3

        client = genai.Client(api_key=cfg.gemini_api_key)
        marks = ", ".join(f"{int(t//60):02d}:{int(t%60):02d}" for t in timestamps)
        prompt = f"Describe in detail exactly what is shown at these timestamps: {marks}."
        contents, _ = t3.build_contents(client, resolved.path, prompt)
        resp = client.models.generate_content(model=cfg.gemini_model, contents=contents)
        return resolved, [], getattr(resp, "text", "")

    raw = ffmpeg_tools.extract_frames_at(resolved.path, timestamps, cfg.frame_max_px)
    return resolved, [Frame(timestamp=ts, image_bytes=img) for ts, img in raw], None
