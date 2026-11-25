# TODO: reliable startup and availability

The command MCP server and OpenAI tunnel are separate processes. Native Windows and Linux have documented manual startup procedures; the Windows Home VM preview automates guest service installation and Windows logon startup, but its full lifecycle is not yet verified on real Windows Home hardware. Do not treat any of these as an always-online guarantee.

## P0 — native installation and lifecycle

- [ ] Add an idempotent native Windows PowerShell installer that registers the server and tunnel as two scheduled tasks under the intended non-admin account. Resolve absolute paths, set the working directory, prevent duplicate instances, start the server first, and configure restart on failure. Provide status, start, stop, restart and uninstall commands. Preserve config and job data by default.
- [ ] Decide and document Windows logon-only vs unattended boot modes; test a supported least-privilege account and logon type, including network access before login and after logout. Do not default to SYSTEM or elevated command execution.
- [ ] Add an idempotent native Linux installer for user systemd units with automatic startup and restart. Make boot persistence via linger an explicit opt-in requiring appropriate authorization; verify after actual logout/reboot. Include status, restart and uninstall.
- [ ] Ensure upgrades preserve credentials, config and SQLite state, drain or explicitly interrupt active commands, and never replay interrupted jobs.

## P0 — recovery and connectivity

- [ ] Test server crash, tunnel crash, hung process, network outage, Wi-Fi change, VPN change and suspend/resume. Verify the tunnel reconnects and ChatGPT can execute a fresh command without manual intervention after connectivity returns.
- [ ] Evaluate a lightweight health supervisor for stuck-but-running processes. Use bounded retries/backoff, avoid restart storms and API rate limits, distinguish local server failure from tunnel readiness and remote ChatGPT errors (including HTTP 429), and do not restart healthy processes merely because ChatGPT is temporarily unavailable.
- [ ] Verify Windows power behavior: sleep, hibernation, lid close, AC/battery and wake. Document that the connector cannot execute commands while the host is asleep/off; offer explicit, user-approved power settings for a machine intended to stay available. Never silently disable sleep or assume wake-on-LAN is available.
- [ ] Provide a single diagnostic command showing process/service status, startup registration, authenticated local health, tunnel readiness, last failure and actionable next steps without exposing credentials or command output. Distinguish local readiness from end-to-end ChatGPT availability.

## P1 — Windows Home VM preview

- [ ] Test a clean install on physical Windows Home hardware, including VirtualBox prerequisites, Ubuntu provisioning, guest reboot, service auto-start, tunnel registration and command execution from ChatGPT.
- [ ] Verify Windows logon task, host reboot/logoff, VM shutdown/crash and host sleep/resume. Guest systemd restart does not restart a stopped VM; evaluate a safe host-level recovery mechanism and unattended boot separately.
- [ ] Test update, uninstall, preserve-data and delete-data flows. Confirm no duplicate VMs/tasks and that the default workspace capacity is correct.
- [ ] Track implementation in the VM preview branch/PR; update this checklist when real-device tests pass.

## Acceptance criteria / test matrix

- [ ] Native Windows and native Linux: fresh setup, repeated setup, reboot, logout/login (where supported), crash recovery, network disconnect/reconnect, and explicit stop/uninstall. Windows VM: repeat the applicable host and guest scenarios.
- [ ] After each recovery, `command-mcp check` passes; an ordinary ChatGPT chat can submit a harmless command, poll the result, and receive exit code 0. Verify concurrent commands and no duplicate execution after interrupted jobs.
- [ ] All service listeners remain loopback-only, local authentication remains enforced, keys stay outside Git, and commands run as the configured OS account. No unnecessary inbound ports, privileges, or credential logging.
- [ ] Record OS versions, startup mode, observed recovery time, failure cases and any remaining manual steps. Add automated tests where practical; CI alone does not prove real reboot or sleep behavior.

## References

- [Native Windows](docs/WINDOWS.md)
- [Native Linux](docs/LINUX.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Security](SECURITY.md)
- Windows Home VM preview: `docs/WINDOWS-VM.md` on the preview branch.
