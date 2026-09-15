[CmdletBinding()]
param(
    [string]$RuntimeConfig = 'E:\build-bot-runtime\phase3\config\forward.json',
    [string]$TaskName = 'BuildBot-Phase3-Forward'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$configPath = (Resolve-Path -LiteralPath $RuntimeConfig).Path
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$repoPath = [System.IO.Path]::GetFullPath([string]$config.repo_path)
$pythonPath = [string]$config.python_path
if (-not [System.IO.Path]::IsPathRooted($pythonPath)) {
    $pythonPath = Join-Path $repoPath $pythonPath
}
$currentRunPath = Join-Path ([string]$config.runtime_root) 'state\current_run.json'
$runId = ''
if (Test-Path -LiteralPath $currentRunPath -PathType Leaf) {
    try {
        $currentRun = Get-Content -LiteralPath $currentRunPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $runId = [string]$currentRun.run_id
    } catch {
        $runId = ''
    }
}

$stopResult = $null
if ($runId) {
    Push-Location $repoPath
    try {
        $stopOutput = & $pythonPath -m agent.phase3 stop-forward --runtime-config $configPath --run-id $runId 2>&1
        $stopExitCode = $LASTEXITCODE
        if ($stopExitCode -eq 0) {
            $stopResult = ($stopOutput -join "`n") | ConvertFrom-Json
        }
    } finally {
        Pop-Location
    }
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    # Disable trước để logon kế tiếp không tự khởi động lại collector đã stop.
    Disable-ScheduledTask -TaskName $TaskName | Out-Null
    if ([string]$task.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $TaskName
    }
}

[pscustomobject]@{
    status = 'TASK_STOP_REQUESTED'
    task_name = $TaskName
    task_state = [string](if ($null -ne $task) { (Get-ScheduledTask -TaskName $TaskName).State } else { 'Absent' })
    collector_stop = $stopResult
    mt5_touched = $false
} | ConvertTo-Json -Depth 8
