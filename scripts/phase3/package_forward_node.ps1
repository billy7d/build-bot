[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Output,
    [Parameter(Mandatory=$true)][string]$ApprovedGitSha,
    [Parameter(Mandatory=$true)][string]$RepositoryUrl,
    [Parameter(Mandatory=$true)][string]$BundleManifest,
    [Parameter(Mandatory=$true)][string]$ModelBundle,
    [Parameter(Mandatory=$true)][string]$HistoryIndex,
    [Parameter(Mandatory=$true)][string]$EaEx5,
    [Parameter(Mandatory=$true)][string]$EaPreset,
    [Parameter(Mandatory=$true)][string]$EaSourceRevision,
    [Parameter(Mandatory=$true)][string]$DependencyManifest,
    [string]$SourceMq5,
    [string]$Phase1Fingerprint,
    [string]$TrustedManifestDigest,
    [string]$InstallRoot = (Get-Location).Path,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Push-Location $InstallRoot
try {
    $arguments = @(
        '-m', 'agent.phase3', 'package-forward-node',
        '--output', $Output,
        '--approved-git-sha', $ApprovedGitSha,
        '--repository-url', $RepositoryUrl,
        '--bundle-manifest', $BundleManifest,
        '--model-bundle', $ModelBundle,
        '--history-index', $HistoryIndex,
        '--ea-ex5', $EaEx5,
        '--ea-preset', $EaPreset,
        '--ea-source-revision', $EaSourceRevision,
        '--dependency-manifest', $DependencyManifest
    )
    foreach ($pair in @(
        @('--source-mq5', $SourceMq5),
        @('--phase1-fingerprint', $Phase1Fingerprint),
        @('--trusted-manifest-digest', $TrustedManifestDigest)
    )) {
        if ($pair[1]) { $arguments += $pair }
    }
    & $PythonPath @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
