# Linux appliance workspace

Commands from the private ChatGPT plugin run here as `agent` inside an Ubuntu
24.04 VirtualBox virtual machine. `/workspace` is persistent guest storage.

- Use `/workspace/<project>` for projects and generated files.
- The `agent` account can use `sudo -n` for full administration **inside this VM**.
- Windows host drives, credentials, and devices are not part of this workspace.
  Do not assume access to them or add shared folders or network exposure without
  an explicit user request.
- The MCP server and tunnel listen only on guest loopback. Do not open public
  ports or change their authentication settings during routine project work.
- Keep secrets out of repositories and command output. Private tunnel settings
  live at `/home/agent/.config/command-mcp-tunnel/config.json`; do not print them.
- Commands have no terminal or interactive stdin. Use noninteractive commands.
- For long commands, retain the returned job ID and poll `get_command` using its
  `next_offset`. Reuse the same UUID `request_id` for an uncertain submission.
- An interrupted job may already have changed files. Inspect before resubmitting.
- Before changing the command service, finish active jobs. Restarting
  `command-mcp.service` terminates its command processes.

Service source: `/home/agent/command-mcp-tunnel-starter`.
Status: `systemctl status command-mcp.service command-mcp-tunnel.service`.
Health: from the source directory, run
`/home/agent/.local/bin/uv run --frozen --no-sync command-mcp check`.
The two services run at guest boot. Windows must keep the VM running for ChatGPT
to reach it; guest service persistence does not start VirtualBox on the host.
