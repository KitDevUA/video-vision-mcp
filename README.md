# video-vision-mcp

[![CI](https://github.com/KitDevUA/video-vision-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/KitDevUA/video-vision-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/video-vision-mcp)](https://pypi.org/project/video-vision-mcp/)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<!-- mcp-name: io.github.KitDevUA/video-vision-mcp -->

An MCP server that gives Claude Code the ability to **analyze any video** —
a local file or a URL — through one set of tools.

Claude can't watch video natively (only text + the first frame of an image).
This server converts a video into **sampled frame images + an audio transcript**,
or — when a Gemini key is present — a **native Gemini analysis** of the whole video.

It is **standalone**: give it a ready video (a local path or a direct URL) and it
does the rest. It does not connect to Jira/Slack/etc. If a video lives behind an
integration, fetch it with that integration first (download to a file or get a
direct URL), then hand the `file_path` or `url` to this server.

> Scenario: a Jira bug ticket has only a screen-recording, no text. Your Jira MCP
> downloads the attachment to a temp file → `analyze_video file_path=/tmp/bug.mp4`
> → you see the frames + transcript (or Gemini's analysis) and can reason about the bug.

## Three backend tiers (auto-selected)

| Tier | Needs | What it does |
|---|---|---|
| **1 — local** (default) | nothing | `ffmpeg` frames + `whisper.cpp` transcript. Free, fully local, always works. |
| **2 — cloud ASR** | `OPENAI_API_KEY` or `GROQ_API_KEY` | Local frames, but transcription via OpenAI Whisper / Groq for higher quality. |
| **3 — native Gemini** | `GEMINI_API_KEY` | Gemini ingests the whole video (visual + audio) in one call, with MM:SS timestamps. Default when the key is set. |

Precedence: **Gemini > OpenAI > Groq > local.** Set `VIDEO_MCP_DISABLE_GEMINI=true`
to force tiers 1/2 even with a Gemini key. The backend used is named in every result.

**Privacy:** tier 1 never uploads anything. Tiers 2/3 print a one-time notice in
the session the first time video content is sent to a third party.

## Tools

- `analyze_video` — frames + transcript + metadata (the main tool). `frame_interval`
  sets seconds between frames (default 1.0; e.g. 0.5/0.25/0.1 denser, 2/5 sparser).
- `get_video_transcript_only` — transcript text only.
- `extract_frames_at` — frames at specific timestamps (`"00:42"`, `"1:05"`, `12.5`).
- `list_recent_analyses` — cached analyses + backend used.

## Install

Requires **Python ≥ 3.10**. A single install pulls everything — backends, plus the
ffmpeg and whisper.cpp dependencies. **Nothing is ever installed globally on your
machine** (no brew/apt/winget, no sudo).

### Use it (recommended)

With [uv](https://docs.astral.sh/uv/) you don't install it explicitly — `uvx` runs
the published package on demand (see [Register in Claude Code](#register-in-claude-code)).
To install into an environment instead:

```bash
uv pip install video-vision-mcp     # or: pip install video-vision-mcp
```

### From source (development)

```bash
git clone https://github.com/KitDevUA/video-vision-mcp.git
cd video-vision-mcp
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"          # all backends bundled
```

### Dependencies — fully self-contained

- **ffmpeg / ffprobe**: if they are already on your `PATH`, those system binaries
  are used. Otherwise the bundled `static-ffmpeg` package supplies them (fetched
  once into its own local cache — never a system-wide install).
- **whisper.cpp** (tier 1 transcription): shipped as the bundled `pywhispercpp`
  binding (prebuilt wheels; builds from source only if no wheel exists for your
  platform/Python). A `whisper-cli` already on `PATH` is used if present.
- **whisper model**: the ggml model (`base` by default) downloads from Hugging
  Face into the cache on first transcription. Override with
  `VIDEO_MCP_WHISPER_MODEL` (`tiny`/`base`/`small`/`medium`/`large-v3`) or
  `VIDEO_MCP_WHISPER_MODEL_PATH`.
- **cloud-only**: set `OPENAI_API_KEY` / `GROQ_API_KEY` (tier 2) or
  `GEMINI_API_KEY` (tier 3); whisper.cpp is then never invoked.

## Configure

```bash
cp env.example .env
# edit .env — nothing is required for tier 1
```

See `env.example` for every variable — all optional (API keys and tuning). Tier 1
needs none.

## Register in Claude Code

Add to your project `.mcp.json` (or global config) — see `.mcp.json.example`:

```json
{
  "mcpServers": {
    "video-vision": {
      "command": "uvx",
      "args": ["video-vision-mcp"],
      "env": { "VIDEO_MCP_ENV": "/abs/path/to/.env" }
    }
  }
}
```

`uvx` downloads and runs the published package automatically — no manual install
step. `VIDEO_MCP_ENV` is optional (tier 1 needs no keys); point it at your `.env`
if you use the cloud backends. For local development against a checkout, use
`"args": ["--from", "/abs/path/to/video-vision-mcp", "video-vision-mcp"]` instead.
Restart Claude Code; the `video-vision` tools then appear.

## Cache

Results are cached at `~/.cache/video-vision-mcp/` keyed by **(file hash,
backend, frame interval)** — re-analyzing the same video is instant, and
switching backends or intervals keeps each result separately. Downloaded URLs and
whisper models live under the same dir. Override with `VIDEO_MCP_CACHE_DIR`.

Cached analyses and downloaded videos older than `VIDEO_MCP_CACHE_TTL_HOURS`
(default **24**) are pruned on startup and skipped on read; set `0` to keep them
forever. Whisper models are never pruned (expensive to re-download).

## Using it with an integration (e.g. Jira, Slack)

This server is deliberately standalone — it never talks to Jira, Slack, or any
other service. When a video lives behind an integration, let that integration's
MCP fetch it, then pass the result here:

1. The integration MCP downloads the attachment to a local file (or gives a
   direct, publicly reachable URL — an authenticated API URL won't work with `url`).
2. Call `analyze_video file_path=<downloaded file>` (or `url=<direct link>`).

This keeps auth and service-specific logic where it belongs, and lets one video
tool serve every source.
