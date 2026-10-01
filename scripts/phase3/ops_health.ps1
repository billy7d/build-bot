[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RuntimeConfig,
    [Parameter(Mandatory=$true)][string]$OpsRoot,
    [string]$PythonPath = 'python',
    [int64]$WarningDiskFreeBytes = 10737418240,
    [int64]$CriticalDiskFreeBytes = 2147483648
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $RuntimeConfig).Path
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$repoPath = [System.IO.Path]::GetFullPath([string]$config.repo_path)
Push-Location $repoPath
try {
    & $PythonPath -m agent.phase3 ops-health --runtime-config $configPath --ops-root $OpsRoot `
        --warning-disk-free-bytes $WarningDiskFreeBytes --critical-disk-free-bytes $CriticalDiskFreeBytes
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
