# V2: agent-operated installation rewrite

## Development agreement

This branch is an independent development workspace. Iterate here and push commits directly; do not open a pull request or merge into main until the owner explicitly approves the finished design. Main remains the existing stable reference. The previous VM experiment is archived separately.

## Product direction

Build a fresh, runnable installation product for agents operating on the target computer. The agent should inspect the host, select and run the appropriate files, and adapt them when necessary. The human should only handle account authorization, local credential entry and explicit decisions about privileges, persistence and power settings. No GUI installer is required.

- Native Windows and Linux first. Treat macOS and an isolated VM as separate later decisions.
- No backward compatibility obligation: redesign the CLI, configuration schema, internal implementation, layout, service identifiers and tool contracts where justified. Avoid migration layers, legacy flags and compatibility shims. Existing code may be reused if it is the best implementation, not merely for compatibility.
- Develop against clean installations. Use isolated test configuration and service identities to avoid disturbing existing installations. Never delete or overwrite legacy credentials, state, services or user data without explicit authorization. Upgrades within V2 should preserve V2 user data safely.
- Make setup, status, diagnostics, start, stop, restart and uninstall executable and predictable. Automate dependency acquisition where practical; verify downloaded artifacts. Do not require agents to reconstruct service definitions or copy commands from a guide.
- Preserve core security properties: least privilege, loopback-only local server, outbound secure tunnel, local credential entry, private storage, no silent changes to power policy, and no replay of interrupted commands.
- Verify actual end-to-end command execution in ChatGPT and recovery across supported reboot, network and sleep scenarios before claiming readiness. Document unsupported modes and honest limitations.

## Milestones

1. Define V2 architecture, installation flow, OS service ownership and clean-install contract. Review or replace the initial prototype on this branch.
2. Implement and test native installers, service lifecycle, health reporting and bounded recovery.
3. Run fresh-machine acceptance tests on Windows and Linux, including real tunnel and ChatGPT connectivity. Resolve blockers and simplify agent instructions.
4. Owner reviews the finished experience; only then open a PR or release.

See TODO.md for the reliability test matrix. This document takes precedence over inherited implementation details during the rewrite.
