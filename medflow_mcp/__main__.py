"""Entry point for `python -m medflow_mcp`."""
from medflow_mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
