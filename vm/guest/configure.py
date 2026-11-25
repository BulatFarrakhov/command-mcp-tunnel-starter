"""Create appliance defaults using local, hidden credential entry only."""

import getpass
import json
import os
import secrets
from pathlib import Path

from command_mcp_tunnel_starter.cli import config_path, load_config, validate


def main() -> None:
    path = config_path()
    if path.exists():
        load_config()
        print("Existing private configuration retained.")
        return
    if not os.isatty(0):
        raise SystemExit("Use an interactive guest console for hidden key entry.")
    settings = {
        "tunnel_id": input("Tunnel ID (tunnel_...): ").strip(),
        "runtime_api_key": getpass.getpass("Runtime API key (hidden): ").strip(),
        "tunnel_client_path": "/home/agent/.local/bin/tunnel-client",
        "inbound_token": secrets.token_urlsafe(48),
        "default_cwd": "/workspace",
        "state_dir": "/home/agent/.local/state/command-mcp-tunnel",
        "server_port": 18102,
        "tunnel_health_port": 18103,
        "max_concurrent_commands": 4,
        "max_output_bytes": 31_457_280,
        "max_timeout_seconds": 86_400,
        "workspace_policy": "This service runs inside a Linux VM. Work in /workspace. "
                            "Do not mount, inspect, or modify Windows host disks, shares, or services.",
    }
    validate(settings)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")
    print(f"Private configuration saved at {path}.")


if __name__ == "__main__":
    main()
