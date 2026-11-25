# Agent-operated native setup

Run on the target computer as the intended non-admin user, not on a remote agent server.

1. Read SECURITY.md and AGENTS.md. Confirm OS, architecture, account, working directory, permissions and persistence preference. Obtain a stable user-owned checkout.
2. Guide the human through creating a new OpenAI Secure MCP Tunnel and a runtime API key with Tunnels Read + Use. Credentials must be entered by the human locally, not sent to the agent, placed in command arguments or committed.
3. Run the OS-specific entrypoint in a local interactive terminal:

       bash scripts/install.sh preflight
       bash scripts/install.sh install

       powershell -NoProfile -File scripts/install.ps1 preflight
       powershell -NoProfile -File scripts/install.ps1 install

   Use only the target OS commands. The installer provisions Python and locked dependencies via uv, downloads and verifies the pinned official tunnel-client release, and prompts locally for credentials and working directory. It preserves existing V2 configuration and never imports V1.
4. Complete the ChatGPT connection described in README.md. Verify a harmless command in a fresh ordinary ChatGPT chat. Local readiness alone does not establish ChatGPT connectivity.

## Persistence

Default: Windows interactive logon tasks; Linux user systemd services. The OS manager starts two independent supervisors with bounded restart policies.

For boot startup before login or continued operation after logout, first obtain explicit authorization, then choose:

       bash scripts/install.sh install --unattended
       powershell -NoProfile -File scripts/install.ps1 install -Unattended

Linux enables linger for the current account (authorization may be required). Uninstall does not disable linger because other services may depend on it. Windows registers password-backed limited tasks with boot and logon triggers; the actual account password, not a PIN, is entered locally and handed to Task Scheduler. Account policy or missing rights may prevent registration. Do not use SYSTEM or elevate command execution to bypass this. Switching Windows startup modes requires uninstalling V2 tasks first; configuration is preserved. These unattended modes need validation on the target machine.

Neither mode operates when the computer is asleep, hibernating or powered off. Ask the human to approve any power changes; no installer changes sleep or lid-close settings.

## Lifecycle

Use the same entrypoint with action: preflight, diagnostics, status, check, start, stop, restart or uninstall. For example:

       bash scripts/install.sh diagnostics
       powershell -NoProfile -File scripts/install.ps1 diagnostics

Preflight, status and diagnostics output JSON (exit 0 means the respective check succeeded; nonzero means not ready). Status includes service-manager state and available failure codes, plus local authentication and tunnel readiness; it never implies ChatGPT has been tested. Start and restart wait for local readiness.

The watchdog checks its own local component, allows 45 seconds at startup, and exits after three consecutive local health failures. A responsive tunnel readiness endpoint that returns non-200 is not itself a reason to restart. The OS manager retries failures within a bounded policy; inspect diagnostics and explicitly restart after exhaustion. Linux uses five starts per 120 seconds and a ten-second restart delay; Windows uses ten retries at one-minute intervals. Windows supervisors contain their child processes in a Job Object, failing closed if containment is unavailable.

Inspect active jobs before stop/restart/uninstall: these can interrupt them. Uninstall preserves V2 credentials, binaries and SQLite history. To update this experimental branch, uninstall services using the existing checkout first, update the checkout, then run install again; do not overwrite service definitions while active. Do not move/delete the checkout while registered services reference it.

V2 has separate config/state paths, task/service names and ports (18202/18203). Do not run two instances of V2 under the same account or reuse an existing V1 tunnel. See TODO.md for actual-machine verification.
