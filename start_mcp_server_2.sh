#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Detect Docker (or set RUN_IN_DOCKER=1 in Dockerfile and check that)
if [ -f "/.dockerenv" ]; then

  # --- Generic Stabilization Delay ---
  # We will wait for a few seconds to give the Docker environment (networking, DNS, etc.)
  # time to become fully stable before launching our resource-heavy Python app.
  # This is a generic wait and does NOT depend on any specific service like Neo4j.
  echo "[Entrypoint] In Docker. Waiting 5 seconds for environment stabilization..."
  sleep 5

  echo "[Entrypoint] Wait complete. Launching Python server..."
  exec python src/crawl4ai_mcp.py --workers 1 \
    2> >(tee -a mcp_server.err >&2)
else
  source .venv/bin/activate

  exec uv run python -u src/crawl4ai_mcp.py --workers 1 \
    2> >(tee -a mcp_server.err >&2)
fi