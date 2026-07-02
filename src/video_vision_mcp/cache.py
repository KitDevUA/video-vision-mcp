"""Content-addressed cache keyed by (file hash, backend, frame interval).

Layout: <cache_dir>/<backend[__variant]>/<sha256>/{result.json, frames/000.jpg ...}
A flat index.json at the cache root powers `list_recent_analyses`. Entries older
than the TTL are pruned on startup and skipped on read; downloaded videos are
pruned too, but whisper models are kept (expensive to re-fetch).
"""

from __future__ import annotations

import hashlib
import json
import shutil
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
    def __init__(self, root: Path, ttl_seconds: float = 0.0):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self.ttl_seconds = ttl_seconds
        if ttl_seconds > 0:
            self._prune_expired()

    def _is_expired(self, path: Path) -> bool:
        if self.ttl_seconds <= 0 or not path.exists():
            return False
        return (time.time() - path.stat().st_mtime) > self.ttl_seconds

    def _prune_expired(self) -> None:
        """Delete analysis entries + downloaded videos older than the TTL.

        Whisper models (models/) are intentionally preserved.
        """
        for result_json in self.root.glob("*/*/result.json"):
            if self._is_expired(result_json):
                shutil.rmtree(result_json.parent, ignore_errors=True)
        downloads = self.root / "downloads"
        if downloads.is_dir():
            for f in downloads.iterdir():
                if f.is_file() and self._is_expired(f):
                    f.unlink(missing_ok=True)
        # Drop index records whose entry directory no longer exists.
        index = [
            e for e in self.read_index()
            if self._entry_dir(e["hash"], e["backend"], e.get("variant", "")).is_dir()
        ]
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def _entry_dir(self, digest: str, backend: str, variant: str = "") -> Path:
        namespace = f"{backend}__{variant}" if variant else backend
        return self.root / namespace / digest

    def load(self, digest: str, backend: str, variant: str = "") -> AnalysisResult | None:
        entry = self._entry_dir(digest, backend, variant)
        result_json = entry / "result.json"
        if not result_json.is_file():
            return None
        if self._is_expired(result_json):
            shutil.rmtree(entry, ignore_errors=True)
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

    def save(self, digest: str, result: AnalysisResult, variant: str = "") -> None:
        entry = self._entry_dir(digest, result.backend, variant)
        (entry / "frames").mkdir(parents=True, exist_ok=True)
        for i, fr in enumerate(result.frames):
            (entry / "frames" / f"{i:03d}.jpg").write_bytes(fr.image_bytes)
        (entry / "result.json").write_text(
            json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._record_index(digest, result, variant)

    def _record_index(self, digest: str, result: AnalysisResult, variant: str = "") -> None:
        index = self.read_index()
        index = [
            e for e in index
            if not (e["hash"] == digest and e["backend"] == result.backend and e.get("variant", "") == variant)
        ]
        index.append(
            {
                "hash": digest,
                "backend": result.backend,
                "variant": variant,
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
