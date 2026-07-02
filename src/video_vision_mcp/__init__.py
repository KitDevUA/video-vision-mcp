"""video-vision-mcp: analyze any video through a single set of MCP tools."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("video-vision-mcp")
except PackageNotFoundError:  # not installed (e.g. running from a raw checkout)
    __version__ = "0.0.0+unknown"
