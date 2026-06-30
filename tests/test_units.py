"""Unit tests — offline, no ffmpeg / network / whisper / cloud SDKs required."""

from __future__ import annotations

import pytest

from video_vision_mcp.backends.base import (
    AnalysisResult,
    Frame,
    TranscriptSegment,
    _fmt_ts,
)
from video_vision_mcp.backends.tier1_local import _is_silence
from video_vision_mcp.cache import Cache, file_hash
from video_vision_mcp.config import Config
from video_vision_mcp.sources.jira_loader import (
    JiraConfigError,
    _client,
    _is_video_attachment,
)
from video_vision_mcp.sources.url_loader import _needs_yt_dlp
from video_vision_mcp import privacy


def test_fmt_ts():
    assert _fmt_ts(5) == "00:05"
    assert _fmt_ts(65) == "01:05"
    assert _fmt_ts(3665) == "01:01:05"


def test_is_silence():
    assert _is_silence("[BLANK_AUDIO]")
    assert _is_silence("  [ Silence ] ")
    assert _is_silence("")
    assert not _is_silence("hello world")


def test_file_hash_is_deterministic(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello world")
    assert file_hash(f) == file_hash(f)
    g = tmp_path / "b.bin"
    g.write_bytes(b"hello world!")
    assert file_hash(f) != file_hash(g)


def test_cache_round_trip_and_backend_isolation(tmp_path):
    cache = Cache(tmp_path)
    result = AnalysisResult(
        source="file:x.mp4", backend="tier1-local", duration=10.0,
        width=100, height=50, has_audio=True,
    )
    result.frames = [Frame(0.0, b"\xff\xd8jpeg-a"), Frame(1.0, b"\xff\xd8jpeg-b")]
    result.segments = [TranscriptSegment(0.0, 1.0, "hi there")]
    result.transcript_text = "hi there"

    cache.save("deadbeef", result)
    loaded = cache.load("deadbeef", "tier1-local")

    assert loaded is not None
    assert (loaded.duration, loaded.width, loaded.height) == (10.0, 100, 50)
    assert len(loaded.frames) == 2
    assert loaded.frames[0].image_bytes == b"\xff\xd8jpeg-a"
    assert loaded.segments[0].text == "hi there"

    index = cache.read_index()
    assert index and index[0]["backend"] == "tier1-local" and index[0]["has_speech"]

    # Same hash, different backend → cached separately (must miss).
    assert cache.load("deadbeef", "tier3-gemini") is None


def test_to_mcp_content_layout():
    result = AnalysisResult(source="s", backend="tier1-local", duration=2, width=10, height=10, has_audio=True)
    result.frames = [Frame(0.0, b"x")]
    result.segments = [TranscriptSegment(0.0, 1.0, "hello")]
    result.transcript_text = "hello"

    content = result.to_mcp_content()
    types = [c.type for c in content]
    assert types[0] == "text"          # metadata block first
    assert "image" in types            # frame image present
    assert types[-1] == "text"         # transcript last


def test_to_mcp_content_gemini_has_no_frames_block():
    result = AnalysisResult(source="s", backend="tier3-gemini")
    result.gemini_summary = "## Summary\nstuff at 00:12"
    content = result.to_mcp_content()
    assert all(c.type == "text" for c in content)
    assert any("Gemini analysis" in c.text for c in content if c.type == "text")


def test_privacy_warn_once():
    privacy.reset()
    assert privacy.warn_once("tier1-local") is None
    first = privacy.warn_once("tier3-gemini")
    assert first and "Gemini" in first
    assert privacy.warn_once("tier3-gemini") is None  # only once per process
    privacy.reset()
    assert privacy.warn_once("tier3-gemini") is not None


def test_gemini_alias_and_disable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY",
                "VIDEO_MCP_DISABLE_GEMINI", "VIDEO_MCP_ENV"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "x")  # alias for GEMINI_API_KEY
    cfg = Config.load()
    assert cfg.gemini_api_key == "x"
    assert cfg.select_backend() == "tier3-gemini"
    assert "tier3-gemini" in cfg.available_backends()


def test_is_video_attachment():
    assert _is_video_attachment({"mimeType": "video/mp4", "filename": "a.mp4"})
    assert _is_video_attachment({"mimeType": "application/octet-stream", "filename": "clip.MOV"})
    assert not _is_video_attachment({"mimeType": "image/png", "filename": "a.png"})


def test_jira_requires_creds(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for var in ("JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "VIDEO_MCP_ENV"):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.load()
    with pytest.raises(JiraConfigError):
        _client(cfg)


def test_needs_yt_dlp():
    assert _needs_yt_dlp("https://youtube.com/watch?v=x")
    assert _needs_yt_dlp("https://www.youtu.be/x")
    assert _needs_yt_dlp("https://loom.com/share/abc")
    assert not _needs_yt_dlp("https://example.com/a.mp4")
