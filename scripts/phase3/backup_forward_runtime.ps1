[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RuntimeConfig,
    [Parameter(Mandatory=$true)][string]$OpsRoot,
    [string]$PythonPath = 'python',
    [string]$BackupRoot,
    [string]$BackupId
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $RuntimeConfig).Path
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$repoPath = [System.IO.Path]::GetFullPath([string]$config.repo_path)
Push-Location $repoPath
try {
    $arguments = @('-m', 'agent.phase3', 'backup-forward-runtime', '--runtime-config', $configPath, '--ops-root', $OpsRoot)
    if ($BackupRoot) { $arguments += @('--backup-root', $BackupRoot) }
    if ($BackupId) { $arguments += @('--backup-id', $BackupId) }
    & $PythonPath @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
