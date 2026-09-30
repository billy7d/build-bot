<#
.SYNOPSIS
    Execute only the operator-approved Gate B Approval A1 procedure.

.DESCRIPTION
    This script is deliberately narrow and fail-closed. It verifies the exact
    installer and protected V26 root, captures a read-only V26 baseline, runs
    the approved installer once, verifies the installed terminal, compares the
    V26 baseline, and writes evidence outside both MT5 roots.

    It does not launch MT5 intentionally, configure a terminal, log in, copy
    an EA/preset, attach a chart, trade, schedule startup, or proceed to A2.
    If the installer self-starts terminal64.exe, only a process whose exact
    executable path is inside the dedicated root may be stopped.
#>

[CmdletBinding()]
param(
    [string]$InstallerPath = 'D:\mt5setup.exe',
    [string]$DedicatedRoot = 'D:\Trading\MT5-GateB-Acceptance',
    [string]$ProtectedV26Root = 'D:\Trading\MT5-V26',
    [string]$EvidenceBase = 'D:\Trading\MT5-GateB-Acceptance-Evidence',
    [int]$MaxInstallSeconds = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ApprovedInstallerSha256 = 'F15EEAE5E46DB7E94AFC2786C059266107E4AAED663B3318AFD4A3FC86D4F972'
$ApprovedInstallerSize = [int64]23312784
$ApprovedInstallerVersion = '5.0.0.5908'
$ApprovedSignerPattern = 'MetaQuotes Ltd.'
$RequiredFreeBytes = [int64]536870912

function Get-UtcNowString {
    return (Get-Date).ToUniversalTime().ToString('o')
}

function Convert-ToFullPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path)
}

function Test-SameOrChild([string]$Path, [string]$Parent) {
    $pathFull = (Convert-ToFullPath $Path).TrimEnd('\')
    $parentFull = (Convert-ToFullPath $Parent).TrimEnd('\')
    if ($pathFull.Equals($parentFull, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    return $pathFull.StartsWith($parentFull + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Get-PathRecord([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) {
        return [ordered]@{
            path = $Path
            exists = $false
            full_name = $Path
            attributes = $null
            link_type = $null
            is_reparse_point = $false
        }
    }
    return [ordered]@{
        path = $Path
        exists = $true
        full_name = $item.FullName
        attributes = [string]$item.Attributes
        link_type = [string]$item.LinkType
        is_reparse_point = (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
        length = if ($item.PSIsContainer) { $null } else { [int64]$item.Length }
        last_write_time_utc = $item.LastWriteTimeUtc.ToString('o')
    }
}

function Get-SignatureRecord([string]$Path) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    $certificate = $signature.SignerCertificate
    return [ordered]@{
        status = [string]$signature.Status
        status_message = [string]$signature.StatusMessage
        signer_subject = if ($null -ne $certificate) { [string]$certificate.Subject } else { $null }
        signer_issuer = if ($null -ne $certificate) { [string]$certificate.Issuer } else { $null }
        signer_thumbprint = if ($null -ne $certificate) { [string]$certificate.Thumbprint } else { $null }
        signer_matches_approved = if ($null -ne $certificate) { ([string]$certificate.Subject -match [regex]::Escape($ApprovedSignerPattern)) } else { $false }
    }
}

function Get-FileRecord([string]$Path, [bool]$IncludeSignature = $false) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item -or $item.PSIsContainer) {
        return [ordered]@{
            status = 'NOT_VERIFIED'
            path = $Path
            exists = $false
        }
    }
    $record = [ordered]@{
        status = 'VERIFIED'
        path = $Path
        exists = $true
        full_name = $item.FullName
        length = [int64]$item.Length
        last_write_time_utc = $item.LastWriteTimeUtc.ToString('o')
        file_version = [string]$item.VersionInfo.FileVersion
        product_version = [string]$item.VersionInfo.ProductVersion
        sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash
        attributes = [string]$item.Attributes
        link_type = [string]$item.LinkType
        is_reparse_point = (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
    }
    if ($IncludeSignature) {
        $record['authenticode'] = Get-SignatureRecord $item.FullName
    }
    return $record
}

function Get-TerminalProcessSnapshot {
    $rows = @()
    foreach ($process in @(Get-Process -Name 'terminal64' -ErrorAction SilentlyContinue)) {
        $executablePath = $null
        $pathStatus = 'NOT_VERIFIED'
        try {
            $executablePath = $process.MainModule.FileName
            $pathStatus = 'VERIFIED'
        } catch {
            $pathStatus = 'FAILED'
        }
        $startTime = $null
        try {
            $startTime = $process.StartTime.ToUniversalTime().ToString('o')
        } catch {
            $startTime = $null
        }
        $rows += [ordered]@{
            pid = [int]$process.Id
            name = [string]$process.ProcessName
            executable_path = $executablePath
            executable_path_status = $pathStatus
            start_time_utc = $startTime
        }
    }
    return @($rows)
}

function Get-DriveRecord([string]$Path) {
    $driveName = [IO.Path]::GetPathRoot((Convert-ToFullPath $Path))
    $drive = [IO.DriveInfo]::new($driveName)
    return [ordered]@{
        name = $drive.Name
        available_free_space = [int64]$drive.AvailableFreeSpace
        total_size = [int64]$drive.TotalSize
        required_free_space = $RequiredFreeBytes
        sufficient_free_space = ($drive.AvailableFreeSpace -ge $RequiredFreeBytes)
    }
}

function Test-ParentWritable([string]$Parent) {
    $probe = Join-Path $Parent ('.a1-write-probe-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $stream = $null
    try {
        $stream = [IO.File]::Open($probe, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $stream.WriteByte(0x41)
        $stream.Flush()
        $stream.Dispose()
        $stream = $null
        Remove-Item -LiteralPath $probe -Force -ErrorAction Stop
        return [ordered]@{ status = 'VERIFIED'; writable = $true; probe = $probe }
    } catch {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
        if (Test-Path -LiteralPath $probe -PathType Leaf) {
            Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        }
        return [ordered]@{ status = 'FAILED'; writable = $false; probe = $probe; error = $_.Exception.Message }
    }
}

function Get-TreeManifest([string]$Root) {
    $rootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
    $entries = @()
    $errors = @()
    foreach ($file in @(Get-ChildItem -LiteralPath $Root -File -Recurse -Force -ErrorAction SilentlyContinue)) {
        try {
            $entries += [ordered]@{
                relative_path = [IO.Path]::GetRelativePath($Root, $file.FullName)
                length = [int64]$file.Length
                last_write_time_utc = $file.LastWriteTimeUtc.ToString('o')
                sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
                attributes = [string]$file.Attributes
                link_type = [string]$file.LinkType
            }
        } catch {
            $errors += [ordered]@{
                path = $file.FullName
                error = $_.Exception.Message
            }
        }
    }
    return [ordered]@{
        status = if ($errors.Count -eq 0) { 'VERIFIED' } else { 'FAILED' }
        root = $rootItem.FullName
        root_attributes = [string]$rootItem.Attributes
        root_link_type = [string]$rootItem.LinkType
        file_count = $entries.Count
        error_count = $errors.Count
        errors = @($errors)
        files = @($entries | Sort-Object relative_path)
    }
}

function Compare-TreeManifest($Before, $After) {
    $beforeByPath = @{}
    foreach ($entry in @($Before.files)) { $beforeByPath[[string]$entry.relative_path] = $entry }
    $afterByPath = @{}
    foreach ($entry in @($After.files)) { $afterByPath[[string]$entry.relative_path] = $entry }
    $added = @()
    $removed = @()
    $modified = @()
    foreach ($path in $afterByPath.Keys) {
        if (-not $beforeByPath.ContainsKey($path)) {
            $added += $path
        } else {
            $beforeEntry = $beforeByPath[$path]
            $afterEntry = $afterByPath[$path]
            if (([string]$beforeEntry.sha256 -ne [string]$afterEntry.sha256) -or ([int64]$beforeEntry.length -ne [int64]$afterEntry.length) -or ([string]$beforeEntry.last_write_time_utc -ne [string]$afterEntry.last_write_time_utc)) {
                $modified += $path
            }
        }
    }
    foreach ($path in $beforeByPath.Keys) {
        if (-not $afterByPath.ContainsKey($path)) { $removed += $path }
    }
    $changed = ($added.Count + $removed.Count + $modified.Count) -eq 0
    return [ordered]@{
        status = if ($Before.status -eq 'VERIFIED' -and $After.status -eq 'VERIFIED' -and $changed) { 'VERIFIED' } else { 'FAILED' }
        unchanged = $changed
        added_files = @($added | Sort-Object)
        removed_files = @($removed | Sort-Object)
        modified_files = @($modified | Sort-Object)
    }
}

function Get-StartupArtifacts([string]$DedicatedPath) {
    $matches = @()
    $runLocations = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'
    )
    foreach ($location in $runLocations) {
        try {
            $properties = Get-ItemProperty -LiteralPath $location -ErrorAction Stop
            foreach ($property in $properties.PSObject.Properties) {
                if ($property.Name -in @('PSPath', 'PSParentPath', 'PSChildName', 'PSDrive', 'PSProvider')) { continue }
                $value = [string]$property.Value
                if ($value -match '(?i)terminal64|metatrader|mt5' -or $value.IndexOf($DedicatedPath, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $matches += [ordered]@{ location = $location; name = $property.Name; value = $value }
                }
            }
        } catch {
            $matches += [ordered]@{ location = $location; status = 'NOT_VERIFIED'; error = $_.Exception.Message }
        }
    }

    $scheduled = @()
    try {
        foreach ($task in @(Get-ScheduledTask -ErrorAction Stop)) {
            foreach ($action in @($task.Actions)) {
                $execute = [string]$action.Execute
                $arguments = [string]$action.Arguments
                if ($execute -match '(?i)terminal64|metatrader|mt5' -or $arguments.IndexOf($DedicatedPath, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $scheduled += [ordered]@{
                        task_name = [string]$task.TaskName
                        task_path = [string]$task.TaskPath
                        execute = $execute
                        arguments = $arguments
                    }
                }
            }
        }
    } catch {
        $scheduled += [ordered]@{ status = 'NOT_VERIFIED'; error = $_.Exception.Message }
    }

    $startupFolders = @(
        [Environment]::GetFolderPath('Startup'),
        [Environment]::GetFolderPath('CommonStartup')
    ) | Where-Object { $_ }
    $startupMatches = @()
    foreach ($folder in $startupFolders) {
        if (Test-Path -LiteralPath $folder -PathType Container) {
            foreach ($item in @(Get-ChildItem -LiteralPath $folder -Force -ErrorAction SilentlyContinue)) {
                if ($item.Name -match '(?i)terminal|metatrader|mt5' -or ([string]$item.FullName).IndexOf($DedicatedPath, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $startupMatches += [ordered]@{ folder = $folder; path = $item.FullName }
                }
            }
        }
    }
    return [ordered]@{
        status = if (@($matches | Where-Object { $_.status -eq 'NOT_VERIFIED' }).Count -eq 0 -and @($scheduled | Where-Object { $_.status -eq 'NOT_VERIFIED' }).Count -eq 0) { 'VERIFIED' } else { 'NOT_VERIFIED' }
        run_key_matches = @($matches)
        scheduled_task_matches = @($scheduled)
        startup_folder_matches = @($startupMatches)
        no_matching_startup_artifacts = (@($matches).Count -eq 0 -and @($scheduled).Count -eq 0 -and @($startupMatches).Count -eq 0)
    }
}

function Write-JsonEvidence([string]$Root, [string]$Name, $Value) {
    $path = Join-Path $Root $Name
    if (Test-Path -LiteralPath $path) { throw "EVIDENCE_OVERWRITE_FORBIDDEN:$path" }
    $json = $Value | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText($path, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    return $path
}

function Write-TextEvidence([string]$Root, [string]$Name, [string]$Text) {
    $path = Join-Path $Root $Name
    if (Test-Path -LiteralPath $path) { throw "EVIDENCE_OVERWRITE_FORBIDDEN:$path" }
    [IO.File]::WriteAllText($path, $Text, [Text.UTF8Encoding]::new($false))
    return $path
}

$startedUtc = Get-UtcNowString
$evidenceRoot = $null
$finalStatus = 'BLOCKED'
$installStatus = 'BLOCKED'
$hardStopReason = $null
$evidencePaths = @()
$preflight = [ordered]@{}
$installation = [ordered]@{}
$postInstall = [ordered]@{}
$v26Comparison = [ordered]@{}

try {
    $dedicatedParent = Split-Path -Parent $DedicatedRoot
    $evidenceBaseFull = Convert-ToFullPath $EvidenceBase
    $dedicatedFull = Convert-ToFullPath $DedicatedRoot
    $v26Full = Convert-ToFullPath $ProtectedV26Root

    if (Test-SameOrChild $DedicatedRoot $ProtectedV26Root -or Test-SameOrChild $ProtectedV26Root $DedicatedRoot) {
        throw 'HARD_STOP_DEDICATED_ROOT_OVERLAPS_V26'
    }
    if (Test-SameOrChild $EvidenceBase $DedicatedRoot -or Test-SameOrChild $EvidenceBase $ProtectedV26Root) {
        throw 'HARD_STOP_EVIDENCE_ROOT_OVERLAPS_MT5_ROOT'
    }
    if (-not (Test-Path -LiteralPath $dedicatedParent -PathType Container)) {
        throw 'HARD_STOP_DEDICATED_PARENT_MISSING'
    }
    if (Test-Path -LiteralPath $DedicatedRoot) {
        throw 'HARD_STOP_DEDICATED_ROOT_EXISTS_NO_OVERWRITE'
    }
    if (-not (Test-Path -LiteralPath $ProtectedV26Root -PathType Container)) {
        throw 'HARD_STOP_V26_ROOT_MISSING'
    }

    $parentRecord = Get-PathRecord $dedicatedParent
    $v26Record = Get-PathRecord $ProtectedV26Root
    if ($parentRecord.is_reparse_point -or $v26Record.is_reparse_point) {
        throw 'HARD_STOP_REPARSE_POINT_ON_PROTECTED_PATH'
    }

    $installerRecord = Get-FileRecord $InstallerPath $true
    $installerHashOk = ($installerRecord.status -eq 'VERIFIED' -and [string]$installerRecord.sha256 -ieq $ApprovedInstallerSha256)
    $installerSizeOk = ($installerRecord.status -eq 'VERIFIED' -and [int64]$installerRecord.length -eq $ApprovedInstallerSize)
    $installerVersionOk = ($installerRecord.status -eq 'VERIFIED' -and [string]$installerRecord.file_version -eq $ApprovedInstallerVersion)
    $installerSignatureOk = ($installerRecord.status -eq 'VERIFIED' -and [string]$installerRecord.authenticode.status -eq 'Valid' -and [bool]$installerRecord.authenticode.signer_matches_approved)
    if (-not ($installerHashOk -and $installerSizeOk -and $installerVersionOk -and $installerSignatureOk)) {
        throw 'HARD_STOP_INSTALLER_VERIFICATION_FAILED'
    }

    $processesBefore = Get-TerminalProcessSnapshot
    foreach ($process in $processesBefore) {
        if ($process.executable_path_status -ne 'VERIFIED' -or [string]::IsNullOrWhiteSpace([string]$process.executable_path)) {
            throw 'HARD_STOP_TERMINAL_PROCESS_OWNERSHIP_NOT_VERIFIED'
        }
    }
    $driveBefore = Get-DriveRecord $DedicatedRoot
    if (-not $driveBefore.sufficient_free_space) {
        throw 'HARD_STOP_INSUFFICIENT_FREE_SPACE'
    }
    $parentWritable = Test-ParentWritable $dedicatedParent
    if (-not $parentWritable.writable) {
        throw 'HARD_STOP_DEDICATED_PARENT_NOT_WRITABLE'
    }

    $v26Before = Get-TreeManifest $ProtectedV26Root
    if ($v26Before.status -ne 'VERIFIED') {
        throw 'HARD_STOP_V26_BASELINE_INCOMPLETE'
    }

    $commonRoot = Join-Path $env:APPDATA 'MetaQuotes\Terminal\Common'
    $v26ExpectedDataFolders = @('Config', 'Profiles', 'MQL5') | ForEach-Object {
        [ordered]@{ name = $_; path = Join-Path $ProtectedV26Root $_; exists = (Test-Path -LiteralPath (Join-Path $ProtectedV26Root $_) -PathType Container) }
    }

    $preflight = [ordered]@{
        status = 'PASS'
        timestamp_utc = Get-UtcNowString
        installer = $installerRecord
        installer_checks = [ordered]@{
            sha256_expected = $ApprovedInstallerSha256
            sha256_match = $installerHashOk
            size_expected = $ApprovedInstallerSize
            size_match = $installerSizeOk
            file_version_expected = $ApprovedInstallerVersion
            file_version_match = $installerVersionOk
            signature_valid = ([string]$installerRecord.authenticode.status -eq 'Valid')
            signer_match = [bool]$installerRecord.authenticode.signer_matches_approved
        }
        dedicated_root = Get-PathRecord $DedicatedRoot
        dedicated_parent = $parentRecord
        protected_v26_root = $v26Record
        protected_v26_terminal = Get-FileRecord (Join-Path $ProtectedV26Root 'terminal64.exe') $true
        v26_terminal_processes_before = @($processesBefore)
        dedicated_parent_writable = $parentWritable
        drive_before = $driveBefore
        v26_expected_data_layout = @($v26ExpectedDataFolders)
        common_root_candidate = Get-PathRecord $commonRoot
        common_root_policy = 'NO_ACCEPTANCE_WRITES_AT_A1; RUNTIME_ISOLATION_REQUIRES_A2'
        preflight_mutated_mt5_roots = $false
        install_command = 'D:\mt5setup.exe /auto /path:"D:\Trading\MT5-GateB-Acceptance"'
    }

    $session = 'A1-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    $evidenceRoot = Join-Path $evidenceBaseFull $session
    if (-not (Test-Path -LiteralPath $evidenceBaseFull)) {
        New-Item -ItemType Directory -Path $evidenceBaseFull -Force:$false | Out-Null
    } elseif (-not (Test-Path -LiteralPath $evidenceBaseFull -PathType Container)) {
        throw 'HARD_STOP_EVIDENCE_BASE_IS_NOT_DIRECTORY'
    }
    if (Test-Path -LiteralPath $evidenceRoot) { throw 'HARD_STOP_EVIDENCE_ROOT_EXISTS' }
    New-Item -ItemType Directory -Path $evidenceRoot -Force:$false | Out-Null
    $evidencePaths += Write-JsonEvidence $evidenceRoot 'preflight.json' $preflight
    $evidencePaths += Write-JsonEvidence $evidenceRoot 'v26-baseline-before.json' $v26Before

    $executionStart = Get-UtcNowString
    $executionClock = [Diagnostics.Stopwatch]::StartNew()
    $argumentList = @('/auto', ('/path:"' + $DedicatedRoot + '"'))
    $installerProcess = Start-Process -FilePath $InstallerPath -ArgumentList $argumentList -PassThru
    $exited = $installerProcess.WaitForExit($MaxInstallSeconds * 1000)
    $executionClock.Stop()
    $executionEnd = Get-UtcNowString
    $exitCode = $null
    if ($exited) {
        $exitCode = $installerProcess.ExitCode
    }
    $installation = [ordered]@{
        status = if ($exited -and $exitCode -eq 0) { 'PASS' } else { 'BLOCKED' }
        command = 'D:\mt5setup.exe /auto /path:"D:\Trading\MT5-GateB-Acceptance"'
        arguments = @($argumentList)
        process_id = [int]$installerProcess.Id
        start_utc = $executionStart
        end_utc = $executionEnd
        elapsed_seconds = [math]::Round($executionClock.Elapsed.TotalSeconds, 3)
        exited = $exited
        exit_code = $exitCode
        target_after_install = Get-PathRecord $DedicatedRoot
    }
    $evidencePaths += Write-JsonEvidence $evidenceRoot 'installation.json' $installation
    if (-not $exited) {
        throw 'HARD_STOP_INSTALLER_TIMEOUT_NO_RETRY'
    }
    if ($exitCode -ne 0) {
        throw ('INSTALLER_EXIT_CODE_NONZERO:' + $exitCode)
    }

    Start-Sleep -Seconds 2
    $processesAfterInstall = Get-TerminalProcessSnapshot
    $dedicatedTerminalProcesses = @($processesAfterInstall | Where-Object {
        $_.executable_path_status -eq 'VERIFIED' -and $_.executable_path -and (Test-SameOrChild ([string]$_.executable_path) $DedicatedRoot)
    })
    $unknownTerminalProcesses = @($processesAfterInstall | Where-Object {
        $_.executable_path_status -ne 'VERIFIED' -or -not $_.executable_path -or (-not (Test-SameOrChild ([string]$_.executable_path) $DedicatedRoot) -and -not (Test-SameOrChild ([string]$_.executable_path) $ProtectedV26Root))
    })
    $v26TerminalProcesses = @($processesAfterInstall | Where-Object {
        $_.executable_path_status -eq 'VERIFIED' -and $_.executable_path -and (Test-SameOrChild ([string]$_.executable_path) $ProtectedV26Root)
    })
    if ($unknownTerminalProcesses.Count -gt 0) {
        throw 'HARD_STOP_TERMINAL_PROCESS_OWNERSHIP_NOT_VERIFIED_AFTER_INSTALL'
    }
    $closedSelfStarted = @()
    foreach ($processRow in $dedicatedTerminalProcesses) {
        $processObject = Get-Process -Id ([int]$processRow.pid) -ErrorAction SilentlyContinue
        if ($null -eq $processObject) { continue }
        $currentPath = $null
        try { $currentPath = $processObject.MainModule.FileName } catch { $currentPath = $null }
        if ($null -eq $currentPath -or -not (Test-SameOrChild $currentPath $DedicatedRoot)) {
            throw 'HARD_STOP_DEDICATED_PROCESS_IDENTITY_CHANGED'
        }
        Stop-Process -Id ([int]$processRow.pid) -ErrorAction Stop
        try { $processObject.WaitForExit(10000) } catch {}
        $closedSelfStarted += [ordered]@{ pid = [int]$processRow.pid; executable_path = $currentPath; close_action = 'SAFE_EXACT_PATH_STOP' }
    }
    $processesAfterClose = Get-TerminalProcessSnapshot
    $remainingDedicated = @($processesAfterClose | Where-Object {
        $_.executable_path_status -eq 'VERIFIED' -and $_.executable_path -and (Test-SameOrChild ([string]$_.executable_path) $DedicatedRoot)
    })
    if ($remainingDedicated.Count -gt 0) {
        throw 'HARD_STOP_DEDICATED_SELF_STARTED_PROCESS_REMAINS'
    }

    $terminalPath = Join-Path $DedicatedRoot 'terminal64.exe'
    $terminalRecord = Get-FileRecord $terminalPath $true
    $terminalPathRecord = Get-PathRecord $terminalPath
    $terminalChecks = [ordered]@{
        exists = ($terminalRecord.status -eq 'VERIFIED')
        exact_install_root = ($terminalRecord.status -eq 'VERIFIED' -and $terminalRecord.full_name.Equals($terminalPath, [StringComparison]::OrdinalIgnoreCase))
        not_reparse_point = ($terminalRecord.status -eq 'VERIFIED' -and -not $terminalRecord.is_reparse_point)
        authenticode_valid = ($terminalRecord.status -eq 'VERIFIED' -and [string]$terminalRecord.authenticode.status -eq 'Valid')
        signer_matches = ($terminalRecord.status -eq 'VERIFIED' -and [bool]$terminalRecord.authenticode.signer_matches_approved)
        version_recorded = ($terminalRecord.status -eq 'VERIFIED' -and -not [string]::IsNullOrWhiteSpace([string]$terminalRecord.file_version))
        installer_version_comparison = if ($terminalRecord.status -eq 'VERIFIED' -and [string]$terminalRecord.file_version -eq $ApprovedInstallerVersion) { 'MATCH' } else { 'DIFFERS_OR_NOT_VERIFIED; INFORMATIONAL_ONLY' }
    }
    if (-not ($terminalChecks.exists -and $terminalChecks.exact_install_root -and $terminalChecks.not_reparse_point -and $terminalChecks.authenticode_valid -and $terminalChecks.signer_matches -and $terminalChecks.version_recorded)) {
        throw 'HARD_STOP_INSTALLED_TERMINAL_VERIFICATION_FAILED'
    }

    $v26After = Get-TreeManifest $ProtectedV26Root
    $v26Comparison = Compare-TreeManifest $v26Before $v26After
    if ($v26Comparison.status -ne 'VERIFIED') {
        throw 'HARD_STOP_V26_CHANGED_OR_COMPARISON_INCOMPLETE'
    }

    $startupArtifacts = Get-StartupArtifacts $DedicatedRoot
    if ($startupArtifacts.status -ne 'VERIFIED' -or -not $startupArtifacts.no_matching_startup_artifacts) {
        throw 'HARD_STOP_UNEXPECTED_STARTUP_ARTIFACT_OR_UNVERIFIED_CHECK'
    }

    $postInstall = [ordered]@{
        status = 'PASS'
        timestamp_utc = Get-UtcNowString
        installation_root = Get-PathRecord $DedicatedRoot
        terminal = $terminalRecord
        terminal_path = $terminalPathRecord
        terminal_checks = $terminalChecks
        terminal_processes_after_install = @($processesAfterInstall)
        dedicated_processes_closed = @($closedSelfStarted)
        terminal_processes_after_close = @($processesAfterClose)
        protected_v26_processes_after_install = @($v26TerminalProcesses)
        startup_activation_checks = $startupArtifacts
        dedicated_data_root = [ordered]@{
            expected_for_a2 = $DedicatedRoot
            actual_runtime_root = 'NOT_VERIFIED_A1_NO_RUNTIME_LAUNCH'
            status = 'NOT_VERIFIED'
        }
        common_root = [ordered]@{
            standard_common_root = $commonRoot
            exists = (Test-Path -LiteralPath $commonRoot -PathType Container)
            acceptance_namespace_written = $false
            status = 'NOT_VERIFIED'
            isolation = 'ISOLATION_PENDING_A2'
        }
        terminal_identity = [ordered]@{
            installation_path = $terminalPath
            runtime_process_identity = 'NOT_VERIFIED_A1_NO_RUNTIME_LAUNCH'
            file_identity = 'VERIFIED'
        }
        no_login_no_attach_no_trading = 'VERIFIED_BY_A1_SCOPE_AND_PROCESS_RECORD'
        v26_safety = $v26Comparison
    }
    $evidencePaths += Write-JsonEvidence $evidenceRoot 'v26-baseline-after.json' $v26After
    $evidencePaths += Write-JsonEvidence $evidenceRoot 'v26-comparison.json' $v26Comparison
    $evidencePaths += Write-JsonEvidence $evidenceRoot 'post-install.json' $postInstall

    $finalStatus = 'PASS'
    $installStatus = 'PASS'
} catch {
    $hardStopReason = $_.Exception.Message
    if ($null -eq $evidenceRoot) {
        try {
            $fallbackSession = 'A1-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-BLOCKED'
            $evidenceRoot = Join-Path (Convert-ToFullPath $EvidenceBase) $fallbackSession
            $fallbackBase = Split-Path -Parent $evidenceRoot
            if (-not (Test-Path -LiteralPath $fallbackBase)) {
                New-Item -ItemType Directory -Path $fallbackBase -Force:$false | Out-Null
            }
            if (-not (Test-Path -LiteralPath $evidenceRoot)) {
                New-Item -ItemType Directory -Path $evidenceRoot -Force:$false | Out-Null
            }
        } catch {}
    }
    $finalStatus = 'BLOCKED'
    $installStatus = if ($installation.status -eq 'PASS') { 'FAIL' } else { 'BLOCKED' }
}

$endedUtc = Get-UtcNowString
$summary = [ordered]@{
    schema = 'gate-b-approval-a1-execution/1'
    approval_a1 = 'GRANTED'
    approval_scope = 'DEDICATED_MT5_INSTALLATION_AND_INSTALLATION_LEVEL_VERIFICATION_ONLY'
    execution_start_utc = $startedUtc
    execution_end_utc = $endedUtc
    installer_path = $InstallerPath
    dedicated_installation_root = $DedicatedRoot
    protected_v26_root = $ProtectedV26Root
    evidence_root = $evidenceRoot
    preflight_status = if ($preflight.Count -gt 0) { [string]$preflight.status } else { 'NOT_VERIFIED' }
    installation_status = $installStatus
    post_install_status = if ($postInstall.Count -gt 0) { [string]$postInstall.status } else { 'NOT_VERIFIED' }
    v26_safety_status = if ($v26Comparison.Contains('status')) { [string]$v26Comparison['status'] } else { 'NOT_VERIFIED' }
    hard_stop_reason = $hardStopReason
    isolation_status = 'ISOLATION_PENDING_A2'
    a1_status = $finalStatus
    a2_authorized = 'NO'
    approval_b_authorized = 'NO'
    trading_authorized = 'NO'
    merge_ready = 'NO'
    activation_ready = 'NO'
    evidence_files = @($evidencePaths)
    no_retry_performed = $true
    no_v26_cleanup_or_rollback_performed = $true
}

if ($null -ne $evidenceRoot) {
    try {
        $summaryPath = Write-JsonEvidence $evidenceRoot 'a1-summary.json' $summary
        $evidencePaths += $summaryPath
        $reportLines = @(
            '### APPROVAL A1 — EXECUTION REPORT',
            '',
            '**1. Decision**',
            '',
            '`APPROVAL_A1=GRANTED`',
            '',
            '**2. Installation**',
            '',
            ('`INSTALL_STATUS=' + $installStatus + '`'),
            '',
            '**3. Installer verification**',
            '',
            ('Installer: `' + $InstallerPath + '`; expected SHA-256: `' + $ApprovedInstallerSha256 + '`; expected size: `' + $ApprovedInstallerSize + '`; expected file version: `' + $ApprovedInstallerVersion + '`; Authenticode signer requirement: `' + $ApprovedSignerPattern + '`.'),
            '',
            '**4. Terminal verification**',
            '',
            ('Installation root: `' + $DedicatedRoot + '`; terminal executable: `' + (Join-Path $DedicatedRoot 'terminal64.exe') + '`.'),
            '',
            '**5. Isolation**',
            '',
            'Dedicated data-root runtime identity and `FILE_COMMON` separation remain `ISOLATION_PENDING_A2` / `NOT_VERIFIED`; no acceptance data was written to the common root.',
            '',
            '**6. V26 safety**',
            '',
            ('Protected root: `' + $ProtectedV26Root + '`; baseline comparison status: `' + (if ($v26Comparison.Contains('status')) { [string]$v26Comparison['status'] } else { 'NOT_VERIFIED' }) + '`.'),
            '',
            '**7. Tests and evidence**',
            '',
            ('Evidence root: `' + $evidenceRoot + '`. Evidence files are listed in `a1-summary.json`.'),
            '',
            '**8. Blockers**',
            '',
            ('`' + [string]$hardStopReason + '`'),
            '',
            '**9. Final status**',
            '',
            ('`A1_STATUS=' + $finalStatus + '`'),
            '',
            '`A2_AUTHORIZED=NO`',
            '',
            '`APPROVAL_B_AUTHORIZED=NO`',
            '',
            '`TRADING_AUTHORIZED=NO`',
            '',
            '`MERGE_READY=NO`',
            '',
            '`ACTIVATION_READY=NO`'
        )
        $report = [string]::Join([Environment]::NewLine, $reportLines) + [Environment]::NewLine
        $reportPath = Write-TextEvidence $evidenceRoot 'a1-execution-report.md' $report
        $evidencePaths += $reportPath
    } catch {
        $summary['evidence_write_error'] = $_.Exception.Message
        $finalStatus = 'BLOCKED'
    }
}

$summary | ConvertTo-Json -Depth 20
if ($finalStatus -ne 'PASS') { exit 20 }
exit 0
