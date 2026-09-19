[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('status', 'health', 'dry-run', 'recover-once', 'start', 'stop')]
    [string]$Action,
    [Parameter(Mandatory = $true)]
    [string]$Config,
    [string]$Instance,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $repoRoot
try {
    if ($Action -eq 'start') {
        # Persistent service/task installation is deliberately outside this script.
        & $PythonPath -m agent.phase3 mt5-watchdog-start --config $Config
        exit $LASTEXITCODE
    }
    if ($Action -eq 'stop') {
        # This command never stops a terminal or a watchdog process.
        & $PythonPath -m agent.phase3 mt5-watchdog-stop --config $Config
        exit $LASTEXITCODE
    }

    $command = switch ($Action) {
        'status' { 'mt5-watchdog-status' }
        'health' { 'mt5-watchdog-health' }
        'dry-run' { 'mt5-watchdog-dry-run' }
        'recover-once' { 'mt5-watchdog-recover-once' }
    }
    $arguments = @('-m', 'agent.phase3', $command, '--config', $Config)
    if ($Instance) { $arguments += @('--instance', $Instance) }
    & $PythonPath @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
