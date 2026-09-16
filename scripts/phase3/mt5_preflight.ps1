[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$TerminalPath,
    [Parameter(Mandatory=$true)][string]$DataDirectory,
    [Parameter(Mandatory=$true)][string]$EaPath,
    [Parameter(Mandatory=$true)][string]$PresetPath,
    [Parameter(Mandatory=$true)][string]$PrimarySourcePath,
    [Parameter(Mandatory=$true)][string]$OpsRoot,
    [string]$ExpectedServer,
    [string]$ExpectedAccount,
    [string]$CommonFilesRoot,
    [string]$JournalEvidencePath,
    [string]$TerminalVersion,
    [string]$ExpectedEaSha256,
    [string]$ExpectedPresetSha256,
    [switch]$MarketDataConfirmed,
    [switch]$RealRecordConfirmed,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Push-Location $InstallRoot
try {
    $arguments = @(
        '-m', 'agent.phase3', 'mt5-preflight',
        '--terminal-path', $TerminalPath,
        '--data-directory', $DataDirectory,
        '--ea-path', $EaPath,
        '--preset-path', $PresetPath,
        '--primary-source-path', $PrimarySourcePath,
        '--ops-root', $OpsRoot
    )
    foreach ($pair in @(
        @('--expected-server', $ExpectedServer),
        @('--expected-account', $ExpectedAccount),
        @('--common-files-root', $CommonFilesRoot),
        @('--journal-evidence-path', $JournalEvidencePath),
        @('--terminal-version', $TerminalVersion),
        @('--expected-ea-sha256', $ExpectedEaSha256),
        @('--expected-preset-sha256', $ExpectedPresetSha256)
    )) {
        if ($pair[1]) { $arguments += $pair }
    }
    if ($MarketDataConfirmed) { $arguments += '--market-data-confirmed' }
    if ($RealRecordConfirmed) { $arguments += '--real-record-confirmed' }
    & $PythonPath @arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
