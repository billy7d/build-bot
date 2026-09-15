[CmdletBinding()]
param(
    [string]$TaskName = 'BuildBot-Phase3-Forward'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    if ([string]$task.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $TaskName
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

[pscustomobject]@{
    status = 'TASK_UNINSTALLED'
    task_name = $TaskName
    task_present = $false
    mt5_touched = $false
} | ConvertTo-Json -Depth 4
