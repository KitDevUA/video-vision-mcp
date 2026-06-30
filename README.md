# video-vision-mcp

An MCP server that gives Claude Code the ability to **analyze any video** —
a local file, a URL, or a Jira ticket attachment — through one set of tools.

Claude can't watch video natively (only text + the first frame of an image).
This server converts a video into **sampled frame images + an audio transcript**,
or — when a Gemini key is present — a **native Gemini analysis** of the whole
video. It works alongside [`mcp-atlassian`](https://github.com/sooperset/mcp-atlassian)
and shares its `.env`.

> Scenario: open a Jira ticket with a video bug report → one command
> (`analyze_video jira_issue_key=DEV-123`) → you see the frames and the
> transcript (or Gemini's analysis if a key is configured), without juggling
> two MCP servers.

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

- `analyze_video` — frames + transcript + metadata (the main tool).
- `get_video_transcript_only` — transcript text only.
- `extract_frames_at` — frames at specific timestamps (`"00:42"`, `"1:05"`, `12.5`).
- `list_recent_analyses` — cached analyses + backend used.
- `compare_backends` — same video via tier 1 and tier 3 side by side.

## Install

Requires **Python ≥ 3.10**. `ffmpeg` and `whisper.cpp` are **auto-installed on
first use** if missing (or you get a precise manual command — never a silent crash).

```bash
git clone <this-repo> video-vision-mcp
cd video-vision-mcp

# Recommended: uv (https://docs.astral.sh/uv/)
uv venv && source .venv/bin/activate
uv pip install -e .            # all backends bundled

# or plain pip
pip install -e .
```

All backend SDKs (OpenAI, Groq, Gemini, pywhispercpp) are bundled by default —
one install enables every tier. `ffmpeg` and `whisper.cpp` are the only external
pieces, auto-installed on first use.

### Per-OS dependency notes

`ffmpeg`/`ffprobe` auto-install path:

| OS | Auto-install via | Manual fallback |
|---|---|---|
| **macOS** | `brew install ffmpeg` | install [Homebrew](https://brew.sh) first |
| **Linux** | `apt-get` / `dnf` | `sudo apt-get install ffmpeg` |
| **Windows** | `winget` (`Gyan.FFmpeg`) / `choco` | `winget install Gyan.FFmpeg` |

`whisper.cpp` (tier 1 transcription) ships as the bundled `pywhispercpp` binding
(prebuilt wheels, no system build on common platforms). If no wheel is available
the server falls back to a `whisper-cli` binary, which on macOS it can install
via `brew install whisper-cpp` (Metal-accelerated).

The ggml model (`base` by default) is downloaded automatically from Hugging Face
into the cache on first transcription. Override with `VIDEO_MCP_WHISPER_MODEL`
(`tiny`/`base`/`small`/`medium`/`large-v3`) or `VIDEO_MCP_WHISPER_MODEL_PATH`.

If you only want cloud transcription, set `OPENAI_API_KEY` or `GROQ_API_KEY`
(tier 2) — or `GEMINI_API_KEY` (tier 3); whisper.cpp is then never invoked.

## Configure

```bash
cp env.example .env
# edit .env — nothing is required for tier 1
```

See `env.example` for every variable. The `.env` format matches `mcp-atlassian`,
so Jira creds (`JIRA_URL` / `JIRA_USERNAME` / `JIRA_API_TOKEN`) can be shared.

## Register in Claude Code

Add to your project `.mcp.json` (or global config), next to `mcp-atlassian` — see
`.mcp.json.example`. With `uv` installed:

```json
{
  "mcpServers": {
    "video-vision": {
      "command": "uvx",
      "args": ["--from", "/abs/path/to/video-vision-mcp", "video-vision-mcp"],
      "env": { "VIDEO_MCP_ENV": "/abs/path/to/video-vision-mcp/.env" }
    }
  }
}
```

Or, if installed into a venv, point `command` at that venv's `video-vision-mcp`
executable. Restart Claude Code; the `video-vision` tools then appear.

## Cache

Results are cached at `~/.cache/video-vision-mcp/` keyed by **(file hash,
backend)** — re-analyzing the same video is instant, and switching backends
keeps each result separately. Downloaded URLs/Jira files and whisper models live
under the same dir. Override with `VIDEO_MCP_CACHE_DIR`.

## How it fits with mcp-atlassian

`mcp-atlassian` can download a Jira attachment but can't analyze it. This server
takes over from there: pass `jira_issue_key` and it fetches the attachment over
Jira REST itself (same creds), so you stay in one tool call. If the Jira token is
missing/invalid you get a clear error pointing at `.env`, not a silent failure.
