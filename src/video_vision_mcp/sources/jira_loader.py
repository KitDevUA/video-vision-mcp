"""Fetch a Jira attachment directly via REST, using the same creds as mcp-atlassian.

We do NOT call the Jira MCP — we hit the REST API ourselves with JIRA_URL /
JIRA_USERNAME / JIRA_API_TOKEN from the shared .env. This keeps a single tool
call (`analyze_video`) end-to-end instead of forcing the user to coordinate two
MCP servers.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from ..config import Config

_VIDEO_EXTS = (".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv")


class JiraConfigError(RuntimeError):
    """Jira creds missing/invalid — surfaced with a hint to check .env."""


def _client(cfg: Config) -> httpx.Client:
    if not (cfg.jira_url and cfg.jira_username and cfg.jira_api_token):
        raise JiraConfigError(
            "Jira credentials missing. Set JIRA_URL, JIRA_USERNAME and JIRA_API_TOKEN "
            "in the .env (the same ones mcp-atlassian uses)."
        )
    return httpx.Client(
        base_url=cfg.jira_url.rstrip("/"),
        auth=(cfg.jira_username, cfg.jira_api_token),
        timeout=120,
        follow_redirects=True,
    )


def _is_video_attachment(att: dict) -> bool:
    mime = (att.get("mimeType") or "").lower()
    name = (att.get("filename") or "").lower()
    return mime.startswith("video/") or name.endswith(_VIDEO_EXTS)


def _pick_attachment(cfg: Config, issue_key: str, client: httpx.Client) -> dict:
    resp = client.get(f"/rest/api/3/issue/{issue_key}", params={"fields": "attachment"})
    if resp.status_code == 401:
        raise JiraConfigError("Jira returned 401 Unauthorized — check JIRA_API_TOKEN in .env.")
    if resp.status_code == 404:
        raise JiraConfigError(f"Jira issue {issue_key} not found (or no access).")
    resp.raise_for_status()
    attachments = resp.json().get("fields", {}).get("attachment", []) or []
    videos = [a for a in attachments if _is_video_attachment(a)]
    if not videos:
        raise JiraConfigError(f"No video attachment found on {issue_key}.")
    if len(videos) > 1:
        listing = ", ".join(f"{a['id']}:{a['filename']}" for a in videos)
        raise JiraConfigError(
            f"{issue_key} has multiple video attachments — pass attachment_id. Options: {listing}"
        )
    return videos[0]


def fetch(cfg: Config, issue_key: str, attachment_id: str | None, cache_dir: Path) -> Path:
    dest_dir = cache_dir / "jira"
    dest_dir.mkdir(parents=True, exist_ok=True)
    with _client(cfg) as client:
        if attachment_id is None:
            att = _pick_attachment(cfg, issue_key, client)
            attachment_id = att["id"]
            filename = att["filename"]
        else:
            filename = f"{issue_key}-{attachment_id}.bin"
        # Jira attachment ids are integers; reject anything else to stop REST path traversal.
        if not str(attachment_id).isdigit():
            raise JiraConfigError(f"Invalid attachment_id (must be numeric): {attachment_id!r}")
        # Strip any directory parts from the server-supplied filename (path traversal).
        safe_name = Path(filename).name or "attachment.bin"
        dest = dest_dir / f"{attachment_id}-{safe_name}"
        with client.stream("GET", f"/rest/api/3/attachment/content/{attachment_id}") as resp:
            if resp.status_code == 401:
                raise JiraConfigError("Jira returned 401 Unauthorized — check JIRA_API_TOKEN in .env.")
            if resp.status_code == 404:
                raise JiraConfigError(f"Jira attachment {attachment_id} not found.")
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in resp.iter_bytes(1 << 16):
                    fh.write(chunk)
    return dest
