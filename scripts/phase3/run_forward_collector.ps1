[CmdletBinding()]
param(
    [string]$RuntimeConfig = 'E:\build-bot-runtime\phase3\config\forward.json',
    [string]$Authorization = '',
    [string]$RunId = '',
    [switch]$NewRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$configPath = (Resolve-Path -LiteralPath $RuntimeConfig).Path
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$config.execution_mode -ne 'NONE' -or [bool]$config.live_execution_enabled) {
    throw 'Collector chỉ chạy với execution_mode=NONE và live_execution_enabled=false.'
}
$repoPath = [System.IO.Path]::GetFullPath([string]$config.repo_path)
$pythonPath = [string]$config.python_path
if (-not [System.IO.Path]::IsPathRooted($pythonPath)) {
    $pythonPath = Join-Path $repoPath $pythonPath
}
$runtimeRoot = [System.IO.Path]::GetFullPath([string]$config.runtime_root)
$logDir = Join-Path $runtimeRoot 'logs'
$logPath = Join-Path $logDir 'forward_collector.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if ((Test-Path -LiteralPath $logPath) -and ((Get-Item -LiteralPath $logPath).Length -gt 5MB)) {
    $archivePath = "$logPath.1"
    if (Test-Path -LiteralPath $archivePath) {
        Remove-Item -LiteralPath $archivePath -Force
    }
    Move-Item -LiteralPath $logPath -Destination $archivePath -Force
}

$currentRunPath = Join-Path $runtimeRoot 'state\current_run.json'
$storedRunId = ''
if (-not $NewRun -and -not $RunId -and (Test-Path -LiteralPath $currentRunPath -PathType Leaf)) {
    try {
        $currentRun = Get-Content -LiteralPath $currentRunPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $storedRunId = [string]$currentRun.run_id
    } catch {
        $storedRunId = ''
    }
}

$arguments = @('-m', 'agent.phase3')
if ($RunId -or $storedRunId) {
    $arguments += @('resume-forward', '--runtime-config', $configPath, '--run-id', $(if ($RunId) { $RunId } else { $storedRunId }))
} else {
    $arguments += @('start-forward', '--runtime-config', $configPath)
}
if ($Authorization) {
    $arguments += @('--authorization', $Authorization)
}

Push-Location $repoPath
try {
    $output = & $pythonPath @arguments 2>&1
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
$stamp = (Get-Date).ToUniversalTime().ToString('o')
Add-Content -LiteralPath $logPath -Value "[$stamp] exit_code=$exitCode"
foreach ($line in $output) {
    Add-Content -LiteralPath $logPath -Value ([string]$line)
}
exit $exitCode
