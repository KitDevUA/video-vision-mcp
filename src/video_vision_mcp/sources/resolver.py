"""Resolve an input (local file or URL) into a local file path + label."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from . import url_loader


@dataclass
class ResolvedSource:
    path: Path
    label: str


class SourceError(ValueError):
    pass


def resolve(
    cfg: Config,
    file_path: str | None = None,
    url: str | None = None,
) -> ResolvedSource:
    provided = [bool(file_path), bool(url)]
    if sum(provided) == 0:
        raise SourceError("Provide one of: file_path or url.")
    if sum(provided) > 1:
        raise SourceError("Provide exactly one source (file_path or url).")

    if file_path:
        p = Path(file_path).expanduser()
        if not p.is_file():
            raise SourceError(f"file_path does not exist: {p}")
        return ResolvedSource(path=p, label=f"file:{p.name}")

    p = url_loader.download(url, cfg.cache_dir)
    return ResolvedSource(path=p, label=f"url:{url}")
