# V2 acceptance and verification

This branch implements the native agent-first rewrite. No V1 compatibility or migration. Main and the archived VM experiment remain independent.

## Implemented

- [x] Native Windows and Linux install entrypoints, dependency provisioning, verified pinned tunnel-client binaries, local credential entry and isolated V2 state.
- [x] Idempotent registration of owned OS tasks/services, start/stop/restart/uninstall, bounded restart policy, preservation of private state.
- [x] Explicit unattended options: Linux user linger and Windows password-backed limited boot tasks.
- [x] Local watchdog distinguishes process exit, unresponsive local endpoints and a responsive but unready tunnel; authentication mismatch fails closed.
- [x] Windows Job Object containment for supervisor descendants; Linux service cgroup cleanup.
- [x] JSON diagnostics include local authentication, tunnel readiness, service manager status and available failure codes. No secrets or command output are emitted.
- [x] Unit tests for commands, isolation, supervision, service definitions and diagnostics; local supervised server smoke test.

## Remaining target-machine acceptance

- [ ] On native Windows and Linux, fresh install as intended non-admin account, repeated install, default logon start, reboot, explicit stop/restart, uninstall and reinstall; preserve configuration and job history.
- [ ] Confirm Windows unattended password registration and reboot before login, logout, account/network access, task failure codes and actual Job Object behavior. Confirm Linux linger survives logout/reboot. Verify with user authorization and actual account policies.
- [ ] Kill each real component and simulate local hangs. Check bounded retries and recovery. Disconnect network, change Wi-Fi/VPN, suspend/resume and verify tunnel reconnection without manual restart. Test sleep, hibernation and lid-close behavior without silently changing power policy.
- [ ] Create a dedicated test tunnel and verify a harmless real ChatGPT command after install and each recovery. Test concurrent commands and interrupted-job idempotence. Confirm no public listener, no elevated execution or credential logging.
- [ ] Record OS versions, startup mode, observed recovery times and failures. CI and local loopback checks do not prove physical reboot, actual network recovery or ChatGPT availability.

Do not label this branch production-ready until the target-machine checks pass. VM/macOS work is outside native V2 scope unless the owner explicitly asks for it.
