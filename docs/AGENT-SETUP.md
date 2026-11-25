# Agent-operated native setup (preview)

Run on the target machine as the intended non-admin user, not on a remote agent server.

1. Read SECURITY.md and AGENTS.md. Confirm OS, architecture, account, working directory and persistence preference. Obtain a local checkout in a stable user-owned directory. Git is needed only for cloning/updating. The entrypoints reuse uv if present or download a pinned, checksum-verified uv binary, then provision Python 3.12 and locked dependencies. Linux requires curl, tar and sha256sum when bootstrapping uv.
2. Guide the human through creating a new OpenAI Secure MCP Tunnel and runtime API key with Tunnels Read + Use. Never ask them to send credentials to the agent or place them in arguments, Git or logs.
3. Run the appropriate file in a local interactive terminal:

       bash scripts/install.sh
       powershell -NoProfile -File scripts/install.ps1

   Use only the command for the target OS. The installer resolves locked Python dependencies via uv, downloads the complete pinned official tunnel client with SHA-256 verification on first setup, and prompts locally for the tunnel ID, hidden API key and working directory. The installer supplies the verified executable path automatically. V2 configuration is reused on repeated V2 installs; V1 configuration is never imported.

   Windows registers two limited interactive logon tasks; Linux installs two user systemd services. Linux requires a working user systemd manager. Neither changes power settings or grants elevated execution.
4. Finish ChatGPT plugin configuration manually as described in README. Run a harmless command in a fresh chat; local health alone is insufficient.
5. Manage the installation from the stable checkout. Pass the action to the same entrypoint (e.g. bash scripts/install.sh diagnostics or powershell -NoProfile -File scripts/install.ps1 diagnostics). Once the local environment exists, lifecycle actions do not need to install dependencies. The preflight and diagnostics actions return JSON; diagnostics reports local authentication and tunnel readiness, never claims to have tested ChatGPT. A nonzero exit means not ready.

   Equivalent direct Python commands:

       uv run --frozen python scripts/setup.py preflight
       uv run --frozen python scripts/setup.py diagnostics
       uv run --frozen python scripts/setup.py status
       uv run --frozen python scripts/setup.py check
       uv run --frozen python scripts/setup.py start
       uv run --frozen python scripts/setup.py stop
       uv run --frozen python scripts/setup.py restart
       uv run --frozen python scripts/setup.py uninstall

Stop/restart/uninstall can interrupt jobs. Inspect active jobs first. Uninstall preserves config, downloaded binaries and job history. Do not move or delete the checkout while services reference it. Do not run a second installation simultaneously. V2 has separate config/state paths, task/service names and ports (18202/18203). Create a new tunnel; do not reuse the tunnel of an existing installation. No V1 migration is supported. For Linux boot/logout persistence, follow the documented opt-in linger procedure with authorization. Windows boot before login, network/sleep recovery and real-device testing remain outstanding (see TODO.md).

Crash retries are bounded: Linux permits five starts per 120 seconds; Windows uses ten retries at one-minute intervals. Inspect diagnostics and explicitly restart after exhaustion. These are process-exit recovery policies, not a hung-process watchdog or proof of network recovery.
