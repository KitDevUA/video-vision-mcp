"""ffprobe metadata + ffmpeg frame/audio extraction.

Frame count adapts to duration within the configured [min_frames, max_frames]
budget; frames are scaled so the longer side is <= frame_max_px.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .installer import ensure_ffmpeg


class FfmpegError(RuntimeError):
    pass


def _scale_filter(max_px: int) -> str:
    # Limit the longer side to max_px, keep aspect ratio, force even dimensions.
    return (
        f"scale='if(gte(iw,ih),min({max_px},iw),-2)':"
        f"'if(gte(iw,ih),-2,min({max_px},ih))'"
    )


def probe(path: Path) -> dict:
    """Return {duration, width, height, has_audio, fps, vcodec} via ffprobe."""
    _, ffprobe = ensure_ffmpeg()
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe failed: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = None
    if data.get("format", {}).get("duration"):
        duration = float(data["format"]["duration"])
    elif video and video.get("duration"):
        duration = float(video["duration"])
    fps = None
    if video and video.get("avg_frame_rate") and "/" in video["avg_frame_rate"]:
        num, den = video["avg_frame_rate"].split("/")
        fps = float(num) / float(den) if float(den) else None
    return {
        "duration": duration,
        "width": int(video["width"]) if video and video.get("width") else None,
        "height": int(video["height"]) if video and video.get("height") else None,
        "has_audio": audio is not None,
        "fps": fps,
        "vcodec": video.get("codec_name") if video else None,
    }


def frame_count_for_interval(duration: float | None, interval: float, max_frames: int) -> int:
    """Frames to sample given a seconds-per-frame interval, capped at max_frames.

    max_frames is a safety ceiling so a dense interval on a long video can't
    explode the model context.
    """
    if not duration or duration <= 0 or not interval or interval <= 0:
        return 1
    return max(1, min(max_frames, round(duration / interval)))


def extract_frames(path: Path, count: int, max_px: int, duration: float | None) -> list[tuple[float, bytes]]:
    """Extract `count` evenly-spaced frames. Returns [(timestamp_seconds, jpeg_bytes)]."""
    ffmpeg, _ = ensure_ffmpeg()
    if not duration or count <= 0:
        count = max(count, 1)
    import tempfile

    with tempfile.TemporaryDirectory(prefix="vvmcp-frames-") as tmp:
        out_pattern = str(Path(tmp) / "frame_%05d.jpg")
        if duration and duration > 0:
            vf = f"fps={count}/{duration:.4f},{_scale_filter(max_px)}"
        else:
            vf = _scale_filter(max_px)
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-vf", vf, "-q:v", "3", out_pattern],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise FfmpegError(f"ffmpeg frame extraction failed: {proc.stderr.strip()}")
        files = sorted(Path(tmp).glob("frame_*.jpg"))
        interval = (duration / len(files)) if (duration and files) else 0.0
        return [(i * interval, f.read_bytes()) for i, f in enumerate(files)]


def extract_frames_at(path: Path, timestamps: list[float], max_px: int) -> list[tuple[float, bytes]]:
    """Extract one frame at each requested timestamp (seconds)."""
    ffmpeg, _ = ensure_ffmpeg()
    import tempfile

    results: list[tuple[float, bytes]] = []
    with tempfile.TemporaryDirectory(prefix="vvmcp-at-") as tmp:
        for i, ts in enumerate(timestamps):
            out = Path(tmp) / f"at_{i:03d}.jpg"
            proc = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{ts:.3f}",
                 "-i", str(path), "-frames:v", "1", "-vf", _scale_filter(max_px),
                 "-q:v", "3", str(out)],
                capture_output=True, text=True,
            )
            if proc.returncode == 0 and out.is_file():
                results.append((ts, out.read_bytes()))
    return results


def extract_audio_wav(path: Path, out_dir: Path) -> Path | None:
    """Extract mono 16kHz WAV for whisper. Returns None if there is no audio."""
    ffmpeg, _ = ensure_ffmpeg()
    out = out_dir / "audio.wav"
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        return None
    return out
