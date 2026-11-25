#!/usr/bin/env bash
# Called after local setup or host provisioning supplies the private config.
set -euo pipefail
umask 077
[[ $(id -un) == agent && $HOME == /home/agent ]] || { printf '%s\n' 'Run as guest agent.' >&2; exit 1; }
readonly repo=/home/agent/command-mcp-tunnel-starter
readonly uv=/home/agent/.local/bin/uv
cd "$repo"
export COMMAND_MCP_CONFIG=/home/agent/.config/command-mcp-tunnel/config.json
"$uv" run --frozen --no-sync python -c 'from command_mcp_tunnel_starter.cli import load_config; load_config()'
sudo -n systemctl start command-mcp.service command-mcp-tunnel.service
ready=false
for _ in {1..30}; do
    if timeout 12 "$uv" run --frozen --no-sync command-mcp check >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 2
done
if [[ $ready != true ]]; then
    printf '%s\n' 'Local MCP/tunnel checks failed. Boot persistence has not been enabled by this run.' \
        'Inspect locally: sudo journalctl -u command-mcp -u command-mcp-tunnel -n 60 --no-pager' >&2
    exit 1
fi
"$uv" run --frozen --no-sync python vm/guest/verify.py
sudo -n systemctl enable command-mcp.service command-mcp-tunnel.service
sudo -n systemctl is-active --quiet command-mcp.service command-mcp-tunnel.service
printf '%s\n' 'Guest services are healthy and enabled for VM boot.'
