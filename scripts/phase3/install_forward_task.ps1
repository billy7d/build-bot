[CmdletBinding()]
param(
    [string]$RuntimeConfig = 'E:\build-bot-runtime\phase3\config\forward.json',
    [string]$TaskName = 'BuildBot-Phase3-Forward',
    [switch]$Start
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-ConfiguredPath([string]$Value, [string]$BasePath) {
    $candidate = [System.IO.Path]::GetFullPath(
        $(if ([System.IO.Path]::IsPathRooted($Value)) { $Value } else { Join-Path $BasePath $Value })
    )
    return $candidate
}

$configPath = (Resolve-Path -LiteralPath $RuntimeConfig).Path
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$config.schema -ne 'phase3-forward-runtime/1') {
    throw 'Runtime config không đúng schema Phase 3.1.'
}
if ([string]$config.execution_mode -ne 'NONE' -or [bool]$config.live_execution_enabled) {
    throw 'Runtime config không được bật execution.'
}

$repoPath = Resolve-ConfiguredPath ([string]$config.repo_path) (Split-Path -Parent $configPath)
$runnerPath = Join-Path $repoPath 'scripts\phase3\run_forward_collector.ps1'
if (-not (Test-Path -LiteralPath $runnerPath -PathType Leaf)) {
    throw "Không tìm thấy collector runner: $runnerPath"
}

$powerShellPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$runnerArguments = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$runnerPath`" -RuntimeConfig `"$configPath`""
$action = New-ScheduledTaskAction -Execute $powerShellPath -Argument $runnerArguments -WorkingDirectory $repoPath
$userId = if ($env:USERDOMAIN) { "$($env:USERDOMAIN)\$($env:USERNAME)" } else { $env:USERNAME }
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType InteractiveToken -RunLevel Limited

# Register-ScheduledTask -Force giúp chạy lại script mà không tạo task trùng.
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$registered = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
if ($Start) {
    Enable-ScheduledTask -TaskName $TaskName | Out-Null
    Start-ScheduledTask -TaskName $TaskName
} else {
    # Install mặc định chỉ tạo task ở trạng thái disabled/stopped.
    Disable-ScheduledTask -TaskName $TaskName | Out-Null
    if ([string]$registered.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $TaskName
    }
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    status = 'TASK_INSTALLED'
    task_name = $TaskName
    task_state = [string](Get-ScheduledTask -TaskName $TaskName).State
    last_run_time = $info.LastRunTime
    next_run_time = $info.NextRunTime
    runtime_config = $configPath
    runner = $runnerPath
    execution_mode = 'NONE'
    live_execution_enabled = $false
} | ConvertTo-Json -Depth 5
