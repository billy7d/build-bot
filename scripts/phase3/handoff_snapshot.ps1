[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RuntimeConfig,
    [Parameter(Mandatory=$true)][string]$OpsRoot,
    [string]$PythonPath = 'python',
    [string]$RunId,
    [string]$NextStep
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $RuntimeConfig).Path
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$repoPath = [System.IO.Path]::GetFullPath([string]$config.repo_path)
Push-Location $repoPath
try {
    $arguments = @('-m', 'agent.phase3', 'handoff-snapshot', '--runtime-config', $configPath, '--ops-root', $OpsRoot)
    if ($RunId) { $arguments += @('--run-id', $RunId) }
    if ($NextStep) { $arguments += @('--next-step', $NextStep) }
    & $PythonPath @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
