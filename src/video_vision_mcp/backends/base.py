"""Shared result types and MCP-content conversion for all backends."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field

from mcp.types import ImageContent, TextContent


def _fmt_ts(seconds: float) -> str:
    """Format seconds as MM:SS (or HH:MM:SS past an hour)."""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


@dataclass
class Frame:
    timestamp: float
    image_bytes: bytes
    mime: str = "image/jpeg"

    def to_image_content(self) -> ImageContent:
        return ImageContent(
            type="image",
            data=base64.b64encode(self.image_bytes).decode("ascii"),
            mimeType=self.mime,
        )


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str

    def to_line(self) -> str:
        return f"[{_fmt_ts(self.start)} - {_fmt_ts(self.end)}] {self.text.strip()}"


@dataclass
class AnalysisResult:
    """Everything one analysis produced, backend-agnostic."""

    source: str
    backend: str
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool = False
    frames: list[Frame] = field(default_factory=list)
    segments: list[TranscriptSegment] = field(default_factory=list)
    transcript_text: str = ""
    # Tier 3 returns a free-form analysis instead of (frames, transcript).
    gemini_summary: str | None = None
    notes: list[str] = field(default_factory=list)

    def metadata_block(self) -> str:
        res = f"{self.width}x{self.height}" if self.width and self.height else "unknown"
        dur = _fmt_ts(self.duration) if self.duration else "unknown"
        lines = [
            "## Video analysis",
            f"- **Source**: {self.source}",
            f"- **Backend**: {self.backend}",
            f"- **Duration**: {dur}",
            f"- **Resolution**: {res}",
            f"- **Speech detected**: {'yes' if self.has_audio and (self.transcript_text or self.segments) else 'no'}",
            f"- **Frames extracted**: {len(self.frames)}",
        ]
        for note in self.notes:
            lines.append(f"- _{note}_")
        return "\n".join(lines)

    def transcript_block(self) -> str:
        if self.segments:
            body = "\n".join(seg.to_line() for seg in self.segments)
            return f"## Transcript\n{body}"
        if self.transcript_text:
            return f"## Transcript\n{self.transcript_text}"
        return "## Transcript\n_(no speech / empty audio track)_"

    def to_mcp_content(self, include_frames: bool = True) -> list[TextContent | ImageContent]:
        """Build the ordered MCP content list: metadata → frames → transcript/summary."""
        out: list[TextContent | ImageContent] = [
            TextContent(type="text", text=self.metadata_block())
        ]
        if self.gemini_summary is not None:
            out.append(TextContent(type="text", text=f"## Gemini analysis\n{self.gemini_summary}"))
        if include_frames and self.frames:
            for fr in self.frames:
                out.append(TextContent(type="text", text=f"### Frame @ {_fmt_ts(fr.timestamp)}"))
                out.append(fr.to_image_content())
        if self.gemini_summary is None:
            out.append(TextContent(type="text", text=self.transcript_block()))
        return out

    # --- cache (de)serialization; frames are stored as files alongside the json ---

    def to_json_dict(self) -> dict:
        d = asdict(self)
        # Frame bytes are persisted separately; keep only timestamps + mime here.
        d["frames"] = [{"timestamp": f.timestamp, "mime": f.mime} for f in self.frames]
        return d
