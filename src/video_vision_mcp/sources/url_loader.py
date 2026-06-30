"""Download a video from a URL.

Known streaming sites (YouTube, Vimeo, Loom, ...) go through yt-dlp; everything
else is a plain HTTP stream-to-disk. Files land in the cache's `downloads/` dir.
"""

from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx


class UrlError(ValueError):
    pass


def _assert_public_http(url: str) -> None:
    """Block non-HTTP(S) schemes and private/loopback/link-local hosts (SSRF).

    Note: only the initial URL is checked; redirects to private hosts are a
    residual risk if the target server is itself untrusted.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlError(f"Only http(s) URLs are allowed, got: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UrlError("URL has no host.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UrlError(f"Cannot resolve host {host!r}: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UrlError(f"Refusing to download from non-public address {ip} (host {host!r}).")

_YT_DLP_HOSTS = (
    "youtube.com", "youtu.be", "vimeo.com", "loom.com", "dailymotion.com",
    "twitch.tv", "streamable.com", "drive.google.com",
)


def _needs_yt_dlp(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _YT_DLP_HOSTS)


def _download_yt_dlp(url: str, dest_dir: Path) -> Path:
    import yt_dlp

    out_template = str(dest_dir / "%(id)s.%(ext)s")
    opts = {"outtmpl": out_template, "format": "mp4/best", "quiet": True, "noprogress": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if path.is_file():
        return path
    # Post-processing (e.g. merge) can change the extension; fall back to newest file.
    candidates = sorted(dest_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    raise UrlError(f"yt-dlp did not produce an output file for: {url}")


def _download_http(url: str, dest_dir: Path) -> Path:
    name = Path(urlparse(url).path).name or "download.bin"
    dest = dest_dir / name
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_bytes(1 << 16):
                fh.write(chunk)
    return dest


def download(url: str, cache_dir: Path) -> Path:
    dest_dir = cache_dir / "downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    if _needs_yt_dlp(url):
        return _download_yt_dlp(url, dest_dir)
    _assert_public_http(url)
    return _download_http(url, dest_dir)
