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

# Khi source chưa tồn tại, dùng bootstrap đã đóng gói để clone đúng SHA trước.
$sourceMarker = Join-Path $InstallRoot '.git'
if (-not (Test-Path -LiteralPath $sourceMarker)) {
    $packageBootstrap = Join-Path $PackagePath 'bootstrap\bootstrap.ps1'
    if (-not (Test-Path -LiteralPath $packageBootstrap -PathType Leaf)) {
        throw 'Package thiếu bootstrap\bootstrap.ps1; dừng trước khi tạo runtime.'
    }
    $packageArguments = @(
        '-InstallRoot', $InstallRoot,
        '-RuntimeRoot', $RuntimeRoot,
        '-OpsRoot', $OpsRoot,
        '-PackagePath', $PackagePath,
        '-ExpectedGitSha', $ExpectedGitSha,
        '-PythonPath', $PythonPath
    )
    if ($ExpectedTrustedManifestDigest) {
        $packageArguments += @('-ExpectedTrustedManifestDigest', $ExpectedTrustedManifestDigest)
    }
    & $packageBootstrap @packageArguments
    exit $LASTEXITCODE
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
