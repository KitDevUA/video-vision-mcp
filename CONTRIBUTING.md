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

**One-time — PyPI Trusted Publishing (no tokens):** on pypi.org create/claim the
`video-vision-mcp` project, then add a GitHub publisher under *Publishing*:
owner `KitDevUA`, repo `video-vision-mcp`, workflow `publish.yml`, environment
`pypi`.

**Each release:**

1. Bump `version` in both `pyproject.toml` and `server.json` (keep them equal).
2. Push, let CI pass.
3. Create a GitHub Release with tag `vX.Y.Z`. This triggers `.github/workflows/publish.yml`,
   which builds and uploads to PyPI via OIDC.
4. **MCP registry** (after the PyPI version is live):
   ```bash
   # install the publisher CLI once (see github.com/modelcontextprotocol/registry)
   mcp-publisher login github
   mcp-publisher publish        # reads ./server.json
   ```
   The registry verifies package ownership via the `mcp-name:` marker in the
   README (carried into the PyPI description). The `io.github.*` namespace is
   authorized by your GitHub login.
