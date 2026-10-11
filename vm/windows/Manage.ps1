#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Start','Stop','Status','Uninstall')][string]$Action,
    [ValidatePattern('^[A-Za-z0-9_-]{1,40}$')][string]$VmName = 'CommandMcpLinux',
    [string]$VBoxManage = "$env:ProgramFiles\Oracle\VirtualBox\VBoxManage.exe",
    [switch]$DeleteData,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $VBoxManage -PathType Leaf)) { throw "VBoxManage missing: $VBoxManage" }
$info = & $VBoxManage showvminfo $VmName --machinereadable 2>$null
if ($LASTEXITCODE -ne 0) { throw "VM $VmName is not registered" }
$stateLine = $info | Where-Object { $_ -match '^VMState=' } | Select-Object -First 1
$state = if ($stateLine) { ($stateLine -split '=',2)[1].Trim('"') } else { 'unknown' }

switch ($Action) {
    'Status' {
        Write-Host "VM: $VmName  State: $state"
        $info | Where-Object { $_ -match '^(nic1|nat-localhostreachable1|clipboard|draganddrop|usb|SATA-0-0|CfgFile)=' }
    }
    'Start' {
        if ($state -eq 'running') { Write-Host 'VM already running'; break }
        & $VBoxManage startvm $VmName --type headless
        if ($LASTEXITCODE -ne 0) { throw 'Could not start VM' }
    }
    'Stop' {
        if ($state -ne 'running') { Write-Host "VM is $state"; break }
        if ($Force) { & $VBoxManage controlvm $VmName poweroff }
        else { & $VBoxManage controlvm $VmName acpipowerbutton }
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop VM' }
    }
    'Uninstall' {
        $taskName = "CommandMcpLinux-$VmName"
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        if ($state -eq 'running') {
            if ($Force) { & $VBoxManage controlvm $VmName poweroff }
            else { & $VBoxManage controlvm $VmName acpipowerbutton }
            if ($LASTEXITCODE -ne 0) { throw 'Could not request guest shutdown' }
            $deadline = (Get-Date).AddMinutes(3)
            do {
                Start-Sleep -Seconds 3
                $check = & $VBoxManage showvminfo $VmName --machinereadable
                $isOff = ($check | Where-Object { $_ -match '^VMState="poweroff"$' }).Count -gt 0
            } until ($isOff -or (Get-Date) -ge $deadline)
            if (-not $isOff) { throw 'Guest did not shut down. Retry Uninstall -Force to power it off.' }
        }
        if ($DeleteData) { & $VBoxManage unregistervm $VmName --delete }
        else { & $VBoxManage unregistervm $VmName }
        if ($LASTEXITCODE -ne 0) { throw 'Could not unregister VM' }
        if ($DeleteData) { Write-Host "Unregistered VM and deleted its VirtualBox files: $VmName" }
        else { Write-Host "Unregistered VM; its virtual disk and data were retained: $VmName" }
    }
}
