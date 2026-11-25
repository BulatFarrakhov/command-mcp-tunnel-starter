param(
    [Parameter(Mandatory)][ValidateSet('install','start','stop','restart','status','uninstall')][string]$Action,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Repo
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$names = @("CommandMCP-$sid-Server", "CommandMCP-$sid-Tunnel")
$roles = @('serve','tunnel')
$description = 'Managed by command-mcp-tunnel-starter native setup'
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
function Get-OwnedTask([string]$Name) {
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($task -and $task.Description -ne $description) {
        throw "Refusing to manage unrelated task: $Name"
    }
    return $task
}
function Stop-Owned {
    foreach ($name in @($names[1], $names[0])) {
        $task = Get-OwnedTask $name
        if ($task -and $task.State -eq 'Running') { Stop-ScheduledTask -InputObject $task }
    }
}
function Start-Owned {
    foreach ($name in $names) {
        $task = Get-OwnedTask $name
        if (-not $task) { throw "Missing task: $name. Run install." }
        if ($task.State -ne 'Running') { Start-ScheduledTask -InputObject $task }
    }
}
switch ($Action) {
    'install' {
        $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
        for ($i=0; $i -lt $names.Count; $i++) {
            $task = Get-OwnedTask $names[$i]
            $argsString = "-m command_mcp_tunnel_starter $($roles[$i])"
            if ($task) {
                if ($task.Actions.Count -ne 1 -or $task.Actions[0].Execute -ne $Python -or $task.Actions[0].Arguments -ne $argsString -or $task.Actions[0].WorkingDirectory -ne $Repo) {
                    throw "Existing installation uses a different path. Stop/uninstall it explicitly first."
                }
                continue
            }
            $taskAction = New-ScheduledTaskAction -Execute $Python -Argument $argsString -WorkingDirectory $Repo
            Register-ScheduledTask -TaskName $names[$i] -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description $description | Out-Null
        }
        Start-Owned
    }
    'start' { Start-Owned }
    'stop' { Stop-Owned }
    'restart' { Stop-Owned; Start-Owned }
    'status' {
        foreach ($name in $names) {
            $task = Get-OwnedTask $name
            if ($task) {
                $task | Select-Object TaskName,State
                Get-ScheduledTaskInfo -InputObject $task | Select-Object LastRunTime,LastTaskResult,NextRunTime
            } else { Write-Output "Missing task: $name" }
        }
    }
    'uninstall' {
        Stop-Owned
        foreach ($name in $names) {
            $task = Get-OwnedTask $name
            if ($task) { Unregister-ScheduledTask -InputObject $task -Confirm:$false }
        }
    }
}
