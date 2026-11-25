# Linux setup

Run these steps as the **non-root account that should execute ChatGPT commands**. This is a native Linux install; it does not require the example VPS layout. Read [SECURITY.md](../SECURITY.md) first.

## 1. Install prerequisites

Install Git and `curl` using your distribution package manager. Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) from its official installer (or your managed package source):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

Download the **full `tunnel-client` release** for your Linux architecture from [openai/tunnel-client releases](https://github.com/openai/tunnel-client/releases/latest). Select the Linux archive matching `uname -m` (`amd64` for x86_64 or `arm64` for aarch64), verify its SHA-256 against the release's `SHA256SUMS.txt`, extract the binary, and place it in a private executable location such as `~/.local/bin/tunnel-client`. Run `~/.local/bin/tunnel-client help quickstart` to confirm it works. Do not use an unrelated reverse tunnel binary.

Create a new tunnel in OpenAI Platform as described in the [official Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels). Associate the intended Platform organization and ChatGPT workspace, and obtain a runtime API key with the required tunnel permissions. Keep the key in a local password manager until `init` asks for it.

## 2. Install this private repo

```bash
git clone git@github.com:BulatFarrakhov/command-mcp-tunnel-starter.git
cd command-mcp-tunnel-starter
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen command-mcp init
```

At `init`, enter the new `tunnel_id`, runtime key at the hidden prompt, the absolute `tunnel-client` path, and an existing absolute default working directory. The config is written to `~/.config/command-mcp-v2/config.json` with mode `0600`; state goes to `~/.local/state/command-mcp-v2`. Never commit either. Use `COMMAND_MCP_CONFIG=/absolute/path/config.json` only when deliberately changing the config path.

## 3. Prove the interactive setup

In terminal A:

```bash
uv run --frozen --no-sync command-mcp serve
```

In terminal B:

```bash
uv run --frozen --no-sync command-mcp tunnel
```

In terminal C:

```bash
uv run --frozen --no-sync command-mcp check
ss -ltn '( sport = :18202 or sport = :18203 )'
```

`check` must report authenticated MCP health and tunnel readiness. `ss` must show only `127.0.0.1` listeners for these ports. A direct unauthenticated `curl -i http://127.0.0.1:18202/healthz` must return 401. The tunnel client needs outbound HTTPS but no inbound firewall opening.

## 4. Keep it running with user systemd

After the interactive checks pass, create two **user** units under `~/.config/systemd/user/`. Substitute the output of `command -v uv` and the absolute path to this checkout. Example:

`command-mcp-v2.service`:

```ini
[Unit]
Description=Private command-only MCP server
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/EXAMPLE/command-mcp-tunnel-starter
ExecStart=/home/EXAMPLE/.local/bin/uv run --frozen --no-sync command-mcp serve
Restart=always
RestartSec=3
UMask=0077

[Install]
WantedBy=default.target
```

`command-mcp-v2-tunnel.service`:

```ini
[Unit]
Description=Secure MCP Tunnel for private commands
After=command-mcp-v2.service network-online.target
Requires=command-mcp-v2.service

[Service]
Type=simple
WorkingDirectory=/home/EXAMPLE/command-mcp-tunnel-starter
ExecStart=/home/EXAMPLE/.local/bin/uv run --frozen --no-sync command-mcp tunnel
Restart=always
RestartSec=3
UMask=0077

[Install]
WantedBy=default.target
```

Enable and validate:

```bash
systemctl --user daemon-reload
systemctl --user enable --now command-mcp-v2.service command-mcp-v2-tunnel.service
systemctl --user is-active command-mcp-v2.service command-mcp-v2-tunnel.service
uv run --frozen --no-sync command-mcp check
```

User services normally run with a login session. If the user requires operation after logout, an administrator can enable linger for this account with `sudo loginctl enable-linger ACCOUNT`; verify startup after logout/reboot. Do not run these units as root just to make them persistent.

Inspect failures with `journalctl --user -u command-mcp-v2.service -u command-mcp-v2-tunnel.service -n 100 --no-pager`. Never paste logs containing command output or credentials into a public issue. Finish setup in ChatGPT using the steps in the [README](../README.md#setup-map).
