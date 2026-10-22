#!/usr/bin/env bash
set -e
command -v uv >/dev/null 2>&1 || {
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
}
echo "Starting Computer Use SubQ Voice Agent..."
uv run python run_agent.py
