[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [Parameter(Mandatory=$true)][string]$TargetRoot,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Push-Location $InstallRoot
try {
    & $PythonPath -m agent.phase3 restore-forward-backup `
        --backup-path $BackupPath --target-root $TargetRoot --mode isolated
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
