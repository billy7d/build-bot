[CmdletBinding()]
param(
    [string]$RuntimeConfig = 'E:\build-bot-runtime\phase3\config\forward.json',
    [string]$TaskName = 'BuildBot-Phase3-Forward'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$taskInfo = if ($null -ne $task) { Get-ScheduledTaskInfo -TaskName $TaskName } else { $null }
$runtimeStatus = $null
if (Test-Path -LiteralPath $RuntimeConfig -PathType Leaf) {
    $config = Get-Content -LiteralPath $RuntimeConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $repoPath = [System.IO.Path]::GetFullPath([string]$config.repo_path)
    $pythonPath = [string]$config.python_path
    if (-not [System.IO.Path]::IsPathRooted($pythonPath)) {
        $pythonPath = Join-Path $repoPath $pythonPath
    }
    Push-Location $repoPath
    try {
        $statusOutput = & $pythonPath -m agent.phase3 status-runtime --runtime-config ((Resolve-Path -LiteralPath $RuntimeConfig).Path) --json 2>&1
        if ($LASTEXITCODE -eq 0) {
            $runtimeStatus = ($statusOutput -join "`n") | ConvertFrom-Json
        }
    } finally {
        Pop-Location
    }
}

[pscustomobject]@{
    task_name = $TaskName
    task_state = [string](if ($null -ne $task) { $task.State } else { 'Absent' })
    last_run_time = if ($null -ne $taskInfo) { $taskInfo.LastRunTime } else { $null }
    last_task_result = if ($null -ne $taskInfo) { $taskInfo.LastTaskResult } else { $null }
    runtime = $runtimeStatus
} | ConvertTo-Json -Depth 12
