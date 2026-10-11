# Windows Home Linux VM (developer preview)

This is the Windows Home path for [task #249](https://github.com/BulatFarrakhov/codex-tasks/issues/249). It creates an Ubuntu Linux VM in VirtualBox and runs the existing command-only MCP server and Secure MCP Tunnel inside it. Commands run as `agent` in the VM; `/workspace` is the default working directory. The `agent` account has passwordless sudo **inside the VM**.

The current release is a PowerShell installer, not an EXE. It requires VirtualBox 7.2 on an x86-64 Windows 10/11 Home host, an Ubuntu Server 24.04 LTS x86-64 ISO, and the ISO's SHA-256 from Ubuntu's official checksum file. Hardware virtualization must be enabled in firmware. The installer checks the ISO hash before creating a VM. VirtualBox's unattended Ubuntu installation and Guest Additions must work on the target PC; this path has not yet been exercised on a Windows Home machine.

Get VirtualBox from [Oracle](https://www.virtualbox.org/wiki/Downloads) and Ubuntu Server from [Ubuntu](https://ubuntu.com/download/server). This preview does not install those prerequisites automatically. Keep the ISO and checksum as a matched pair. Obtain a new Secure MCP Tunnel ID and a runtime API key with Tunnels Read + Use from [OpenAI Platform](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels). Associate the tunnel with the ChatGPT workspace that will use the plugin. Enter the runtime key only at the installer’s hidden local prompt; never put it in a command argument, issue, or repo file.

From a complete checkout, in PowerShell as your ordinary Windows account:

```powershell
Set-Location C:\path\to\command-mcp-tunnel-starter
.\vm\windows\Install.ps1 -UbuntuIso 'C:\path\to\ubuntu-24.04.x-live-server-amd64.iso' -UbuntuIsoSha256 '64-character-SHA256' -DiskGiB 200 -MemoryMiB 8192 -CpuCount 4
```

The installer asks for a Linux login password, tunnel ID, and runtime key. It provisions the VM, installs the bundled repo source and locked Python dependencies in the guest, starts the services, and registers a Windows **logon** task to start the VM after you sign in. Ubuntu updates, `uv`, and the pinned tunnel client are downloaded during guest provisioning and verified as described in the guest bootstrap script. Installation may take 20–45 minutes. The default disk is **200 GiB maximum**, dynamically allocated: it grows as used and does not reserve 200 GiB immediately. The guest OS, tools, and workspace all count toward that capacity. VM logs and VirtualBox metadata use some additional Windows disk space. The installer checks for 15 GiB free before starting; you need more as the disk grows.

After installation:

```powershell
.\vm\windows\Manage.ps1 -Action Status
.\vm\windows\Manage.ps1 -Action Stop
.\vm\windows\Manage.ps1 -Action Start
```

Connect the tunnel as a custom MCP plugin in ordinary ChatGPT, then start a new chat and confirm the three tools: `start_command`, `get_command`, `cancel_command`. Start with `pwd` and verify that it returns `/workspace`. See the [main connection guide](../README.md#setup-map). A new tunnel/plugin is recommended for the VM; do not reuse a VPS tunnel ID that is currently connected to another machine.

To remove the integration while retaining the VM disk:

```powershell
.\vm\windows\Manage.ps1 -Action Uninstall
```

To delete the registered VM and its VirtualBox files, including the Linux workspace:

```powershell
.\vm\windows\Manage.ps1 -Action Uninstall -DeleteData
```

Uninstalling this package does **not** uninstall the separately installed VirtualBox application or revoke the OpenAI runtime key. Revoke the key and remove the ChatGPT plugin/tunnel separately if retiring access.

## What the VM does and does not enforce

The installer uses NAT with no inbound port forwarding and disables VirtualBox shared folders, clipboard, drag-and-drop, USB controllers, and guest access to the host's localhost via VirtualBox NAT. It does not attach Windows disks. The default `/workspace/AGENTS.md` and MCP instructions tell the agent to work in Linux and avoid Windows resources. Those instructions are **advisory**: an arbitrary Bash tool cannot enforce them. The guest may still reach Windows or LAN services over their network addresses if those services accept connections. Do not treat this preview as an internet-only network sandbox. VirtualBox itself and Windows host networking need separate hardening for stronger isolation.

The installer briefly stages a guest password and runtime config in a private Windows directory under `%LOCALAPPDATA%\CommandMcpLinux`, then removes the staging directory. The runtime key remains in the guest config, readable by the `agent` account that runs commands. An agent with arbitrary guest commands can read that key; use a dedicated tunnel key. VM backups and snapshots also contain it.

The VM starts at Windows logon, not before login. If Windows is shut down or the user has not logged on after reboot, the tunnel is offline. `Manage.ps1` can start or stop it manually. The Linux services restart inside the running VM.
