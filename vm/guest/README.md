# Guest provisioning interface

The Windows installer copies the source to
`/home/agent/command-mcp-tunnel-starter` in an Ubuntu 24.04 guest. It creates the
`agent` account with passwordless sudo **inside the VM**, then invokes:

```bash
/bin/bash /home/agent/command-mcp-tunnel-starter/vm/guest/bootstrap.sh
```

Run as `agent`, with `HOME=/home/agent`. This is a VM provisioning script; do not
run it on an existing host. It uses sudo for OS packages, `/workspace`, and
systemd unit installation. Python dependency installation runs as `agent` with
`uv sync --frozen --no-dev`. It refuses to update while either service is active.
After finishing active jobs, stop both services before rerunning provisioning.

The host may preseed private configuration at
`/home/agent/.config/command-mcp-tunnel/config.json`. Use the existing CLI schema
and these guest paths:

| Setting | Value |
| --- | --- |
| `tunnel_client_path` | `/home/agent/.local/bin/tunnel-client` |
| `default_cwd` | `/workspace` |
| `state_dir` | `/home/agent/.local/state/command-mcp-tunnel` |
| `server_port` | `18102` |
| `tunnel_health_port` | `18103` |

The config directory is `0700` and file is `0600`, owned by `agent`. Bootstrap
does not replace an existing config or `/workspace/AGENTS.md`. Config and job
state stay outside the source tree. No secret is accepted as a script argument.
The same VM account can read its config and administer the guest; permissions
do not isolate the config from plugin commands.

Without configuration, bootstrap installs software and units but does not start
or enable them. In a guest console, run:

```bash
bash /home/agent/command-mcp-tunnel-starter/vm/guest/setup.sh
```

This asks for the tunnel ID and runtime API key locally, with hidden key input.
If the host supplies config later, call `vm/guest/start-services.sh` with Bash
instead. Startup validates authentication, tunnel readiness, loopback listeners,
the exact three tools, repeated request IDs, and a harmless command proving
`agent`, `/workspace`, and `sudo -n` before enabling guest boot persistence.
Failed validation exits nonzero, leaves services available for local diagnosis,
and does not newly enable them. Existing enablement is not changed.

Units are `command-mcp.service` and `command-mcp-tunnel.service`, installed under
`/etc/systemd/system`, both with `User=agent`, `Restart=always`, and a private
umask. Stopping the server unit terminates its command process group. No ports
or firewall rules are opened. Guest services start on VM boot; host-side VM
startup is the Windows installer's responsibility.

Downloads are pinned to uv `0.13.0` and the **full** tunnel-client `v0.0.16`
release. Embedded SHA-256 values were checked against the official release
checksums on 2026-10-10. Both amd64 and arm64 guest archives are supported; the
Windows appliance installer may impose a narrower host architecture requirement.
The full tunnel release includes `cloudflared` and its manifest, installed beside
the executable under `~/.local/lib/tunnel-client-v0.0.16`.

Checks for these provisioning files (from the repository root):

```bash
bash -n vm/guest/bootstrap.sh vm/guest/setup.sh vm/guest/start-services.sh
uv run --frozen pytest -q vm/guest/tests
```

These checks do not substitute for installation and reboot validation on an
actual Windows Home / VirtualBox guest.
