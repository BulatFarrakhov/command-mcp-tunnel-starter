# Fresh agent instructions

This repository is a **command-only** MCP server for a **private OpenAI Secure MCP Tunnel**. It has exactly `start_command`, `get_command`, and `cancel_command`. Do not add Codex agent/gateway, SSH, file staging, artifact download, or public HTTP exposure without a separate user request.

## Ask the user before setup

1. Which host OS is it: native Windows or Linux? Is it the actual machine that should run commands?
2. Which local OS account should execute commands? What files and privileges should it have? Should it be able to elevate, and if so, for which tasks?
3. Which ChatGPT workspace/account will use the plugin, and which OpenAI Platform organization owns the tunnel? Can the user create a tunnel and a runtime API key with Tunnels Read + Use?
4. Should the process run only while the user is logged in or survive logoff/reboot? This changes the Windows task account and Linux service choice.
5. What existing absolute directory should be the default working directory? What job concurrency and timeout limits are acceptable?

Do not ask the user to paste the runtime key into a chat or issue. `command-mcp init` reads it locally with a hidden prompt. Never copy a real config file into this repository.

## Procedure

1. Read `README.md`, `SECURITY.md`, and the relevant `docs/LINUX.md` or `docs/WINDOWS.md` fully.
2. Confirm ChatGPT custom MCP server access, tunnel workspace association, and Platform Tunnels permissions in official docs. These product rules can change.
3. Install `uv`, Python 3.12, and the official `openai/tunnel-client` release for this OS. Use `uv sync --frozen`.
4. Run `uv run --frozen command-mcp init` under the intended execution account. Keep the generated config outside Git and restrict access to that account.
5. Start `serve` and `tunnel` in separate processes. Run `uv run --frozen command-mcp check`. Inspect the MCP tool list and run a harmless command before any privileged command.
6. Install OS startup integration only after interactive checks pass. Verify restart behavior and localhost-only listeners.
7. In ChatGPT Plugins, add a custom MCP server with Connection = Tunnel and this tunnel ID. Confirm exactly three tools in a new ordinary ChatGPT conversation.

## Invariants

- The server binds `127.0.0.1`, requires `X-Command-MCP-Token`, and the tunnel admin listener binds `127.0.0.1`.
- No inbound firewall port is needed. `tunnel-client` makes outbound HTTPS calls to OpenAI.
- The runtime key and local token are private. A command with the OS account's permissions can still read files accessible to that account, including its config; treat plugin access as equivalent to shell access.
- `request_id` is a UUID. Retry the same ID for uncertain submissions. A restarted in-flight job is `interrupted` and is never replayed automatically.
- Commands use Bash on Linux and Windows PowerShell on native Windows. They have no interactive stdin or terminal.
- Changes to tool metadata require refreshing the custom MCP server connection in ChatGPT and opening a new chat.

## Development

Run `uv run --frozen pytest -q` on both OSes through CI. Keep dependencies locked in `uv.lock`. Do not commit secrets, output logs, or state databases. Cross-platform claims require the Windows and Linux CI jobs to pass; an Ubuntu-only local test is not proof of Windows behavior.
