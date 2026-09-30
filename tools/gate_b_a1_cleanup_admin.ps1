#requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Execute
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Fixed, evidence-bound targets. No arbitrary target path is accepted.
$script:TargetRoot = 'C:\Program Files\MetaTrader 5'
$script:V26Root = 'D:\Trading\MT5-V26'
$script:ApprovedRoot = 'D:\Trading\MT5-GateB-Acceptance'
$script:TradingParent = 'D:\Trading'
$script:EvidenceParent = 'D:\Trading\MT5-GateB-Acceptance-Evidence'
$script:PreCleanupEvidence = 'D:\Trading\MT5-GateB-Acceptance-Evidence\A1-R-20260924T105432Z-c04f088c\pre-cleanup.json'
$script:V26Baseline = 'D:\Trading\MT5-GateB-Acceptance-Evidence\A1-R-20260924T105432Z-c04f088c\v26-before-cleanup.json'
$script:ExpectedPreCleanupHash = 'AA6FC32521EE4BECB29317FB21A476F837E0B4EE7C54397431E55154F48FFB1C'
$script:ExpectedV26BaselineHash = '623BA3C04786F4CF8220324F5D222EB013B5936F5D80DE7DADA6043BB024A843'
$script:RegistryKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MetaTrader 5'
$script:V26RegistryKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MetaTrader 5 v26'
$script:ExpectedTerminalHash = 'F61ECFAD618A4577DF6743EB10E21CFEB2C374EA66BA8D4813C2C0CCCA784D33'
$script:ExpectedTerminalVersion = '5.0.0.6182'
$script:ExpectedUninstallerHash = 'F15EEAE5E46DB7E94AFC2786C059266107E4AAED663B3318AFD4A3FC86D4F972'
$script:DataRootToPreserve = 'C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075'
$script:CommonRootToPreserve = 'C:\Users\billy\AppData\Roaming\MetaQuotes\Terminal\Common'
$script:EvidenceDirectory = $null
$script:LogLines = [System.Collections.Generic.List[string]]::new()
$script:AdminState = $null
$script:ExitCode = 0

$script:Result = [ordered]@{
    schema = 'gate-b-a1r3-cleanup-admin/1'
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    mode = if ($DryRun) { 'DRY_RUN' } elseif ($Execute) { 'EXECUTE' } else { 'UNSPECIFIED' }
    identity = $null
    administrator_group_member = $false
    token_is_elevated = $false
    integrity_level = 'UNKNOWN'
    admin_verified = $false
    target_path = $script:TargetRoot
    target_canonical_path = $null
    v26_protected_path = $script:V26Root
    v26_canonical_path = $null
    approved_destination = $script:ApprovedRoot
    target_fingerprint = $null
    v26_pre_cleanup = $null
    v26_post_cleanup = $null
    process_list_before = $null
    process_list_after = $null
    system_references_before = $null
    system_references_after = $null
    actions_performed = @()
    files_removed = $null
    directories_removed = $null
    registry_key = $script:RegistryKey
    registry_backup = $null
    registry_action = 'NOT_RUN'
    preserved_paths = @($script:DataRootToPreserve, $script:CommonRootToPreserve)
    deferred_admin_read_checks = @()
    audit_warnings = @()
    final_target_exists = $null
    final_registry_entry_exists = $null
    status = 'NOT_STARTED'
    errors = @()
    exit_code = $null
}

function Write-LogLine {
    param([Parameter(Mandatory = $true)][string]$Message)
    $line = '{0} {1}' -f [DateTime]::UtcNow.ToString('o'), $Message
    $script:LogLines.Add($line)
    Write-Host $Message
}

function Get-TokenState {
    if (-not ('A1R3TokenNative' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class A1R3TokenNative {
    [DllImport("kernel32.dll")] public static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool CloseHandle(IntPtr h);
    [DllImport("advapi32.dll", SetLastError=true)] public static extern bool OpenProcessToken(IntPtr p, UInt32 access, out IntPtr token);
    [DllImport("advapi32.dll", SetLastError=true)] public static extern bool GetTokenInformation(IntPtr token, Int32 cls, out Int32 info, Int32 len, out Int32 returned);
}
'@ -ErrorAction Stop
    }

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $adminSid = [Security.Principal.SecurityIdentifier]::new([Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid, $null)
    $sidValues = @($identity.Groups | ForEach-Object { $_.Value })
    $groupMember = $sidValues -contains $adminSid.Value
    $inAdminRole = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    $token = [IntPtr]::Zero
    if (-not [A1R3TokenNative]::OpenProcessToken([A1R3TokenNative]::GetCurrentProcess(), 0x0008, [ref]$token)) {
        throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
    }
    try {
        $elevationType = 0
        $isElevated = 0
        $returned = 0
        if (-not [A1R3TokenNative]::GetTokenInformation($token, 18, [ref]$elevationType, 4, [ref]$returned)) {
            throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        if (-not [A1R3TokenNative]::GetTokenInformation($token, 20, [ref]$isElevated, 4, [ref]$returned)) {
            throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
    }
    finally {
        [void][A1R3TokenNative]::CloseHandle($token)
    }

    $groupsText = (& whoami.exe /groups /fo list 2>&1 | Out-String)
    $rid = $null
    if ($groupsText -match '(?im)SID:\s*S-1-16-(\d+)') { $rid = [int]$Matches[1] }
    $integrity = if ($null -eq $rid) { 'UNKNOWN' }
        elseif ($rid -ge 16384) { 'SYSTEM' }
        elseif ($rid -ge 12288) { 'HIGH' }
        elseif ($rid -ge 8192) { 'MEDIUM' }
        elseif ($rid -ge 4096) { 'LOW' }
        else { 'UNTRUSTED' }
    $typeName = switch ($elevationType) { 1 { 'Default' } 2 { 'Full' } 3 { 'Limited' } default { 'Unknown' } }
    $verified = $groupMember -and $inAdminRole -and ($isElevated -eq 1) -and ($integrity -in @('HIGH', 'SYSTEM'))

    return [pscustomobject]@{
        Identity = $identity.Name
        AdministratorGroupMember = $groupMember
        AdministratorRoleEnabled = $inAdminRole
        TokenElevationType = $typeName
        TokenIsElevated = ($isElevated -eq 1)
        IntegrityRid = $rid
        IntegrityLevel = $integrity
        Verified = $verified
    }
}

function ConvertTo-UtcTicks {
    param([Parameter(Mandatory = $true)]$Value)
    if ($Value -is [DateTime]) { return $Value.ToUniversalTime().Ticks }
    return ([DateTimeOffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)).UtcDateTime.Ticks
}

function Assert-NoReparseChain {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    $driveRoot = [IO.Path]::GetPathRoot($full)
    $probe = $full.TrimEnd('\')
    while ($probe -and ($probe -ine $driveRoot.TrimEnd('\'))) {
        if (Test-Path -LiteralPath $probe) {
            $item = Get-Item -LiteralPath $probe -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw ('UNEXPECTED_REPARSE_POINT: ' + $item.FullName)
            }
        }
        $parent = Split-Path -Parent $probe
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -ieq $probe) { break }
        $probe = $parent.TrimEnd('\')
    }
    if (Test-Path -LiteralPath $driveRoot) {
        $drive = Get-Item -LiteralPath $driveRoot -Force
        if ($drive.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw ('UNEXPECTED_REPARSE_POINT: ' + $driveRoot)
        }
    }
}

function Get-TreeSnapshotNoFollow {
    param([Parameter(Mandatory = $true)][string]$Path)
    $rootItem = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (-not $rootItem.PSIsContainer) { throw ('TARGET_NOT_DIRECTORY: ' + $Path) }
    if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('TARGET_IS_REPARSE_POINT: ' + $Path) }

    $files = [System.Collections.Generic.List[object]]::new()
    $directories = [System.Collections.Generic.List[string]]::new()
    $directoryMetadata = [System.Collections.Generic.List[object]]::new()
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($rootItem.FullName)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        foreach ($entry in Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop) {
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw ('UNEXPECTED_REPARSE_POINT: ' + $entry.FullName)
            }
            $relative = $entry.FullName.Substring($rootItem.FullName.Length).TrimStart('\')
            if ($entry.PSIsContainer) {
                $directories.Add($relative)
                $directoryMetadata.Add([pscustomobject]@{
                    relative_path = $relative
                    creation_utc = $entry.CreationTimeUtc
                    modified_utc = $entry.LastWriteTimeUtc
                })
                $pending.Push($entry.FullName)
            }
            else {
                $files.Add([pscustomobject]@{
                    relative_path = $relative
                    length = [long]$entry.Length
                    sha256 = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
                    creation_utc = $entry.CreationTimeUtc
                    modified_utc = $entry.LastWriteTimeUtc
                })
            }
        }
    }
    return [pscustomobject]@{
        Files = $files.ToArray()
        Directories = $directories.ToArray()
        DirectoryMetadata = $directoryMetadata.ToArray()
    }
}

function Assert-ExactFileManifest {
    param(
        [Parameter(Mandatory = $true)][object[]]$Expected,
        [Parameter(Mandatory = $true)][object[]]$Actual,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $expectedByPath = @{}
    foreach ($item in $Expected) {
        $key = [string]$item.relative_path
        if ($expectedByPath.ContainsKey($key)) { throw ($Label + '_BASELINE_DUPLICATE_PATH: ' + $key) }
        $expectedByPath[$key] = $item
    }
    $actualByPath = @{}
    foreach ($item in $Actual) { $actualByPath[[string]$item.relative_path] = $item }
    $added = [System.Collections.Generic.List[string]]::new()
    $removed = [System.Collections.Generic.List[string]]::new()
    $changed = [System.Collections.Generic.List[string]]::new()
    foreach ($path in $actualByPath.Keys) {
        if (-not $expectedByPath.ContainsKey($path)) { $added.Add($path); continue }
        $metadataChanged = [long]$expectedByPath[$path].length -ne [long]$actualByPath[$path].length -or
            [string]$expectedByPath[$path].sha256 -cne [string]$actualByPath[$path].sha256
        if ($expectedByPath[$path].PSObject.Properties['creation_utc']) {
            $metadataChanged = $metadataChanged -or
                (ConvertTo-UtcTicks $expectedByPath[$path].creation_utc) -ne (ConvertTo-UtcTicks $actualByPath[$path].creation_utc)
        }
        if ($expectedByPath[$path].PSObject.Properties['modified_utc']) {
            $metadataChanged = $metadataChanged -or
                (ConvertTo-UtcTicks $expectedByPath[$path].modified_utc) -ne (ConvertTo-UtcTicks $actualByPath[$path].modified_utc)
        }
        if ($metadataChanged) {
            $changed.Add($path)
        }
    }
    foreach ($path in $expectedByPath.Keys) {
        if (-not $actualByPath.ContainsKey($path)) { $removed.Add($path) }
    }
    if ($added.Count -or $removed.Count -or $changed.Count) {
        throw ('{0}_FINGERPRINT_MISMATCH added={1} removed={2} changed={3}' -f $Label, $added.Count, $removed.Count, $changed.Count)
    }
    return [pscustomobject]@{ FileCount = $Actual.Count; Added = 0; Removed = 0; Changed = 0 }
}

function Assert-TargetFingerprint {
    if (-not (Test-Path -LiteralPath $script:TargetRoot -PathType Container)) { throw 'FAILED_INSTALLATION_ROOT_MISSING' }
    Assert-NoReparseChain -Path $script:TargetRoot
    Assert-NoReparseChain -Path $script:V26Root
    Assert-NoReparseChain -Path $script:TradingParent
    if (Test-Path -LiteralPath $script:ApprovedRoot) { throw 'APPROVED_DESTINATION_ALREADY_EXISTS' }

    $manifestHash = (Get-FileHash -LiteralPath $script:PreCleanupEvidence -Algorithm SHA256 -ErrorAction Stop).Hash
    if ($manifestHash -cne $script:ExpectedPreCleanupHash) { throw 'A1R_BASELINE_MANIFEST_HASH_MISMATCH' }
    $baseline = Get-Content -LiteralPath $script:PreCleanupEvidence -Raw -ErrorAction Stop | ConvertFrom-Json
    if ([string]$baseline.schema -cne 'gate-b-approval-a1r-precleanup/1' -or
        [string]$baseline.wrong_root.path -ine $script:TargetRoot -or
        [int]$baseline.wrong_root.file_count -ne 583 -or
        [int]$baseline.wrong_root.directory_count -ne 19 -or
        [int]$baseline.wrong_root.hash_errors -ne 0 -or
        [bool]$baseline.wrong_root.reparse -or
        [bool]$baseline.failed_a1_install.approved_root_exists) {
        throw 'A1R_BASELINE_OWNERSHIP_EVIDENCE_MISMATCH'
    }

    $recordedRootCreated = ConvertTo-UtcTicks $baseline.failed_a1_install.root_creation_utc
    $inventoryRootCreated = ConvertTo-UtcTicks $baseline.wrong_root.creation_utc
    $recordedInstallStart = ConvertTo-UtcTicks $baseline.failed_a1_install.a1_install_started_utc
    if ($recordedRootCreated -ne $inventoryRootCreated -or $recordedRootCreated -le $recordedInstallStart) {
        throw 'A1R_BASELINE_CREATION_TIME_RELATIONSHIP_MISMATCH'
    }
    if (-not [bool]$baseline.failed_a1_install.wrong_root_created_after_a1_start) {
        $script:Result.audit_warnings = @($script:Result.audit_warnings) + @(
            'R1 derived flag wrong_root_created_after_a1_start=false conflicts with exact UTC timestamps; root creation (2026-09-22T14:39:12.2328917Z) is 44.570s after A1 install start (2026-09-22T14:38:27.6626996Z). Exact timestamps and live root CreationTimeUtc agree; preserve prior evidence unchanged.'
        )
    }

    $actual = Get-TreeSnapshotNoFollow -Path $script:TargetRoot
    $fileResult = Assert-ExactFileManifest -Expected @($baseline.wrong_root.files) -Actual @($actual.Files) -Label 'FAILED_ROOT'
    $expectedDirectories = @($baseline.wrong_root.directories | ForEach-Object { [string]$_.relative_path })
    $actualDirectories = @($actual.Directories)
    $dirSet = @{}
    foreach ($p in $actualDirectories) { $dirSet[$p] = $true }
    $directoryAdded = @($actualDirectories | Where-Object { $_ -notin $expectedDirectories })
    $directoryRemoved = @($expectedDirectories | Where-Object { -not $dirSet.ContainsKey($_) })
    if ($actualDirectories.Count -ne $expectedDirectories.Count -or $directoryAdded.Count -or $directoryRemoved.Count) {
        throw ('FAILED_ROOT_DIRECTORY_FINGERPRINT_MISMATCH added={0} removed={1}' -f $directoryAdded.Count, $directoryRemoved.Count)
    }
    $expectedDirectoryByPath = @{}
    foreach ($directory in $baseline.wrong_root.directories) {
        $expectedDirectoryByPath[[string]$directory.relative_path] = $directory
    }
    foreach ($directory in $actual.DirectoryMetadata) {
        $expectedDirectory = $expectedDirectoryByPath[[string]$directory.relative_path]
        if ((ConvertTo-UtcTicks $expectedDirectory.creation_utc) -ne (ConvertTo-UtcTicks $directory.creation_utc) -or
            (ConvertTo-UtcTicks $expectedDirectory.modified_utc) -ne (ConvertTo-UtcTicks $directory.modified_utc)) {
            throw ('FAILED_ROOT_DIRECTORY_TIMESTAMP_MISMATCH: ' + $directory.relative_path)
        }
    }

    $rootItem = Get-Item -LiteralPath $script:TargetRoot -Force
    if ($rootItem.CreationTimeUtc.Ticks -ne $recordedRootCreated) {
        throw 'FAILED_ROOT_CREATION_TIME_MISMATCH'
    }
    if ($rootItem.LastWriteTimeUtc.Ticks -ne (ConvertTo-UtcTicks $baseline.wrong_root.modified_utc)) {
        throw 'FAILED_ROOT_MODIFIED_TIME_MISMATCH'
    }
    if ($rootItem.CreationTimeUtc.Ticks -le $recordedInstallStart) {
        throw 'FAILED_ROOT_PRE_DATES_A1_INSTALL'
    }

    $terminalPath = Join-Path $script:TargetRoot 'terminal64.exe'
    $terminal = Get-Item -LiteralPath $terminalPath -ErrorAction Stop
    $terminalHash = (Get-FileHash -LiteralPath $terminalPath -Algorithm SHA256).Hash
    $terminalSignature = Get-AuthenticodeSignature -FilePath $terminalPath
    if ($terminalHash -cne $script:ExpectedTerminalHash -or
        [string]$terminal.VersionInfo.FileVersion -cne $script:ExpectedTerminalVersion -or
        [string]$terminalSignature.Status -cne 'Valid' -or
        [string]$terminalSignature.SignerCertificate.Subject -notmatch 'MetaQuotes Ltd\.') {
        throw 'FAILED_ROOT_TERMINAL_IDENTITY_MISMATCH'
    }

    $uninstallerPath = Join-Path $script:TargetRoot 'uninstall.exe'
    $uninstallerHash = (Get-FileHash -LiteralPath $uninstallerPath -Algorithm SHA256).Hash
    $uninstallerSignature = Get-AuthenticodeSignature -FilePath $uninstallerPath
    if ($uninstallerHash -cne $script:ExpectedUninstallerHash -or
        [string]$uninstallerSignature.Status -cne 'Valid' -or
        [string]$uninstallerSignature.SignerCertificate.Subject -notmatch 'MetaQuotes Ltd\.') {
        throw 'FAILED_ROOT_UNINSTALLER_IDENTITY_MISMATCH'
    }

    $registry = Get-ItemProperty -LiteralPath $script:RegistryKey -ErrorAction Stop
    if ([string]$registry.DisplayName -cne 'MetaTrader 5' -or
        [string]$registry.InstallLocation -ine $script:TargetRoot -or
        ([string]$registry.UninstallString).Trim('"') -ine $uninstallerPath -or
        [string]$registry.Publisher -cne 'MetaQuotes Ltd.') {
        throw 'FAILED_ROOT_REGISTRY_IDENTITY_MISMATCH'
    }
    $v26Registry = Get-ItemProperty -LiteralPath $script:V26RegistryKey -ErrorAction Stop
    if ([string]$v26Registry.InstallLocation -ine $script:V26Root) { throw 'V26_REGISTRY_IDENTITY_MISMATCH' }

    $suspicious = @($actual.Files | Where-Object {
        $ext = [IO.Path]::GetExtension([string]$_.relative_path).ToLowerInvariant()
        $ext -in @('.ex5', '.mq5', '.mqh', '.set', '.tpl')
    })
    $allowedDefaults = @(
        'Profiles\SymbolSets\forex.all.set',
        'Profiles\SymbolSets\forex.crosses.set',
        'Profiles\SymbolSets\forex.major.set',
        'Profiles\Templates\ADX.tpl',
        'Profiles\Templates\BollingerBands.tpl',
        'Profiles\Templates\Momentum.tpl'
    )
    $unexpectedArtifacts = @($suspicious | Where-Object { $_.relative_path -notin $allowedDefaults })
    if ($unexpectedArtifacts.Count) { throw ('FAILED_ROOT_POTENTIAL_USER_ARTIFACTS: ' + ($unexpectedArtifacts.relative_path -join ', ')) }

    $script:Result.target_canonical_path = (Resolve-Path -LiteralPath $script:TargetRoot -ErrorAction Stop).ProviderPath.TrimEnd('\')
    $script:Result.v26_canonical_path = (Resolve-Path -LiteralPath $script:V26Root -ErrorAction Stop).ProviderPath.TrimEnd('\')
    $destinationCanonical = Join-Path ((Resolve-Path -LiteralPath $script:TradingParent -ErrorAction Stop).ProviderPath.TrimEnd('\')) 'MT5-GateB-Acceptance'
    if ($script:Result.target_canonical_path -ieq $script:Result.v26_canonical_path -or
        $script:Result.target_canonical_path.StartsWith($script:Result.v26_canonical_path + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $script:Result.v26_canonical_path.StartsWith($script:Result.target_canonical_path + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $destinationCanonical -ieq $script:Result.v26_canonical_path -or
        $destinationCanonical.StartsWith($script:Result.v26_canonical_path + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $script:Result.v26_canonical_path.StartsWith($destinationCanonical + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'TARGET_PATH_COLLIDES_WITH_V26'
    }

    $script:Result.target_fingerprint = [pscustomobject]@{
        root = $script:TargetRoot
        canonical_path = $script:Result.target_canonical_path
        root_creation_utc = $rootItem.CreationTimeUtc.ToString('o')
        root_modified_utc = $rootItem.LastWriteTimeUtc.ToString('o')
        file_count = $fileResult.FileCount
        directory_count = $actualDirectories.Count
        baseline_manifest_sha256 = $manifestHash
        terminal_path = $terminalPath
        terminal_sha256 = $terminalHash
        terminal_version = [string]$terminal.VersionInfo.FileVersion
        terminal_signature = [string]$terminalSignature.Status
        terminal_signer = [string]$terminalSignature.SignerCertificate.Subject
        uninstaller_path = $uninstallerPath
        uninstaller_sha256 = $uninstallerHash
        uninstaller_signature = [string]$uninstallerSignature.Status
        registry_install_location = [string]$registry.InstallLocation
        registry_uninstall_string = [string]$registry.UninstallString
        candidate_custom_artifacts = @($suspicious.relative_path)
        unexpected_user_artifacts = 0
    }
    return $baseline
}

function Assert-V26Baseline {
    if (-not (Test-Path -LiteralPath $script:V26Root -PathType Container)) { throw 'V26_ROOT_MISSING' }
    Assert-NoReparseChain -Path $script:V26Root
    $manifestHash = (Get-FileHash -LiteralPath $script:V26Baseline -Algorithm SHA256 -ErrorAction Stop).Hash
    if ($manifestHash -cne $script:ExpectedV26BaselineHash) { throw 'V26_BASELINE_MANIFEST_HASH_MISMATCH' }
    $parsedExpected = Get-Content -LiteralPath $script:V26Baseline -Raw -ErrorAction Stop |
        ConvertFrom-Json

    $expected = @($parsedExpected)

    if ($expected.Count -ne 582) {
        throw 'V26_BASELINE_COUNT_MISMATCH'
    }
    $tree = Get-TreeSnapshotNoFollow -Path $script:V26Root
    $fileResult = Assert-ExactFileManifest -Expected $expected -Actual @($tree.Files) -Label 'V26'
    $reg = Get-ItemProperty -LiteralPath $script:V26RegistryKey -ErrorAction Stop
    if ([string]$reg.InstallLocation -ine $script:V26Root) { throw 'V26_REGISTRY_LOCATION_MISMATCH' }

    $expectedByPath = @{}
    foreach ($f in $expected) { $expectedByPath[[string]$f.relative_path] = $f }
    $timeChanged = [System.Collections.Generic.List[string]]::new()
    foreach ($f in $tree.Files) {
        $expectedTime = ConvertTo-UtcTicks $expectedByPath[[string]$f.relative_path].last_write_time_utc
        $currentPath = Join-Path $script:V26Root ([string]$f.relative_path)
        if ((Get-Item -LiteralPath $currentPath -Force).LastWriteTimeUtc.Ticks -ne $expectedTime) {
            $timeChanged.Add([string]$f.relative_path)
        }
    }
    if ($timeChanged.Count) { throw ('V26_TIMESTAMP_MISMATCH count=' + $timeChanged.Count) }
    return [pscustomobject]@{
        path = $script:V26Root
        canonical_path = (Resolve-Path -LiteralPath $script:V26Root -ErrorAction Stop).ProviderPath.TrimEnd('\')
        file_count = $fileResult.FileCount
        baseline_sha256 = $manifestHash
        added = 0
        removed = 0
        hash_or_size_changed = 0
        timestamp_changed = 0
        status = 'PASS'
    }
}

function Get-TargetSystemReferences {
    $references = [ordered]@{
        failed_root_processes = @()
        v26_processes = @()
        services = @()
        scheduled_tasks = @()
        startup_commands = @()
        run_entries = @()
        read_errors = [System.Collections.Generic.List[string]]::new()
    }
    $targetPrefix = $script:TargetRoot.TrimEnd('\') + '\'
    $v26Prefix = $script:V26Root.TrimEnd('\') + '\'

    try {
        $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
        $failed = @($processes | Where-Object { $_.ExecutablePath -and ([string]$_.ExecutablePath).StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase) })
        $v26 = @($processes | Where-Object { $_.ExecutablePath -and ([string]$_.ExecutablePath).StartsWith($v26Prefix, [StringComparison]::OrdinalIgnoreCase) })
        $references.failed_root_processes = @($failed | Select-Object ProcessId, Name, ExecutablePath, CreationDate)
        $references.v26_processes = @($v26 | Select-Object ProcessId, Name, ExecutablePath, CreationDate)
    }
    catch {
        $references.failed_root_processes = $null
        $references.v26_processes = $null
        $references.read_errors.Add('processes: ' + $_.Exception.Message)
    }

    try {
        $services = @(Get-CimInstance Win32_Service -ErrorAction Stop | Where-Object {
            $_.PathName -and ([string]$_.PathName).IndexOf($script:TargetRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
        } | Select-Object Name, State, StartName, PathName)
        $references.services = $services
    }
    catch {
        $references.services = $null
        $references.read_errors.Add('services: ' + $_.Exception.Message)
    }

    try {
        $tasks = [System.Collections.Generic.List[object]]::new()
        foreach ($task in Get-ScheduledTask -ErrorAction Stop) {
            $taskXml = Export-ScheduledTask -InputObject $task -ErrorAction Stop

            if ([string]::IsNullOrWhiteSpace([string]$taskXml)) {
                throw ('SCHEDULED_TASK_EXPORT_EMPTY: {0}{1}' -f $task.TaskPath, $task.TaskName)
            }

            $taskXmlText = [string]$taskXml

            if ($taskXmlText.IndexOf(
                    $script:TargetRoot,
                    [StringComparison]::OrdinalIgnoreCase
                ) -ge 0) {
                $tasks.Add([pscustomobject]@{
                    TaskPath = $task.TaskPath
                    TaskName = $task.TaskName
                    Match    = 'TASK_XML_CONTAINS_TARGET_ROOT'
                })
            }
        }
        $references.scheduled_tasks = $tasks.ToArray()
    }
    catch {
        $references.scheduled_tasks = $null
        $references.read_errors.Add(
            'scheduled_tasks: ' + $_.Exception.Message
        )
    }

    try {
        $startup = @(Get-CimInstance Win32_StartupCommand -ErrorAction Stop | Where-Object {
            $_.Command -and ([string]$_.Command).IndexOf($script:TargetRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
        } | Select-Object Name, Command, Location, User)
        $references.startup_commands = $startup
    }
    catch {
        $references.startup_commands = $null
        $references.read_errors.Add('startup_commands: ' + $_.Exception.Message)
    }

    $runEntries = [System.Collections.Generic.List[object]]::new()
    $runKeys = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce'
    )
    foreach ($key in $runKeys) {
        try {
            if (-not (Test-Path -LiteralPath $key)) { continue }
            $properties = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
            foreach ($property in $properties.PSObject.Properties) {
                if ($property.Name -notmatch '^PS' -and [string]$property.Value -and
                    ([string]$property.Value).IndexOf($script:TargetRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $runEntries.Add([pscustomobject]@{ Key = $key; Name = $property.Name; Value = [string]$property.Value })
                }
            }
        }
        catch { $references.read_errors.Add(('run_entry {0}: {1}' -f $key, $_.Exception.Message)) }
    }
    $references.run_entries = $runEntries.ToArray()
    return [pscustomobject]$references
}

function Assert-NoSystemReferences {
    param([ValidateSet('BEFORE', 'AFTER')][string]$Stage = 'BEFORE')
    $refs = Get-TargetSystemReferences
    $processSnapshot = $null
    if ($null -ne $refs.failed_root_processes -and $null -ne $refs.v26_processes) {
        $processSnapshot = @($refs.failed_root_processes + $refs.v26_processes)
    }
    if ($Stage -eq 'BEFORE') {
        $script:Result.process_list_before = $processSnapshot
        $script:Result.system_references_before = $refs
    }
    else {
        $script:Result.process_list_after = $processSnapshot
        $script:Result.system_references_after = $refs
    }
    if ($refs.read_errors.Count) {
        if ($DryRun -and -not $script:AdminState.Verified) {
            $script:Result.deferred_admin_read_checks = @($refs.read_errors.ToArray())
            Write-LogLine ('ADMIN_READ_CHECKS_DEFERRED count=' + $refs.read_errors.Count)
            return $false
        }
        throw ('SYSTEM_REFERENCE_CHECK_INCOMPLETE: ' + ($refs.read_errors -join '; '))
    }
    if (@($refs.failed_root_processes).Count) { throw ('TARGET_PROCESS_ACTIVE: ' + (@($refs.failed_root_processes | ForEach-Object { '{0}:{1}' -f $_.ProcessId, $_.ExecutablePath }) -join '; ')) }
    if (@($refs.services).Count -or @($refs.scheduled_tasks).Count -or @($refs.startup_commands).Count -or @($refs.run_entries).Count) {
        throw 'TARGET_SERVICE_OR_STARTUP_REFERENCE_FOUND'
    }
    return $true
}

function New-EvidenceDirectory {
    param([Parameter(Mandatory = $true)][string]$Kind)
    if (-not (Test-Path -LiteralPath $script:EvidenceParent -PathType Container)) { throw 'EVIDENCE_PARENT_MISSING' }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $name = if ($Kind -eq 'DRYRUN') { 'A1-R3-DryRun-' + $stamp } else { 'A1-R3-' + $stamp }
    $path = Join-Path $script:EvidenceParent $name
    New-Item -ItemType Directory -Path $path -ErrorAction Stop | Out-Null
    $script:EvidenceDirectory = $path
    $script:Result.evidence_directory = $path
    return $path
}

function Save-EvidenceFiles {
    if (-not $script:EvidenceDirectory) { return }
    $jsonPath = Join-Path $script:EvidenceDirectory 'cleanup-admin-result.json'
    $logPath = Join-Path $script:EvidenceDirectory 'cleanup-admin.log.txt'
    $script:Result.exit_code = $script:ExitCode
    $script:Result.timestamp_utc = [DateTime]::UtcNow.ToString('o')
    $script:Result.cleanup_result_json = $jsonPath
    $script:Result.transcript_log = $logPath
    $script:Result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $jsonPath -Encoding UTF8
    $script:LogLines | Set-Content -LiteralPath $logPath -Encoding UTF8
}

# Verify the actual token before any possible modification.
try {
    $script:AdminState = Get-TokenState
    $script:Result.identity = $script:AdminState.Identity
    $script:Result.administrator_group_member = $script:AdminState.AdministratorGroupMember
    $script:Result.token_is_elevated = $script:AdminState.TokenIsElevated
    $script:Result.integrity_level = $script:AdminState.IntegrityLevel
    $script:Result.admin_verified = $script:AdminState.Verified
}
catch {
    $script:Result.status = 'TOKEN_CHECK_FAILED'
    $script:Result.errors = @($_.Exception.Message)
    $script:ExitCode = 11
}

if ($script:ExitCode -eq 0 -and ($DryRun -eq $Execute)) {
    $script:Result.status = 'MODE_REQUIRED'
    $script:Result.errors = @('Specify exactly one of -DryRun or -Execute.')
    $script:ExitCode = 2
}

if ($script:ExitCode -eq 0 -and -not $script:AdminState.Verified) {
    Write-LogLine 'ADMIN_REQUIRED'
    if ($Execute) {
        $script:Result.status = 'ADMIN_REQUIRED_NO_MODIFICATION'
        $script:Result.errors = @('Execute mode requires enabled Administrators membership, an elevated token, and High/System integrity.')
        $script:ExitCode = 10
    }
}

if ($script:ExitCode -eq 0) {
    try {
        if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess) {
            throw '64_BIT_WINDOWS_POWERSHELL_REQUIRED'
        }

        $baseline = Assert-TargetFingerprint
        $script:Result.v26_pre_cleanup = Assert-V26Baseline
        Write-LogLine 'TARGET_FINGERPRINT=PASS'
        Write-LogLine 'V26_PRE_R3=PASS'

        $referencesComplete = Assert-NoSystemReferences
        if ($DryRun) {
            if ($referencesComplete) {
                $script:Result.status = 'DRY_RUN_PASS'
                $script:ExitCode = 0
                Write-LogLine 'DRY_RUN_STATUS=PASS'
                if ($script:AdminState.Verified) { [void](New-EvidenceDirectory -Kind 'DRYRUN') }
            }
            else {
                $script:Result.status = 'DRY_RUN_CORE_PASS_ADMIN_READS_DEFERRED'
                $script:ExitCode = 20
                Write-LogLine 'DRY_RUN_CORE_CHECKS=PASS'
                Write-LogLine 'DRY_RUN_STATUS=INCOMPLETE_ADMIN_READ_CHECKS'
            }
        }
        else {
            [void](New-EvidenceDirectory -Kind 'EXECUTE')
            Write-LogLine 'CLEANUP_METHOD=CONTROLLED_MANUAL_EXACT_TARGET'
            Write-LogLine 'APPDATA_COMMON_ACTION=PRESERVE_NO_DELETE'

            $backup = Join-Path $script:EvidenceDirectory 'failed-install-uninstall-entry.reg'
            $script:Result.registry_backup = $backup
            $exportOutput = & reg.exe export 'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\MetaTrader 5' $backup /y 2>&1
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $backup -PathType Leaf)) {
                throw ('REGISTRY_EXPORT_FAILED: ' + ($exportOutput -join ' '))
            }
            $script:Result.registry_action = 'EXPORTED_BEFORE_REMOVAL'
            $script:LogLines.Add('REGISTRY_EXPORT=PASS path=' + $backup)

            # Repeat the full fingerprint and V26 checks immediately before deletion.
            $null = Assert-TargetFingerprint
            $null = Assert-V26Baseline
            $regNow = Get-ItemProperty -LiteralPath $script:RegistryKey -ErrorAction Stop
            if ([string]$regNow.InstallLocation -ine $script:TargetRoot -or
                ([string]$regNow.UninstallString).Trim('"') -ine (Join-Path $script:TargetRoot 'uninstall.exe')) {
                throw 'REGISTRY_CHANGED_AFTER_EXPORT'
            }

            # Recheck process/service/task/startup references immediately before removal.
            $null = Assert-NoSystemReferences -Stage 'BEFORE'
            $beforeTree = Get-TreeSnapshotNoFollow -Path $script:TargetRoot
            $script:Result.files_removed = @($beforeTree.Files).Count
            $script:Result.directories_removed = @($beforeTree.Directories).Count
            Remove-Item -LiteralPath $script:TargetRoot -Recurse -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $script:TargetRoot) { throw 'WRONG_ROOT_REMOVAL_INCOMPLETE' }
            $script:Result.actions_performed = @($script:Result.actions_performed) + @('Removed exact failed A1 tree: ' + $script:TargetRoot)
            Write-LogLine 'WRONG_ROOT_TREE_REMOVED=YES'

            if (Test-Path -LiteralPath $script:RegistryKey) {
                $regCurrent = Get-ItemProperty -LiteralPath $script:RegistryKey -ErrorAction Stop
                if ([string]$regCurrent.InstallLocation -ine $script:TargetRoot -or
                    ([string]$regCurrent.UninstallString).Trim('"') -ine (Join-Path $script:TargetRoot 'uninstall.exe')) {
                    throw 'REGISTRY_OWNERSHIP_CHANGED_AFTER_TREE_REMOVAL'
                }
                Remove-Item -LiteralPath $script:RegistryKey -Recurse -Force -ErrorAction Stop
                $script:Result.registry_action = 'EXPORTED_THEN_REMOVED_EXACT_MATCHING_ENTRY'
            }
            else {
                throw 'EXPECTED_FAILED_ROOT_REGISTRY_ENTRY_MISSING_AFTER_TREE_REMOVAL'
            }

            if (Test-Path -LiteralPath $script:TargetRoot) { throw 'WRONG_ROOT_RESIDUAL_AFTER_CLEANUP' }
            if (Test-Path -LiteralPath $script:RegistryKey) { throw 'WRONG_ROOT_REGISTRY_RESIDUAL_AFTER_CLEANUP' }
            $script:Result.final_target_exists = $false
            $script:Result.final_registry_entry_exists = $false
            $script:Result.v26_post_cleanup = Assert-V26Baseline
            $null = Assert-NoSystemReferences -Stage 'AFTER'
            $script:Result.status = 'CLEANUP_PASS'
            $script:ExitCode = 0
            Write-LogLine 'WRONG_ROOT_CLEAN=YES'
            Write-LogLine 'V26_POST_R3_CLEANUP=PASS'
            Write-LogLine 'CLEANUP_STATUS=PASS'
        }
    }
    catch {
        $script:Result.status = if ($DryRun) { 'DRY_RUN_FAIL' } else { 'CLEANUP_BLOCKED_OR_FAILED' }
        $script:Result.errors = @($script:Result.errors) + @($_.Exception.Message)
        $script:ExitCode = 1
        Write-LogLine ('ERROR: ' + $_.Exception.Message)
        if ($Execute -and $script:EvidenceDirectory) {
            $script:Result.final_target_exists = [bool](Test-Path -LiteralPath $script:TargetRoot)
            $script:Result.final_registry_entry_exists = [bool](Test-Path -LiteralPath $script:RegistryKey)
        }
    }
}

$script:Result.exit_code = $script:ExitCode
if ($script:EvidenceDirectory) {
    try { Save-EvidenceFiles }
    catch {
        $script:Result.status = 'EVIDENCE_WRITE_FAILED'
        $script:Result.errors = @($script:Result.errors) + @($_.Exception.Message)
        $script:ExitCode = 30
        $script:Result.exit_code = $script:ExitCode
        Write-LogLine ('EVIDENCE_WRITE_ERROR: ' + $_.Exception.Message)
    }
}

Write-Output ($script:Result | ConvertTo-Json -Depth 12)
exit $script:ExitCode
