"""video-vision-mcp — FastMCP server exposing video analysis tools to Claude.

Backend selection is automatic (see config.select_backend): Gemini > OpenAI >
Groq > local whisper.cpp, based on which keys are present in the .env.
"""

from __future__ import annotations

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

from .backends.base import _fmt_ts
from .cache import Cache
from .config import Config
from . import pipeline

INSTRUCTIONS = """\
Analyze a video (local file or URL) as frames + transcript. Standalone: it takes
a ready video, it does not fetch from Jira/Slack/etc.

PROACTIVE USE: whenever the user references a video file or video URL, offer
`analyze_video` without waiting to be explicitly asked to "analyze the video".
If the video lives behind an integration (e.g. a Jira attachment), first obtain
it via that integration — download it to a local file or get a direct URL — then
pass the resulting file_path or url here.

Inputs are mutually exclusive: pass exactly one of file_path / url. Use
`frame_interval` (seconds between frames, default 1.0) to control frame density
when the user wants finer or coarser sampling.
"""

cfg = Config.load()
cache = Cache(cfg.cache_dir)
mcp = FastMCP("video-vision-mcp", instructions=INSTRUCTIONS)


@mcp.tool()
def analyze_video(
    file_path: str | None = None,
    url: str | None = None,
    frame_interval: float | None = None,
    force_refresh: bool = False,
) -> list[TextContent | ImageContent]:
    """Analyze a video into frames + transcript + metadata.

    Provide exactly ONE source:
      - file_path: local path to a video file (already on disk).
      - url: direct/streaming URL (yt-dlp for known sites, HTTP otherwise).

    frame_interval: seconds between sampled frames (default 1.0 = one per second).
    Denser sampling: 0.5 / 0.25 / 0.1; sparser: 2 / 5; or any custom value. The
    total is capped by the frame budget so long/dense videos can't flood context.
    Ignored by the native Gemini backend (it ingests the whole video).

    The backend (local whisper.cpp / OpenAI / Groq / native Gemini) is chosen
    automatically from configured keys and named in the result metadata. Results
    are cached per (file-hash, backend, frame_interval); pass force_refresh=true
    to recompute.
    """
    result = pipeline.analyze(
        cfg, cache, file_path=file_path, url=url,
        frame_interval=frame_interval, force_refresh=force_refresh,
    )
    return result.to_mcp_content(include_frames=True)


@mcp.tool()
def get_video_transcript_only(
    file_path: str | None = None,
    url: str | None = None,
    force_refresh: bool = False,
) -> str:
    """Fast path: return only the transcript text (no frame images).

    Same inputs and backend selection as analyze_video. With the Gemini backend,
    returns Gemini's analysis text instead of a plain transcript.
    """
    result = pipeline.analyze(
        cfg, cache, file_path=file_path, url=url, force_refresh=force_refresh,
    )
    if result.gemini_summary is not None:
        return f"{result.metadata_block()}\n\n## Gemini analysis\n{result.gemini_summary}"
    return f"{result.metadata_block()}\n\n{result.transcript_block()}"


@mcp.tool()
def extract_frames_at(
    timestamps: list[str],
    file_path: str | None = None,
    url: str | None = None,
) -> list[TextContent | ImageContent]:
    """Extract frames at specific timestamps.

    timestamps accepts seconds ("12", "12.5") or "MM:SS" / "HH:MM:SS".
    Tier 1/2 return real frame images; with the Gemini backend you get a textual
    description of those moments instead (no local frame cutting).
    """
    seconds = [pipeline.parse_timestamp(t) for t in timestamps]
    resolved, frames, gemini_text = pipeline.frames_at(
        cfg, timestamps=seconds, file_path=file_path, url=url,
    )
    if gemini_text is not None:
        return [TextContent(type="text", text=f"## Frames @ {', '.join(timestamps)} (Gemini)\n{gemini_text}")]
    out: list[TextContent | ImageContent] = [
        TextContent(type="text", text=f"## Frames from {resolved.label}")
    ]
    for fr in frames:
        out.append(TextContent(type="text", text=f"### Frame @ {_fmt_ts(fr.timestamp)}"))
        out.append(fr.to_image_content())
    return out


@mcp.tool()
def list_recent_analyses() -> str:
    """List previously analyzed videos from the cache, with the backend used for each."""
    index = sorted(cache.read_index(), key=lambda e: e.get("analyzed_at", 0), reverse=True)
    if not index:
        return "No analyses cached yet."
    lines = ["## Recent analyses", "", "| When (UTC) | Backend | Interval | Source | Duration | Speech | Frames |", "|---|---|---|---|---|---|---|"]
    for e in index:
        when = datetime.fromtimestamp(e.get("analyzed_at", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        dur = _fmt_ts(e["duration"]) if e.get("duration") else "—"
        variant = e.get("variant", "")
        interval = f"{variant[1:]}s" if variant.startswith("i") else "—"
        lines.append(
            f"| {when} | {e['backend']} | {interval} | {e['source']} | {dur} | "
            f"{'yes' if e.get('has_speech') else 'no'} | {e.get('frames', 0)} |"
        )
    return "\n".join(lines)


@mcp.tool()
def compare_backends(
    file_path: str | None = None,
    url: str | None = None,
    frame_interval: float | None = None,
) -> list[TextContent | ImageContent]:
    """Run the same video through tier 1 (local) and tier 3 (Gemini) side by side.

    frame_interval (seconds between frames) applies to the tier-1 half. Requires a
    Gemini key for the tier-3 half; otherwise reports that tier 3 is unavailable
    and returns only the local result.
    """
    available = cfg.available_backends()
    out: list[TextContent | ImageContent] = [
        TextContent(type="text", text="# Backend comparison\n\n---\n## Tier 1 — local (ffmpeg + whisper.cpp)")
    ]
    local = pipeline.analyze(
        cfg, cache, file_path=file_path, url=url,
        backend_override="tier1-local", frame_interval=frame_interval,
    )
    out.extend(local.to_mcp_content(include_frames=True))

    out.append(TextContent(type="text", text="\n---\n## Tier 3 — native Gemini"))
    if "tier3-gemini" not in available:
        out.append(TextContent(type="text", text="_Gemini backend unavailable (no GEMINI_API_KEY). Skipped._"))
        return out
    gemini = pipeline.analyze(
        cfg, cache, file_path=file_path, url=url, backend_override="tier3-gemini",
    )
    out.extend(gemini.to_mcp_content(include_frames=True))
    return out


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
