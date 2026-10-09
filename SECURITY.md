# Security model

This server intentionally accepts arbitrary shell commands from an authorized ChatGPT plugin. Access to the plugin is therefore equivalent to shell access as the configured OS account. A command can read secrets, edit files, start processes, and reach networks available to that account. The local token, output cap, and tunnel protect the transport and resource usage; they do not sandbox commands.

## Access boundaries

1. Use a dedicated non-admin OS account with access only to the intended working files. Do not grant `sudo`, Administrators, Docker socket, or cloud credentials unless the user explicitly wants that authority. A privileged command service is a privileged remote-control channel.
2. In OpenAI Platform, use a dedicated runtime key with the smallest available tunnel permissions. Tunnels Read + Use is needed for operation. Creating/editing the tunnel requires Manage. Associate only the intended Platform organization and ChatGPT workspace. Restrict who may add/use the custom MCP plugin in the workspace.
3. Keep `config.json` outside the checkout. `command-mcp init` creates it under the operator's private config directory. On Linux it is mode `0600` in a `0700` directory. On Windows it removes inherited file ACLs and grants the current user full access; inspect with `icacls` before deployment. Backups of this file are secrets too.
4. The HTTP MCP server and tunnel health listener bind `127.0.0.1`. Do not proxy them to the internet. Keep the host firewall closed to inbound access. Allow outbound HTTPS to OpenAI as documented in the [Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
5. The tunnel injects a private `X-Command-MCP-Token` on its local hop. The server rejects requests without it, including `/healthz`. `command-mcp check` verifies rejection and acceptance. Never place the runtime API key or local token in command arguments or logs.

## Key limitation of unrestricted commands

The command process runs as the same OS account that owns the repo's generated config by default. It can therefore read that config and any other file accessible to the account. The code removes known tunnel credential environment variables before spawning a command to avoid accidental inheritance, but this is not a security boundary. If secrets must be inaccessible to commands, move the tunnel client and its key to a separate account with a separate credential store and adjust the launch design. Do not claim that config permissions alone isolate secrets from arbitrary commands under the same account.

## Command lifecycle

- `request_id` UUIDs make submission idempotent. Repeating an ID with different arguments fails. In-flight jobs become `interrupted` on service restart and are not replayed.
- Output is stored as combined stdout/stderr under the private state directory and capped at the configured byte limit. Output can contain secrets if a command prints them; limit account access, retention, and backups accordingly.
- Cancellation and timeout stop the process tree best-effort. Work done before the signal remains. A child that escapes its process group or task tree can survive; inspect the host if that matters.
- The service does not provide a terminal, interactive stdin, per-command approval, or command allowlist. If your use case requires those controls, change the product design before deployment.

## Compromise or lost access

1. Disable/uninstall the custom plugin, then stop `command-mcp tunnel` and `command-mcp serve`.
2. Revoke the runtime API key and remove the tunnel association or tunnel in Platform if compromised.
3. Replace `runtime_api_key` and `inbound_token` in the private config. Generate a new local token with `python -c "import secrets; print(secrets.token_urlsafe(48))"` on the host; restart both processes.
4. Review command job records, output logs, shell effects, and account credentials accessible to the execution account. Rotate other exposed credentials as needed.

The tunnel ID is a selector, not the runtime secret. Knowing an ID alone does not grant a person access to the tunnel: Platform permissions and ChatGPT workspace/plugin controls also apply. Do not use a tunnel ID as an authorization mechanism.
