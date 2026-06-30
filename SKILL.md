---
name: video-vision
description: Analyze any video (local file, URL, or Jira attachment) into frames + transcript via the video-vision MCP server. Use when the user references a video file, a video bug report, or a video attachment on a Jira ticket.
---

# Video Vision

Claude cannot watch video natively (only text + the first frame of an image).
The `video-vision` MCP server bridges that gap: it converts any video into
sampled frame images + an audio transcript (or a native Gemini analysis), and
returns them as MCP content.

## When to use it (proactively)

Offer `analyze_video` WITHOUT waiting to be explicitly asked, whenever:

- A Jira ticket has a video attachment (`.mp4`, `.mov`, `.webm`, screen recording).
- The user pastes a video URL (YouTube, Loom, direct link).
- The user mentions "the recording", "the screen capture", "watch this video".
- A bug report references reproduction steps shown in a video.

## Tools

| Tool | Use for |
|---|---|
| `analyze_video` | Full analysis: frames + transcript + metadata. The default. |
| `get_video_transcript_only` | Just the spoken text (fast, no images). |
| `extract_frames_at` | Frames at specific timestamps ("00:42", "1:05"). |
| `list_recent_analyses` | What's already cached, and with which backend. |
| `compare_backends` | Same video via local + Gemini side by side. |

## Inputs (pick exactly one)

- `file_path` — a local path (including a temp file produced by mcp-atlassian's
  `jira_download_attachments`).
- `url` — a direct or streaming URL.
- `jira_issue_key` (+ optional `attachment_id`) — the server fetches the
  attachment itself via Jira REST. **Do not** call `jira_download_attachments`
  first; pass the issue key directly.

## Backends (automatic)

Chosen from configured API keys, named in every result:
`Gemini (native)` > `OpenAI Whisper` > `Groq` > `local whisper.cpp`.
Tier 1 is fully local and always available. Cloud tiers print a one-time
privacy notice (video content is uploaded to a third party).
