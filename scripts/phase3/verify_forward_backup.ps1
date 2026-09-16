[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [string]$SourcePath,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Push-Location $InstallRoot
try {
    $arguments = @('-m', 'agent.phase3', 'verify-forward-backup', '--backup-path', $BackupPath)
    if ($SourcePath) { $arguments += @('--source-path', $SourcePath) }
    & $PythonPath @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
