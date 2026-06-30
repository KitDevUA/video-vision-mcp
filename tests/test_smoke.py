"""Offline smoke tests — no network, no ffmpeg required."""

from __future__ import annotations

import os

import pytest

from video_vision_mcp.config import Config
from video_vision_mcp.media import ffmpeg_tools
from video_vision_mcp.pipeline import parse_timestamp
from video_vision_mcp.sources.url_loader import UrlError, _assert_public_http


def test_backend_selection_precedence(monkeypatch, tmp_path):
    # Isolate from any real .env up the directory tree.
    monkeypatch.chdir(tmp_path)
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY",
                "VIDEO_MCP_DISABLE_GEMINI", "VIDEO_MCP_ENV"):
        monkeypatch.delenv(var, raising=False)

    base = Config.load()
    assert base.select_backend() == "tier1-local"

    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert Config.load().select_backend() == "tier2-groq"

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert Config.load().select_backend() == "tier2-openai"

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert Config.load().select_backend() == "tier3-gemini"

    monkeypatch.setenv("VIDEO_MCP_DISABLE_GEMINI", "true")
    assert Config.load().select_backend() == "tier2-openai"


def test_parse_timestamp():
    assert parse_timestamp("12") == 12.0
    assert parse_timestamp(12.5) == 12.5
    assert parse_timestamp("01:05") == 65.0
    assert parse_timestamp("1:01:05") == 3665.0


def test_adaptive_frame_count_clamps():
    assert ffmpeg_tools.adaptive_frame_count(None, 8, 60) == 8
    assert ffmpeg_tools.adaptive_frame_count(2.0, 8, 60) == 8       # short → min
    assert ffmpeg_tools.adaptive_frame_count(10_000, 8, 60) == 60   # long → max


def test_url_guard_blocks_non_public():
    with pytest.raises(UrlError):
        _assert_public_http("file:///etc/passwd")
    with pytest.raises(UrlError):
        _assert_public_http("http://localhost:6333/")
    with pytest.raises(UrlError):
        _assert_public_http("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(UrlError):
        _assert_public_http("http://127.0.0.1/")


def test_available_backends(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "VIDEO_MCP_ENV"):
        monkeypatch.delenv(var, raising=False)
    assert Config.load().available_backends() == ["tier1-local"]
