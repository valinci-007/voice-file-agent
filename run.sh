#!/bin/zsh
# Launcher: always uses the project venv, works from any directory.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Setting up venv (first run only)..."
  python3 -m venv .venv && .venv/bin/pip install --quiet claude-agent-sdk
fi
exec .venv/bin/python agent.py "$@"
