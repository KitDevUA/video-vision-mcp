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


def test_frame_count_for_interval():
    assert ffmpeg_tools.frame_count_for_interval(None, 1.0, 60) == 1
    assert ffmpeg_tools.frame_count_for_interval(9.0, 1.0, 60) == 9      # once per second
    assert ffmpeg_tools.frame_count_for_interval(9.0, 0.5, 60) == 18     # twice per second
    assert ffmpeg_tools.frame_count_for_interval(9.0, 5.0, 60) == 2      # sparse honored (no min floor)
    assert ffmpeg_tools.frame_count_for_interval(1000.0, 0.1, 60) == 60  # capped by max_frames


def test_frame_interval_config_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIDEO_MCP_FRAME_INTERVAL_SEC", raising=False)
    monkeypatch.delenv("VIDEO_MCP_ENV", raising=False)
    assert Config.load().frame_interval_sec == 1.0
    monkeypatch.setenv("VIDEO_MCP_FRAME_INTERVAL_SEC", "0.25")
    assert Config.load().frame_interval_sec == 0.25


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
