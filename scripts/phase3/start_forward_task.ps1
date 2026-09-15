[CmdletBinding()]
param(
    [string]$TaskName = 'BuildBot-Phase3-Forward'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Enable-ScheduledTask -TaskName $TaskName | Out-Null
Start-ScheduledTask -TaskName $TaskName
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
[pscustomobject]@{
    status = 'TASK_START_REQUESTED'
    task_name = $TaskName
    task_state = [string]$task.State
} | ConvertTo-Json -Depth 4
