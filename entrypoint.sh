#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/app"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-7776}"

cd "$INSTALL_DIR" || { echo "Failed to cd to $INSTALL_DIR"; exit 1; }

# Run the venv's console script rather than `uv run`: uv wants a writable cache at runtime,
# which forecloses a read-only root filesystem later.
exec ./.venv/bin/fastmcp run main.py:mcp --transport http --host "$HOST" --port "$PORT"
