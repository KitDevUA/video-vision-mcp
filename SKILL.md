---
name: video-vision
description: Analyze any video (local file or URL) into frames + transcript via the video-vision MCP server. Use when the user references a video file or video URL, or a video bug report.
---

# Video Vision

Claude cannot watch video natively (only text + the first frame of an image).
The `video-vision` MCP server bridges that gap: it converts a video into
sampled frame images + an audio transcript (or a native Gemini analysis), and
returns them as MCP content. It is standalone — it takes a ready video, it does
not fetch from Jira/Slack/etc.

## When to use it (proactively)

Offer `analyze_video` WITHOUT waiting to be explicitly asked, whenever:

- The user pastes a video URL (YouTube, Loom, direct link).
- The user mentions "the recording", "the screen capture", "watch this video".
- A bug report references reproduction steps shown in a video.
- A video attachment surfaces via another integration (e.g. a Jira ticket) — first
  fetch it with that integration (download to a file / get a direct URL), then
  pass the `file_path` or `url` here.

## Tools

| Tool | Use for |
|---|---|
| `analyze_video` | Full analysis: frames + transcript + metadata. The default. |
| `get_video_transcript_only` | Just the spoken text (fast, no images). |
| `extract_frames_at` | Frames at specific timestamps ("00:42", "1:05"). |
| `list_recent_analyses` | What's already cached, and with which backend. |
| `compare_backends` | Same video via local + Gemini side by side. |

## Inputs (pick exactly one)

- `file_path` — a local path to a video file (including a temp file another MCP
  downloaded).
- `url` — a direct or streaming URL. (An authenticated API URL won't work — download
  it to a file first.)

## Backends (automatic)

Chosen from configured API keys, named in every result:
`Gemini (native)` > `OpenAI Whisper` > `Groq` > `local whisper.cpp`.
Tier 1 is fully local and always available. Cloud tiers print a one-time
privacy notice (video content is uploaded to a third party).
