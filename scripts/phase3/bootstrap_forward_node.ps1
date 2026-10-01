[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$OpsRoot,
    [Parameter(Mandatory=$true)][string]$PackagePath,
    [Parameter(Mandatory=$true)][string]$ExpectedGitSha,
    [string]$ExpectedTrustedManifestDigest,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $PackagePath -PathType Container)) {
    throw "Không tìm thấy deployment package: $PackagePath"
}

# Chỉ code từ checkout đã được operator/trusted channel phê duyệt mới được chạy.
# Không chạy bất kỳ script nào lấy từ deployment package trước khi verifier tin cậy
# đã kiểm tra package; package bootstrap chỉ là dữ liệu không đáng tin ở thời điểm này.
if (-not (Test-Path -LiteralPath $InstallRoot -PathType Container)) {
    throw 'BOOTSTRAP_STOP_TRUSTED_SOURCE_REQUIRED'
}
$sourceMarker = Join-Path $InstallRoot '.git'
if (-not (Test-Path -LiteralPath $sourceMarker)) {
    throw 'BOOTSTRAP_STOP_TRUSTED_SOURCE_REQUIRED'
}

if ($ExpectedGitSha -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'BOOTSTRAP_STOP_INVALID_EXPECTED_GIT_SHA'
}
$gitShaArguments = @('-C', $InstallRoot, 'rev-parse', '--verify', 'HEAD')
$actualGitShaOutput = & git @gitShaArguments 2>$null
$gitShaExitCode = $LASTEXITCODE
$actualGitSha = ($actualGitShaOutput -join "`n").Trim()
if ($gitShaExitCode -ne 0 -or $actualGitSha -ne $ExpectedGitSha.ToLowerInvariant()) {
    throw 'BOOTSTRAP_STOP_TRUSTED_SOURCE_SHA_MISMATCH'
}
$gitStatusArguments = @('-C', $InstallRoot, 'status', '--porcelain', '--untracked-files=all')
$sourceStatusOutput = & git @gitStatusArguments 2>$null
$gitStatusExitCode = $LASTEXITCODE
if ($gitStatusExitCode -ne 0) {
    throw 'BOOTSTRAP_STOP_TRUSTED_SOURCE_STATUS_UNAVAILABLE'
}
if ((($sourceStatusOutput -join "`n").Trim()).Length -gt 0) {
    throw 'BOOTSTRAP_STOP_TRUSTED_SOURCE_NOT_CLEAN'
}

Push-Location $InstallRoot
try {
    $arguments = @(
        '-m', 'agent.phase3', 'bootstrap-forward-node',
        '--package-path', $PackagePath,
        '--install-root', $InstallRoot,
        '--runtime-root', $RuntimeRoot,
        '--ops-root', $OpsRoot,
        '--expected-git-sha', $ExpectedGitSha
    )
    if ($ExpectedTrustedManifestDigest) {
        $arguments += @('--expected-trusted-manifest-digest', $ExpectedTrustedManifestDigest)
    }
    & $PythonPath @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
