param(
    [Parameter(Mandatory)][ValidateSet('install','start','stop','restart','status','diagnostics','uninstall')][string]$Action,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Repo,
    [switch]$Unattended
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$names = @("CommandMCP-V2-$sid-Server", "CommandMCP-V2-$sid-Tunnel")
$roles = @('serve','tunnel')
$description = 'Managed by command-mcp-tunnel-starter V2 native setup'
function Get-OwnedTask([string]$Name) {
    $task = Get-ScheduledTask -TaskPath "\" -TaskName $Name -ErrorAction SilentlyContinue
    if ($task -and $task.Description -ne $description) {
        throw "Refusing to manage unrelated task: $Name"
    }
    if ($task) {
        $index = [array]::IndexOf($names, $Name)
        $expected = "-m command_mcp_tunnel_starter.supervisor $($roles[$index])"
        if ($task.Actions.Count -ne 1 -or $task.Actions[0].Execute -ne $Python -or $task.Actions[0].Arguments -ne $expected -or $task.Actions[0].WorkingDirectory -ne $Repo) {
            throw "Refusing to manage task from a different checkout or configuration: $Name"
        }
    }
    return $task
}
function Stop-Owned {
    foreach ($name in @($names[1], $names[0])) {
        $task = Get-OwnedTask $name
        if ($task -and $task.State -eq 'Running') {
            Stop-ScheduledTask -InputObject $task
            $deadline = (Get-Date).AddSeconds(30)
            do {
                Start-Sleep -Milliseconds 250
                $task = Get-OwnedTask $name
            } while ($task -and $task.State -eq 'Running' -and (Get-Date) -lt $deadline)
            if ($task -and $task.State -eq 'Running') { throw "Timed out stopping task: $name" }
        }
    }
}
function Start-Owned {
    foreach ($name in $names) {
        $task = Get-OwnedTask $name
        if (-not $task) { throw "Missing task: $name. Run install." }
        if ($task.State -ne 'Running') { Start-ScheduledTask -InputObject $task }
    }
}
if ($Action -ne 'diagnostics' -and $Action -ne 'status') {
    foreach ($name in $names) { $null = Get-OwnedTask $name }
}
switch ($Action) {
    'install' {
        $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
        # Only a real, locally supplied password can support password-backed boot startup.
        # Never run as SYSTEM or use a stored password outside Task Scheduler.
        $expectedLogon = if ($Unattended) { 'Password' } else { 'Interactive' }
        $existingTasks = @($names | ForEach-Object { Get-OwnedTask $_ } | Where-Object { $null -ne $_ })
        foreach ($task in $existingTasks) {
            if ($task -and $task.Principal.LogonType.ToString() -ne $expectedLogon) {
                throw 'Existing V2 task uses a different startup mode. Uninstall it explicitly before switching.'
            }
        }
        $password = $null
        $bstr = [IntPtr]::Zero
        if ($Unattended -and $existingTasks.Count -lt $names.Count) {
            $secret = Read-Host 'Windows account password for Task Scheduler (not your PIN)' -AsSecureString
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
            try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr); $secret.Dispose() }
            if (-not $password) { throw 'A real account password is required.' }
        }
        try {
        $settings = New-ScheduledTaskSettingsSet -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        $trigger = @(New-ScheduledTaskTrigger -AtLogOn -User $identity)
        if ($Unattended) { $trigger += New-ScheduledTaskTrigger -AtStartup }
        for ($i=0; $i -lt $names.Count; $i++) {
            $task = Get-OwnedTask $names[$i]
            $argsString = "-m command_mcp_tunnel_starter.supervisor $($roles[$i])"
            if ($task) {
                if ($task.Actions.Count -ne 1 -or $task.Actions[0].Execute -ne $Python -or $task.Actions[0].Arguments -ne $argsString -or $task.Actions[0].WorkingDirectory -ne $Repo) {
                    throw "Existing installation uses a different path. Stop/uninstall it explicitly first."
                }
                continue
            }
            $taskAction = New-ScheduledTaskAction -Execute $Python -Argument $argsString -WorkingDirectory $Repo
            if ($Unattended) {
                Register-ScheduledTask -TaskPath "\" -TaskName $names[$i] -Action $taskAction -Trigger $trigger -User $identity -Password $password -RunLevel Limited -Settings $settings -Description $description | Out-Null
            } else {
                Register-ScheduledTask -TaskPath "\" -TaskName $names[$i] -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description $description | Out-Null
            }
        }
        Start-Owned
        } finally { $password = $null }
    }
    'start' { Start-Owned }
    'stop' { Stop-Owned }
    'restart' { Stop-Owned; Start-Owned }
    'diagnostics' {
        $rows = @()
        for ($i=0; $i -lt $names.Count; $i++) {
            $task = Get-ScheduledTask -TaskPath "\" -TaskName $names[$i] -ErrorAction SilentlyContinue
            if (-not $task) {
                $rows += @{ role = $roles[$i]; state = 'missing'; owned = $false }
                continue
            }
            $owned = $task.Description -eq $description
            if (-not $owned) {
                $rows += @{ role = $roles[$i]; state = 'foreign'; owned = $false }
                continue
            }
            $info = Get-ScheduledTaskInfo -InputObject $task
            $boot = @($task.Triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskBootTrigger' }).Count -gt 0
            $rows += @{ role = $roles[$i]; state = $task.State.ToString(); owned = $true
                        enabled = [bool]$task.Settings.Enabled; logon_type = $task.Principal.LogonType.ToString()
                        last_result = $info.LastTaskResult; boot_trigger = $boot }
        }
        ConvertTo-Json -InputObject @($rows) -Compress -Depth 3
    }
    'status' { throw 'Use diagnostics for safe machine-readable status.' }
    'uninstall' {
        Stop-Owned
        foreach ($name in $names) {
            $task = Get-OwnedTask $name
            if ($task) { Unregister-ScheduledTask -InputObject $task -Confirm:$false }
        }
    }
}
