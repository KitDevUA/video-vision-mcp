"""Resolve any of the three inputs into a local file path + human-readable label."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from . import jira_loader, url_loader


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
    jira_issue_key: str | None = None,
    attachment_id: str | None = None,
) -> ResolvedSource:
    provided = [bool(file_path), bool(url), bool(jira_issue_key)]
    if sum(provided) == 0:
        raise SourceError("Provide one of: file_path, url, or jira_issue_key.")
    if sum(provided) > 1:
        raise SourceError("Provide exactly one source (file_path, url, or jira_issue_key).")

    if file_path:
        p = Path(file_path).expanduser()
        if not p.is_file():
            raise SourceError(f"file_path does not exist: {p}")
        return ResolvedSource(path=p, label=f"file:{p.name}")

    if url:
        p = url_loader.download(url, cfg.cache_dir)
        return ResolvedSource(path=p, label=f"url:{url}")

    p = jira_loader.fetch(cfg, jira_issue_key, attachment_id, cfg.cache_dir)
    return ResolvedSource(path=p, label=f"jira:{jira_issue_key}/{p.name}")
