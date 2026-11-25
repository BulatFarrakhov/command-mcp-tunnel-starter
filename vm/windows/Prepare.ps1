#requires -Version 5.1
<#
.SYNOPSIS
  Download checked prerequisites and launch the Windows Home VM installer.
#>
[CmdletBinding()]
param(
    [ValidateRange(32,2048)][int]$DiskGiB = 200,
    [ValidateRange(2048,131072)][int]$MemoryMiB = 8192,
    [ValidateRange(1,64)][int]$CpuCount = 4,
    [ValidatePattern('^[A-Za-z0-9_-]{1,40}$')][string]$VmName = 'CommandMcpLinux',
    [string]$DataRoot = "$env:LOCALAPPDATA\CommandMcpLinux",
    [switch]$SkipTunnelSetup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# These hashes are from the publishers' SHA256SUMS files. Update as a pair
# with the pinned URLs; never accept a hash downloaded alongside an artifact.
$virtualBoxUrl = 'https://download.virtualbox.org/virtualbox/7.2.18/VirtualBox-7.2.18-175117-Win.exe'
$virtualBoxSha256 = 'aae27200546a21b9b7dc11cfc42bd04802329a29f69ae0ada55682715a389d8d'
$ubuntuUrl = 'https://releases.ubuntu.com/24.04/ubuntu-24.04.5-live-server-amd64.iso'
$ubuntuSha256 = '97f3d7ffb032c3eb3b23d2c8be9cc76e60c2c1f2c0146ba5ba9fe01cafae0fd8'

function Get-CheckedDownload {
    param([string]$Url, [string]$Path, [string]$Sha256)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash -ieq $Sha256) {
            Write-Host "Verified cached download: $([System.IO.Path]::GetFileName($Path))"
            return
        }
        Remove-Item -LiteralPath $Path -Force
    }
    $partial = "$Path.part"
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    Write-Host "Downloading $([System.IO.Path]::GetFileName($Path)) (this can take a while)."
    try {
        try {
            Start-BitsTransfer -Source $Url -Destination $partial -ErrorAction Stop
        } catch {
            if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
            Write-Host 'BITS download unavailable; retrying with HTTPS.'
            Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing -ErrorAction Stop
        }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash -ine $Sha256) {
            throw "Publisher SHA-256 mismatch for $Url"
        }
        Move-Item -LiteralPath $partial -Destination $Path
    } finally {
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    }
}

if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw 'This package currently supports x86-64 Windows only.'
}
if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is required.' }
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$lockfile = Join-Path $sourceRoot 'uv.lock'
if (-not (Test-Path -LiteralPath $lockfile -PathType Leaf)) { throw 'The setup package is incomplete (uv.lock missing).' }
$downloads = Join-Path $DataRoot 'downloads'
New-Item -ItemType Directory -Path $downloads -Force | Out-Null
$virtualBoxInstaller = Join-Path $downloads 'VirtualBox-7.2.18-175117-Win.exe'
$ubuntuIso = Join-Path $downloads 'ubuntu-24.04.5-live-server-amd64.iso'
$vboxManage = "$env:ProgramFiles\Oracle\VirtualBox\VBoxManage.exe"

if (-not (Test-Path -LiteralPath $vboxManage -PathType Leaf)) {
    Get-CheckedDownload -Url $virtualBoxUrl -Path $virtualBoxInstaller -Sha256 $virtualBoxSha256
    Write-Host 'Installing VirtualBox. Windows may request administrator approval.'
    $process = Start-Process -FilePath $virtualBoxInstaller -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-msiparams', 'ADDLOCAL=VBoxApplication', '/qn', '/norestart'
    )
    if ($process.ExitCode -notin @(0, 3010)) { throw "VirtualBox installer exited $($process.ExitCode)" }
    if ($process.ExitCode -eq 3010) {
        throw 'VirtualBox requires a Windows restart. Restart, then run Setup.cmd again; downloads will be reused.'
    }
    if (-not (Test-Path -LiteralPath $vboxManage -PathType Leaf)) {
        throw 'VirtualBox installation needs a Windows restart. Restart, then run Setup.cmd again; downloads will be reused.'
    }
}
$version = (& $vboxManage --version) -join ''
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^7\.2\.') {
    throw "VirtualBox 7.2 is required. Found: $version. Update VirtualBox, then run Setup.cmd again."
}

& $vboxManage showvminfo $VmName --machinereadable *> $null
if ($LASTEXITCODE -eq 0) { throw "VM $VmName already exists. Use Manage.ps1 or the installed app entry to manage it." }
Get-CheckedDownload -Url $ubuntuUrl -Path $ubuntuIso -Sha256 $ubuntuSha256

# Keep the installed scripts outside Downloads so Add/Remove Programs keeps an
# uninstaller even after the downloaded ZIP has been deleted.
$packageRoot = Join-Path $DataRoot 'package'
if ([System.IO.Path]::GetFullPath($sourceRoot).TrimEnd('\') -ine [System.IO.Path]::GetFullPath($packageRoot).TrimEnd('\')) {
    if (Test-Path -LiteralPath $packageRoot) { Remove-Item -LiteralPath $packageRoot -Recurse -Force }
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    foreach ($name in @('pyproject.toml','uv.lock','README.md','SECURITY.md','src','vm')) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $name) -Destination (Join-Path $packageRoot $name) -Recurse -Force
    }
}
$installer = Join-Path $packageRoot 'vm\windows\Install.ps1'
& $installer -UbuntuIso $ubuntuIso -UbuntuIsoSha256 $ubuntuSha256 -DiskGiB $DiskGiB `
    -MemoryMiB $MemoryMiB -CpuCount $CpuCount -VmName $VmName -VBoxManage $vboxManage `
    -DataRoot $DataRoot -SkipTunnelSetup:$SkipTunnelSetup
if (-not $?) { throw 'VM installation did not complete.' }
