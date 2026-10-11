#requires -Version 5.1
<#
.SYNOPSIS
  Creates the command-only Linux VM on Windows Home using Oracle VirtualBox.
.NOTES
  Run from a release checkout with VirtualBox installed and a verified Ubuntu Server ISO.
  The installer never puts either secret in a process command line.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$UbuntuIso,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$UbuntuIsoSha256,
    [ValidateRange(32,2048)][int]$DiskGiB = 200,
    [ValidateRange(2048,131072)][int]$MemoryMiB = 8192,
    [ValidateRange(1,64)][int]$CpuCount = 4,
    [ValidatePattern('^[A-Za-z0-9_-]{1,40}$')][string]$VmName = 'CommandMcpLinux',
    [string]$VBoxManage = "$env:ProgramFiles\Oracle\VirtualBox\VBoxManage.exe",
    [string]$DataRoot = "$env:LOCALAPPDATA\CommandMcpLinux",
    [switch]$SkipTunnelSetup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-VBox {
    param([string[]]$Arguments)
    & $VBoxManage @Arguments
    if ($LASTEXITCODE -ne 0) { throw "VBoxManage failed (exit $LASTEXITCODE): $($Arguments[0])" }
}

function Protect-LocalPath {
    param([string]$Path)
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path /inheritance:r /grant:r "${identity}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict permissions on $Path" }
}

function Read-PrivateText {
    param([string]$Prompt)
    $secure = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Write-PrivateFile {
    param([string]$Path, [string]$Value)
    [System.IO.File]::WriteAllText($Path, $Value, [System.Text.UTF8Encoding]::new($false))
    Protect-LocalPath $Path
}

function Invoke-Guest {
    param([string[]]$Arguments)
    Invoke-VBox -Arguments (@('guestcontrol', $VmName, $Arguments[0], '--username=agent', "--passwordfile=$guestPasswordFile") + $Arguments[1..($Arguments.Length - 1)])
}

if (-not (Test-Path -LiteralPath $VBoxManage -PathType Leaf)) { throw "Install VirtualBox first; VBoxManage missing: $VBoxManage" }
if (-not (Test-Path -LiteralPath $UbuntuIso -PathType Leaf)) { throw "Ubuntu ISO missing: $UbuntuIso" }
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $UbuntuIso).Hash
if ($actualHash -ine $UbuntuIsoSha256) { throw 'Ubuntu ISO SHA-256 mismatch' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\uv.lock'))) { throw 'Run this script from a complete release checkout' }
$rootPath = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($DataRoot))
$freeBytes = (Get-PSDrive -Name $rootPath.Substring(0,1)).Free
if ($freeBytes -lt 15GB) { throw 'At least 15 GiB free space is needed before creating the dynamic VM disk' }

& $VBoxManage showvminfo $VmName --machinereadable *> $null
if ($LASTEXITCODE -eq 0) { throw "A VM named $VmName already exists. Refusing to overwrite it." }

$guestPassword = Read-PrivateText 'Choose a Linux agent login password'
if ([string]::IsNullOrWhiteSpace($guestPassword)) { throw 'Linux password cannot be empty' }
$tunnelId = $null
$runtimeKey = $null
if (-not $SkipTunnelSetup) {
    $tunnelId = (Read-Host 'Tunnel ID (tunnel_...)').Trim()
    if ($tunnelId -notmatch '^tunnel_[0-9a-f]{32}$') { throw 'Invalid tunnel ID' }
    $runtimeKey = Read-PrivateText 'Runtime API key'
    if ($runtimeKey.Length -lt 20) { throw 'Runtime API key is too short' }
}

New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
Protect-LocalPath $DataRoot
$stage = Join-Path $DataRoot ('stage-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
Protect-LocalPath $stage
$guestPasswordFile = Join-Path $stage 'guest-password.txt'
$created = $false
try {
    Write-PrivateFile $guestPasswordFile $guestPassword
    $guestPassword = $null
    $vmFolder = Join-Path $DataRoot 'machines'
    New-Item -ItemType Directory -Path $vmFolder -Force | Out-Null
    Invoke-VBox -Arguments @('createvm', "--name=$VmName", '--ostype=Ubuntu_64', "--basefolder=$vmFolder", '--register')
    $created = $true
    $disk = Join-Path $vmFolder "$VmName\system.vdi"
    Invoke-VBox -Arguments @('modifyvm', $VmName, "--memory=$MemoryMiB", "--cpus=$CpuCount", '--ioapic=on', '--nic1=nat',
        '--nat-localhostreachable1=off', '--nic2=none', '--nic3=none', '--nic4=none',
        '--clipboard-mode=disabled', '--clipboard-file-transfers=disabled', '--drag-and-drop=disabled',
        '--usb-ohci=off', '--usb-ehci=off', '--usb-xhci=off', '--audio-enabled=off', '--boot1=disk', '--boot2=dvd')
    Invoke-VBox -Arguments @('createmedium', 'disk', "--filename=$disk", "--size=$($DiskGiB * 1024)", '--format=VDI', '--variant=Standard')
    Invoke-VBox -Arguments @('storagectl', $VmName, '--name=SATA', '--add=sata', '--controller=IntelAhci')
    Invoke-VBox -Arguments @('storageattach', $VmName, '--storagectl=SATA', '--port=0', '--device=0', '--type=hdd', "--medium=$disk")
    $aux = Join-Path $stage 'unattended'
    Invoke-VBox -Arguments @('unattended', 'install', $VmName, "--iso=$UbuntuIso", '--user=agent',
        "--user-password-file=$guestPasswordFile", "--admin-password-file=$guestPasswordFile",
        '--full-user-name=Command MCP Agent', '--hostname=command-mcp-linux', '--install-additions',
        "--post-install-command=printf 'agent ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/90-command-mcp-agent && chmod 0440 /etc/sudoers.d/90-command-mcp-agent",
        "--auxiliary-base-path=$aux", '--start-vm=headless')

    Write-Host 'Installing Ubuntu. This can take 20-45 minutes.'
    $deadline = (Get-Date).AddMinutes(60)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 15
        & $VBoxManage guestcontrol $VmName run --exe=/usr/bin/id --username=agent "--passwordfile=$guestPasswordFile" --timeout=30000 -- -u *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    }
    if (-not $ready) { throw 'Guest did not become available through VirtualBox Guest Additions. Inspect VM console.' }
    & $VBoxManage guestcontrol $VmName run --exe=/usr/bin/sudo --username=agent "--passwordfile=$guestPasswordFile" --timeout=30000 -- -n true *> $null
    if ($LASTEXITCODE -ne 0) {
        # Some Ubuntu unattended versions skip the post-install hook. Try the
        # root login configured with the same private password file.
        & $VBoxManage guestcontrol $VmName run --exe=/bin/sh --username=root "--passwordfile=$guestPasswordFile" --timeout=30000 -- -c "printf 'agent ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/90-command-mcp-agent && chmod 0440 /etc/sudoers.d/90-command-mcp-agent" *> $null
        if ($LASTEXITCODE -ne 0) { throw 'Could not configure guest sudo through unattended hook or root guest control. Inspect the VM console.' }
        & $VBoxManage guestcontrol $VmName run --exe=/usr/bin/sudo --username=agent "--passwordfile=$guestPasswordFile" --timeout=30000 -- -n true *> $null
        if ($LASTEXITCODE -ne 0) { throw 'Guest agent still lacks passwordless sudo after provisioning.' }
    }

    # Compress only application source; no .git directory, host secrets, or build state.
    $sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    $bundle = Join-Path $stage 'command-mcp.zip'
    $files = @('pyproject.toml', 'uv.lock', 'README.md', 'SECURITY.md', 'src', 'vm') |
        ForEach-Object { Join-Path $sourceRoot $_ }
    Compress-Archive -Path $files -DestinationPath $bundle -CompressionLevel Optimal
    Invoke-Guest -Arguments @('copyto', $bundle, '/home/agent/command-mcp.zip')
    Invoke-Guest -Arguments @('run', '--exe=/usr/bin/python3', '--timeout=120000', '--', '-m', 'zipfile', '-e',
        '/home/agent/command-mcp.zip', '/home/agent/command-mcp-tunnel-starter')

    if (-not $SkipTunnelSetup) {
        $tokenBytes = [byte[]]::new(48)
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($tokenBytes) } finally { $rng.Dispose() }
        $config = [ordered]@{
            tunnel_id = $tunnelId; runtime_api_key = $runtimeKey
            tunnel_client_path = '/home/agent/.local/bin/tunnel-client'
            inbound_token = [Convert]::ToBase64String($tokenBytes)
            default_cwd = '/workspace'; state_dir = '/home/agent/.local/state/command-mcp-tunnel'
            server_port = 18102; tunnel_health_port = 18103; max_concurrent_commands = 4
            max_output_bytes = 31457280; max_timeout_seconds = 86400
            workspace_policy = 'This service runs inside a Linux VM. Work in /workspace. Do not mount, inspect, or modify Windows host disks, shares, or services.'
        }
        $privateConfig = Join-Path $stage 'config.json'
        Write-PrivateFile $privateConfig ($config | ConvertTo-Json -Depth 3)
        $runtimeKey = $null
        Invoke-Guest -Arguments @('mkdir', '--parents', '/home/agent/.config/command-mcp-tunnel')
        Invoke-Guest -Arguments @('copyto', $privateConfig, '/home/agent/.config/command-mcp-tunnel/config.json')
        Invoke-Guest -Arguments @('run', '--exe=/bin/chmod', '--', '700', '/home/agent/.config/command-mcp-tunnel')
        Invoke-Guest -Arguments @('run', '--exe=/bin/chmod', '--', '600', '/home/agent/.config/command-mcp-tunnel/config.json')
    }
    Invoke-Guest -Arguments @('run', '--exe=/bin/bash', '--timeout=1800000', '--wait-stdout', '--wait-stderr', '--',
        '/home/agent/command-mcp-tunnel-starter/vm/guest/bootstrap.sh')
    $taskName = "CommandMcpLinux-$VmName"
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $taskAction = New-ScheduledTaskAction -Execute $VBoxManage -Argument "startvm `"$VmName`" --type headless"
    $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Description 'Start private command MCP Linux VM at logon' -Force | Out-Null
    Write-Host "VM $VmName installed. Check with: .\Manage.ps1 -Action Status -VmName $VmName"
} catch {
    if ($created) { Write-Warning "VM $VmName was created and retained for inspection. Remove it with Manage.ps1 -Action Uninstall -DeleteData after reviewing the failure." }
    throw
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    $runtimeKey = $null
    $guestPassword = $null
}
