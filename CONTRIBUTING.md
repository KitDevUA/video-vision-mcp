# Contributing

Thanks for your interest in improving video-vision-mcp.

## Development setup

```bash
git clone https://github.com/KitDevUA/video-vision-mcp.git
cd video-vision-mcp
uv venv && source .venv/bin/activate      # or: python -m venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"                # or: pip install -e ".[dev]"
```

`ffmpeg` resolves to your system binary if present, otherwise to the bundled
`static-ffmpeg` (fetched on first use). Nothing is installed system-wide.

## Running tests

```bash
pytest -q
```

Tests are offline by design — no ffmpeg, network, whisper, or cloud keys
required. Keep new tests that way where possible; gate anything needing a real
backend behind an explicit marker or skip.

## Project layout

- `src/video_vision_mcp/server.py` — FastMCP tools (the public surface).
- `backends/` — tier 1 (local), tier 2 (cloud ASR), tier 3 (Gemini).
- `sources/` — input resolution (file / url / Jira).
- `media/` — ffmpeg + dependency resolution.
- `pipeline.py` — orchestration (resolve → hash → cache → backend).

## Conventions

- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/) —
  `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`.
- **Code/comments/docs**: English. Comments only for non-obvious *why*; keep them short.
- **Errors**: raise typed errors with clear messages; never swallow silently.
- **No secrets** in code or commits — config comes from `.env` only.

## Pull requests

1. Branch from `main`.
2. Make the change + add/adjust tests; `pytest` green.
3. Open a PR describing what and why. CI (tests + build) must pass.

## Releasing (maintainers)

Releases are **fully tag-driven** — you never hand-edit the version. Publishing
`.github/workflows/publish.yml` stamps the version from the release tag into
`pyproject.toml` + `server.json`, then publishes to PyPI and the MCP registry,
both via OIDC (no tokens). `__version__` derives from installed metadata.

**To cut a release:** create a GitHub Release with tag `vX.Y.Z`. That's it.

**One-time setup:**
- **PyPI Trusted Publishing:** on pypi.org add a GitHub publisher for the
  `video-vision-mcp` project — owner `KitDevUA`, repo `video-vision-mcp`,
  workflow `publish.yml`, environment `pypi`.
- **MCP registry:** authorized via GitHub OIDC (`mcp-publisher login github-oidc`
  in the workflow); the `io.github.KitDevUA` namespace matches the repo owner.
  Ownership of the PyPI package is verified via the `mcp-name:` marker in the
  README (carried into the PyPI description).

The committed `version` fields are just a local-dev fallback; the release tag is
the source of truth for what gets published.
