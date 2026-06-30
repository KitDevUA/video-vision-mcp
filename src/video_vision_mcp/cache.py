"""Content-addressed cache keyed by (file hash, backend).

Layout: <cache_dir>/<backend>/<sha256>/{result.json, frames/000.jpg ...}
A flat index.json at the cache root powers `list_recent_analyses`.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .backends.base import AnalysisResult, Frame, TranscriptSegment


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


class Cache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"

    def _entry_dir(self, digest: str, backend: str) -> Path:
        return self.root / backend / digest

    def load(self, digest: str, backend: str) -> AnalysisResult | None:
        entry = self._entry_dir(digest, backend)
        result_json = entry / "result.json"
        if not result_json.is_file():
            return None
        data = json.loads(result_json.read_text(encoding="utf-8"))
        frames: list[Frame] = []
        for i, fr in enumerate(data.get("frames", [])):
            img = entry / "frames" / f"{i:03d}.jpg"
            if img.is_file():
                frames.append(Frame(timestamp=fr["timestamp"], image_bytes=img.read_bytes(), mime=fr["mime"]))
        segments = [TranscriptSegment(**s) for s in data.get("segments", [])]
        return AnalysisResult(
            source=data["source"],
            backend=data["backend"],
            duration=data.get("duration"),
            width=data.get("width"),
            height=data.get("height"),
            has_audio=data.get("has_audio", False),
            frames=frames,
            segments=segments,
            transcript_text=data.get("transcript_text", ""),
            gemini_summary=data.get("gemini_summary"),
            notes=data.get("notes", []),
        )

    def save(self, digest: str, result: AnalysisResult) -> None:
        entry = self._entry_dir(digest, result.backend)
        (entry / "frames").mkdir(parents=True, exist_ok=True)
        for i, fr in enumerate(result.frames):
            (entry / "frames" / f"{i:03d}.jpg").write_bytes(fr.image_bytes)
        (entry / "result.json").write_text(
            json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._record_index(digest, result)

    def _record_index(self, digest: str, result: AnalysisResult) -> None:
        index = self.read_index()
        index = [e for e in index if not (e["hash"] == digest and e["backend"] == result.backend)]
        index.append(
            {
                "hash": digest,
                "backend": result.backend,
                "source": result.source,
                "duration": result.duration,
                "has_speech": bool(result.transcript_text or result.segments),
                "frames": len(result.frames),
                "analyzed_at": time.time(),
            }
        )
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_index(self) -> list[dict]:
        if not self.index_path.is_file():
            return []
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
