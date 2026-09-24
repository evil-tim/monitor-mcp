"""Entrypoint for `fastmcp run main.py:mcp`, mirroring the nmap-mcp repo shape."""

from monitor_mcp.server import mcp

__all__ = ["mcp"]
