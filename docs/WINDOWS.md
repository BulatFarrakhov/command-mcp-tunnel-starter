# Native Windows setup

Run these steps in PowerShell as the **non-admin account that should execute ChatGPT commands**. Windows commands run under `powershell.exe -NoProfile -NonInteractive -Command`, not WSL or Bash. Read [SECURITY.md](../SECURITY.md) first.

## 1. Install prerequisites

Install [Git for Windows](https://git-scm.com/download/win) and [`uv`](https://docs.astral.sh/uv/getting-started/installation/). The official `uv` PowerShell installer is:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv python install 3.12
```

Restart PowerShell if `uv` is not yet on `PATH`. Download the **full `tunnel-client` release** for your Windows architecture from [openai/tunnel-client releases](https://github.com/openai/tunnel-client/releases/latest). Choose the matching Windows archive, verify the zip's SHA-256 against `SHA256SUMS.txt` using `Get-FileHash`, extract `tunnel-client.exe` to a directory owned by the execution account, and note its absolute path. Test `& 'C:\path\to\tunnel-client.exe' help quickstart`.

Create a new tunnel in OpenAI Platform using the [official Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels). Associate the intended Platform organization and ChatGPT workspace. Obtain a runtime API key with Tunnels Read + Use. Keep it in a password manager until the local hidden `init` prompt asks for it.

## 2. Install this private repo

```powershell
git clone git@github.com:BulatFarrakhov/command-mcp-tunnel-starter.git
Set-Location command-mcp-tunnel-starter
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen command-mcp init
```

At `init`, enter the tunnel ID, key, absolute path to `tunnel-client.exe`, and existing absolute default working directory. Config is written to `$env:APPDATA\command-mcp-v2\config.json`; runtime state is under `$env:LOCALAPPDATA\command-mcp-v2`. `init` removes inherited ACLs from the config and grants the current account access. Inspect with:

```powershell
icacls "$env:APPDATA\command-mcp-v2\config.json"
```

Make sure no unintended account can read it. Do not place the config, logs, or state in Git or a broadly synced/shared directory. If policy forbids local secret files, adapt the launcher to your approved secret store before deployment.

## 3. Prove the interactive setup

Open three PowerShell windows in the repository. In window A run `uv run --frozen --no-sync command-mcp serve`. In window B run `uv run --frozen --no-sync command-mcp tunnel`. In window C run:

```powershell
uv run --frozen --no-sync command-mcp check
Get-NetTCPConnection -LocalPort 18202,18203 | Select-Object LocalAddress,LocalPort,State
```

Both listeners must have local address `127.0.0.1`. The server must reject an unauthenticated request:

```powershell
try { Invoke-WebRequest http://127.0.0.1:18202/healthz } catch { $_.Exception.Response.StatusCode.value__ }
```

Expected status: 401. No Windows Defender Firewall inbound rule is needed; the tunnel makes outbound HTTPS connections.

## 4. Start at logon

For a personal workstation, use Task Scheduler to create **two tasks** under the intended account, triggered **At log on** for that account:

| Task | Program/script | Arguments | Start in |
| --- | --- | --- | --- |
| Command MCP server | Absolute path from `(Get-Command uv).Source` | `run --frozen --no-sync command-mcp serve` | Absolute repo path |
| Command MCP tunnel | Same `uv.exe` | `run --frozen --no-sync command-mcp tunnel` | Same repo path |

Set **Run only when user is logged on**, leave **Run with highest privileges** unchecked, configure restart on failure, and prevent a second instance. Start the server task first and the tunnel task second. The tunnel retries after startup failure if Task Scheduler is configured to restart it. Reboot, log in, run `command-mcp check`, and inspect the two task histories. This logon setup stops working when the account is logged out.

If it must run while logged out, ask the user to provide a dedicated non-admin service account and an approved password-backed Task Scheduler or Windows service setup. Avoid `SYSTEM` and avoid S4U tasks when network credentials are needed. Test after actual logoff and reboot, not only in an interactive shell.

Finish setup in ChatGPT using the [README](../README.md#setup-map). If it sees an older schema after changes, Refresh the custom MCP server connection and start a new chat.
