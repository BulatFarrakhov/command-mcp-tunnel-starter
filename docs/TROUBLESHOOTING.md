# Troubleshooting

Run `uv run --frozen --no-sync command-mcp check` from the repo under the configured account. It tests the local auth contract and tunnel readiness; it cannot prove that ChatGPT has installed the plugin.

| Symptom | Check and remedy |
| --- | --- |
| `No config` | Run `command-mcp init` as the account that will launch both processes. Confirm `COMMAND_MCP_CONFIG` points to the intended absolute file if customized. |
| Config permissions error | Linux: `chmod 600 ~/.config/command-mcp-tunnel/config.json` and `chmod 700 ~/.config/command-mcp-tunnel`. Windows: inspect `icacls "$env:APPDATA\command-mcp-tunnel\config.json"`; restrict it to the intended account. |
| MCP server unreachable | Start `command-mcp serve`. Check the configured `server_port` and that another process is not already using it. It must listen on `127.0.0.1` only. |
| Anonymous health is not 401 | Stop deployment. Check that the process on `server_port` is this MCP server and that token middleware is active. |
| Tunnel not ready | Start `command-mcp tunnel`. Check the `tunnel-client` binary path, runtime key, tunnel ID, outbound HTTPS, and local server health. Use `tunnel-client doctor --explain` if supported by the installed release. Inspect the loopback admin UI `/ui` and `/health/mcp` on `tunnel_health_port`. |
| Tunnel absent in ChatGPT | Check Platform organization and ChatGPT workspace association, Tunnels Read + Use permission, and custom MCP server permissions in the ChatGPT workspace. Permission changes may take time to propagate. |
| ChatGPT lists old tools | In ChatGPT Plugins, open the custom server connection and select Refresh, then start a new chat. There should be exactly three tools. |
| `Command slots are busy` | Poll active jobs or cancel them. The default limit is four; edit `max_concurrent_commands` in private config if the host can handle more. |
| `interrupted` after restart | The job may already have had effects. Inspect the target files/processes. The same `request_id` returns the interrupted record; a new UUID is a new execution. |
| Long output stops growing | The default saved output cap is 30 MiB. `output_limit_reached=true` confirms truncation. A process that keeps writing is still drained so it can finish. |
| Windows command cannot access network when scheduled | Use an account with an interactive or password-backed logon token. S4U tasks can lack network credentials. The starter's manual Task Scheduler setup uses an interactive logon trigger by default. |

OpenAI product instructions: [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels), [connect and refresh a plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt), [custom MCP server access](https://developers.openai.com/api/docs/guides/custom-mcp-server).
