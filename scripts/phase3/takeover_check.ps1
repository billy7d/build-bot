[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$OpsRoot,
    [string]$ExpectedRunId,
    [string]$ExpectedGitSha,
    [string]$ExpectedSourceIdentity,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Push-Location $InstallRoot
try {
    $arguments = @('-m', 'agent.phase3', 'takeover-check', '--ops-root', $OpsRoot)
    foreach ($pair in @(
        @('--expected-run-id', $ExpectedRunId),
        @('--expected-git-sha', $ExpectedGitSha),
        @('--expected-source-identity', $ExpectedSourceIdentity)
    )) {
        if ($pair[1]) { $arguments += $pair }
    }
    & $PythonPath @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
