# Agent-operated native setup (preview)

Run on the target machine as the intended non-admin user, not on a remote agent server.

1. Read SECURITY.md and AGENTS.md. Confirm OS, architecture, account, working directory and persistence preference. Install Git and uv if missing using approved sources. Clone into a stable user-owned directory.
2. Guide the human through creating a new OpenAI Secure MCP Tunnel and runtime API key with Tunnels Read + Use. Never ask them to send credentials to the agent or place them in arguments, Git or logs.
3. Run the appropriate file in a local interactive terminal:

       bash scripts/install.sh
       powershell -NoProfile -File scripts/install.ps1

   Use only the command for the target OS. The installer resolves locked Python dependencies via uv, downloads the complete pinned official tunnel client with SHA-256 verification on first setup, and prompts locally for the tunnel ID, hidden API key and working directory. Accept the suggested absolute tunnel-client path. Existing config is reused.

   Windows registers two limited interactive logon tasks; Linux installs two user systemd services. Linux requires a working user systemd manager. Neither changes power settings or grants elevated execution.
4. Finish ChatGPT plugin configuration manually as described in README. Run a harmless command in a fresh chat; local health alone is insufficient.
5. Manage the installation from the stable checkout:

       uv run --frozen python scripts/setup.py status
       uv run --frozen python scripts/setup.py check
       uv run --frozen python scripts/setup.py start
       uv run --frozen python scripts/setup.py stop
       uv run --frozen python scripts/setup.py restart
       uv run --frozen python scripts/setup.py uninstall

Stop/restart/uninstall can interrupt jobs. Inspect active jobs first. Uninstall preserves config, downloaded binaries and job history. Do not move or delete the checkout while services reference it. Do not run a second installation simultaneously. Existing manual installations require explicit migration. For Linux boot/logout persistence, follow the documented opt-in linger procedure with authorization. Windows boot before login, network/sleep recovery and real-device testing remain outstanding (see TODO.md).
