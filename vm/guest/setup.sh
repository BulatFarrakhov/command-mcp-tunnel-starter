#!/usr/bin/env bash
# Run locally in the guest console; the API key is prompted without echo.
set -euo pipefail
umask 077
[[ $(id -un) == agent && $HOME == /home/agent ]] || { printf '%s\n' 'Run as guest agent.' >&2; exit 1; }
cd /home/agent/command-mcp-tunnel-starter
/home/agent/.local/bin/uv run --frozen --no-sync python vm/guest/configure.py
/bin/bash vm/guest/start-services.sh
