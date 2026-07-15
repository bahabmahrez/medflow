"""
MedFlow MCP server — exposes the 10 query-layer functions as MCP tools
for any Model Context Protocol client (Claude Desktop, etc.).
"""
from .server import mcp

__all__ = ["mcp"]
