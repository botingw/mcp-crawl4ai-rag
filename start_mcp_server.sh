#!/bin/bash
# This script activates the virtual environment and then starts the MCP server.

# Navigate to the script's directory to ensure relative paths are correct
cd "$(dirname "$0")"

# Activate the virtual environment
source .venv/bin/activate

# Run the server, allowing stdio to be used by the MCP client
uv run src/crawl4ai_mcp.py --workers 1 \
     2> >(tee -a mcp_server.err >&2)
