[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [Parameter(Mandatory=$true)][string]$NewInstallRoot,
    [Parameter(Mandatory=$true)][string]$NewRuntimeRoot,
    [string]$Output,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Push-Location $InstallRoot
try {
    $arguments = @(
        '-m', 'agent.phase3', 'plan-forward-migration',
        '--backup-path', $BackupPath,
        '--new-install-root', $NewInstallRoot,
        '--new-runtime-root', $NewRuntimeRoot
    )
    if ($Output) { $arguments += @('--output', $Output) }
    & $PythonPath @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
