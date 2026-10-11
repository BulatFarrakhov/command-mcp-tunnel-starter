#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9_-]{1,40}$')][string]$VmName = 'CommandMcpLinux',
    [string]$DataRoot = "$env:LOCALAPPDATA\CommandMcpLinux",
    [switch]$DeleteData,
    [switch]$NoPrompt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $DeleteData -and -not $NoPrompt) {
    $answer = Read-Host 'Delete the Linux VM disk and workspace too? Type DELETE to confirm, or press Enter to keep them'
    $DeleteData = $answer -ceq 'DELETE'
}
$manager = Join-Path $PSScriptRoot 'Manage.ps1'
& $manager -Action Uninstall -VmName $VmName -DeleteData:$DeleteData
if (-not $?) { throw 'VirtualBox VM removal did not complete.' }
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CommandMcpLinux-$VmName"
if (Test-Path -LiteralPath $uninstallKey) { Remove-Item -LiteralPath $uninstallKey -Force }
foreach ($directory in @((Join-Path $DataRoot 'downloads'), (Join-Path $DataRoot 'package'))) {
    if (Test-Path -LiteralPath $directory) { Remove-Item -LiteralPath $directory -Recurse -Force }
}
Write-Host 'Command MCP Linux VM uninstalled. VirtualBox remains installed for any other VMs.'
if (-not $DeleteData) { Write-Host "VM disk retained under $DataRoot\machines" }
