[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PolicyApprovalPath,
    [Parameter(Mandatory=$true)][string]$ExecutionApprovalPath,
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$OpsRoot,
    [Parameter(Mandatory=$true)][string]$PackagePath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$TrustedManifestDigest,
    [Parameter(Mandatory=$true)][string]$ProductionRuntimeRoot,
    [Parameter(Mandatory=$true)][string]$ReportPath,
    [Parameter(Mandatory=$true)][switch]$OperatorApprovalConfirmed,
    [switch]$TestOnly,
    [string]$PythonPath = 'python',
    [string]$BackupRoot,
    [string]$RestoreRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedSourceSha = 'bbf87b40eb72de35318608cb9e4d4f77d150e32a'
$ExpectedManifestSha = '480699fb07371cce25912c73bef4ee5dc81a161839265f24e7d369300f9aaf34'
$ExpectedEx5Sha = 'a4e77d4a16ee17b5327dfdba8b5d8f503413bb419c61082b93a92a8fd63565be'
$ExpectedPresetSha = 'b5ead1a5e54d3ca2f473c04d8c01c5cb9e2508e339b1793dc67f8f00d96b2abf'

function Full([string]$Path) { return [System.IO.Path]::GetFullPath($Path).TrimEnd('\') }
function Sha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Has-Property($Object, [string]$Name) { return $null -ne $Object -and ($Object.PSObject.Properties.Name -contains $Name) }
function Require-Path([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "GATE_C_LITE_STOP_MISSING_$Label" }
}
function Require-EmptyOrMissing([string]$Path, [string]$Label) {
    if (Test-Path -LiteralPath $Path) {
        if (@(Get-ChildItem -LiteralPath $Path -Force).Count -gt 0) {
            throw "GATE_C_LITE_STOP_NON_EMPTY_$Label"
        }
    }
}
function Run-Python([string[]]$Arguments) {
    Push-Location $InstallRoot
    try {
        $output = @(& $PythonPath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally { Pop-Location }
    return [ordered]@{
        exit_code = $exitCode
        output = @($output | ForEach-Object { [string]$_ })
        text = ($output -join [Environment]::NewLine)
    }
}
function Parse-JsonOutput($Result, [string]$Label) {
    if ($Result.exit_code -ne 0) { throw "GATE_C_LITE_STOP_${Label}_$($Result.text)" }
    try { return ($Result.text | ConvertFrom-Json) } catch { throw "GATE_C_LITE_STOP_INVALID_${Label}_JSON" }
}
function Resolve-ApprovalEvidencePath([string]$ApprovalPath, [string]$EvidencePath) {
    if ([System.IO.Path]::IsPathRooted($EvidencePath)) { return Full $EvidencePath }
    return Full (Join-Path (Split-Path -Parent (Full $ApprovalPath)) $EvidencePath)
}
function Write-Result($Result) {
    $reportFull = [System.IO.Path]::GetFullPath($ReportPath)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportFull) | Out-Null
    $Result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportFull -Encoding UTF8
    Write-Output "GATE_C_LITE_REPORT=$reportFull"
}

$result = [ordered]@{
    schema = 'pr6-gate-c-lite-smoke-result/1'
    generated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    policy_id = 'PR6-C-LITE-20260919'
    policy_status = 'UNKNOWN'
    execution_status = 'UNKNOWN'
    evidence_class = if ($TestOnly) { 'TEST_ONLY' } else { 'PRODUCTION' }
    c1_bootstrap = 'NOT_RUN'
    c2_health = 'NOT_RUN'
    c3_backup_restore = 'NOT_RUN'
    c4_safety = 'NOT_RUN'
    gate_c_lite = 'NOT_RUN'
    deferred_tests = @('CLEAN_WINDOWS_BOOTSTRAP', 'WINDOWS_LOCK_LOGOFF_REBOOT_OPERATIONAL_TESTS', 'WINDOWS_RECOVERY', 'CROSS_MACHINE_TAKEOVER', 'LONG_DURATION_STABILITY')
    merge_ready = 'NO'
    activation_ready = 'NO'
    safety = [ordered]@{
        live_trading = 'NO'
        order_placement = 'NO'
        execution_authority = 'NONE'
        trade_control_authority = 'NONE'
        scheduler = 'DISABLED'
        production_runtime_change = 'NO'
    }
}

try {
    Require-Path $PolicyApprovalPath 'POLICY_APPROVAL'
    Require-Path $ExecutionApprovalPath 'EXECUTION_APPROVAL'
    $policyApprovalFull = Full $PolicyApprovalPath
    $executionApprovalFull = Full $ExecutionApprovalPath
    if ($policyApprovalFull -eq $executionApprovalFull) {
        throw 'GATE_C_LITE_STOP_APPROVAL_RECORDS_NOT_INDEPENDENT'
    }
    $policyApproval = Get-Content -Raw -LiteralPath $PolicyApprovalPath | ConvertFrom-Json
    $executionApproval = Get-Content -Raw -LiteralPath $ExecutionApprovalPath | ConvertFrom-Json
    $result.policy_status = if (Has-Property $policyApproval 'policy_status') { [string]$policyApproval.policy_status } else { 'MISSING' }
    $result.execution_status = if (Has-Property $executionApproval 'execution_status') { [string]$executionApproval.execution_status } else { 'MISSING' }
    if (-not $OperatorApprovalConfirmed) { throw 'GATE_C_LITE_STOP_OPERATOR_CONFIRMATION_REQUIRED' }
    if (-not (Has-Property $policyApproval 'schema') -or [string]$policyApproval.schema -ne 'pr6-gate-c-lite-policy-approval/1' -or
        -not (Has-Property $policyApproval 'approval_type') -or [string]$policyApproval.approval_type -ne 'POLICY_APPROVAL' -or
        $result.policy_status -ne 'APPROVED' -or [string]$policyApproval.approved_scope -ne 'MSI_ACCEPTANCE_RUNTIME_C1_C4_ONLY') {
        throw 'GATE_C_LITE_STOP_POLICY_APPROVAL_INVALID'
    }
    if (-not (Has-Property $executionApproval 'schema') -or [string]$executionApproval.schema -ne 'pr6-gate-c-lite-execution-approval/1' -or
        -not (Has-Property $executionApproval 'approval_type') -or [string]$executionApproval.approval_type -ne 'EXECUTION_APPROVAL' -or
        $result.execution_status -ne 'APPROVED' -or [string]$executionApproval.approved_scope -ne 'MSI_ACCEPTANCE_RUNTIME_C1_C4_ONLY') {
        throw 'GATE_C_LITE_STOP_EXECUTION_APPROVAL_INVALID'
    }
    foreach ($approval in @($policyApproval, $executionApproval)) {
        if (-not (Has-Property $approval 'proposal_id') -or [string]$approval.proposal_id -ne 'PR6-C-LITE-20260919') {
            throw 'GATE_C_LITE_STOP_APPROVAL_POLICY_ID_MISMATCH'
        }
        foreach ($field in @('operator_id', 'approved_at_utc', 'approved_scope')) {
            if (-not (Has-Property $approval $field) -or [string]$approval.$field -eq '') {
                throw "GATE_C_LITE_STOP_APPROVAL_MISSING_$field"
            }
        }
    }
    foreach ($field in @('gate_a', 'gate_b', 'package_trust', 'non_trading_enforcement', 'mt5_preflight', 'real_telemetry')) {
        if (Has-Property $policyApproval $field) { throw "GATE_C_LITE_STOP_POLICY_MIXES_EXECUTION_$field" }
    }
    $expectedDeferred = @('CLEAN_WINDOWS_BOOTSTRAP', 'WINDOWS_LOCK_LOGOFF_REBOOT_OPERATIONAL_TESTS', 'WINDOWS_RECOVERY', 'CROSS_MACHINE_TAKEOVER', 'LONG_DURATION_STABILITY')
    if (-not (Has-Property $policyApproval 'deferred_tests') -or (@($policyApproval.deferred_tests | ForEach-Object { [string]$_ }) -join '|') -ne ($expectedDeferred -join '|')) {
        throw 'GATE_C_LITE_STOP_POLICY_DEFERRED_TESTS_MISMATCH'
    }
    if (-not (Has-Property $policyApproval 'deferred_tests_remain_open') -or [string]$policyApproval.deferred_tests_remain_open -ne 'YES' -or
        -not (Has-Property $policyApproval 'acknowledged_limits') -or [string]$policyApproval.acknowledged_limits -ne 'YES') {
        throw 'GATE_C_LITE_STOP_POLICY_LIMITS_NOT_ACKNOWLEDGED'
    }
    if (-not (Has-Property $policyApproval 'merge_authority') -or [string]$policyApproval.merge_authority -ne 'NONE' -or
        -not (Has-Property $policyApproval 'activation_authority') -or [string]$policyApproval.activation_authority -ne 'NONE') {
        throw 'GATE_C_LITE_STOP_POLICY_AUTHORITY_NOT_NONE'
    }
    if (-not (Has-Property $executionApproval 'merge_authority') -or [string]$executionApproval.merge_authority -ne 'NONE' -or
        -not (Has-Property $executionApproval 'activation_authority') -or [string]$executionApproval.activation_authority -ne 'NONE') {
        throw 'GATE_C_LITE_STOP_EXECUTION_AUTHORITY_NOT_NONE'
    }
    $required = [ordered]@{
        gate_a = 'PASS'
        gate_b = 'PASS'
        package_trust = 'PASS'
        non_trading_enforcement = 'PASS'
        mt5_preflight = 'PASS'
        real_telemetry = 'PASS'
        acceptance_roots_empty_and_separate = 'PASS'
        scheduler_disabled = 'PASS'
        execution_authority_none = 'PASS'
    }
    if (-not (Has-Property $executionApproval 'prerequisites')) { throw 'GATE_C_LITE_STOP_EXECUTION_PREREQUISITES_MISSING' }
    foreach ($key in $required.Keys) {
        if (-not (Has-Property $executionApproval.prerequisites $key) -or [string]$executionApproval.prerequisites.$key -ne $required[$key]) {
            throw "GATE_C_LITE_STOP_EXECUTION_PRECONDITION_$key"
        }
    }
    if (-not (Has-Property $executionApproval 'evidence')) { throw 'GATE_C_LITE_STOP_EXECUTION_EVIDENCE_MISSING' }
    foreach ($key in @('gate_a', 'gate_b', 'package_trust', 'non_trading_enforcement', 'mt5_preflight', 'real_telemetry')) {
        if (-not (Has-Property $executionApproval.evidence $key) -or [string]$executionApproval.evidence.$key -eq '') {
            throw "GATE_C_LITE_STOP_EXECUTION_EVIDENCE_$key"
        }
        Require-Path (Resolve-ApprovalEvidencePath $ExecutionApprovalPath ([string]$executionApproval.evidence.$key)) "EXECUTION_EVIDENCE_$key"
    }
    if (-not (Has-Property $executionApproval 'c3_data_source')) { throw 'GATE_C_LITE_STOP_C3_DATA_SOURCE_DECLARATION_MISSING' }
    $c3Approval = $executionApproval.c3_data_source
    if ($null -eq $c3Approval -or -not (Has-Property $c3Approval 'mode') -or [string]$c3Approval.mode -notin @('VERIFIED_REAL_COPIED', 'ISOLATED_FIXTURE')) {
        throw 'GATE_C_LITE_STOP_C3_DATA_SOURCE_MODE_INVALID'
    }
    foreach ($field in @('evidence_path', 'runtime_path', 'runtime_sha256')) {
        if (-not (Has-Property $c3Approval $field) -or [string]$c3Approval.$field -eq '') {
            throw "GATE_C_LITE_STOP_C3_DATA_SOURCE_$field"
        }
    }
    if ([string]$c3Approval.runtime_sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'GATE_C_LITE_STOP_C3_DATA_SOURCE_SHA_INVALID' }
    Require-Path (Resolve-ApprovalEvidencePath $ExecutionApprovalPath ([string]$c3Approval.evidence_path)) 'C3_DATA_SOURCE_EVIDENCE'
    if ([string]$c3Approval.mode -eq 'VERIFIED_REAL_COPIED') {
        if (-not (Has-Property $c3Approval 'contract_copy_authorized') -or -not [bool]$c3Approval.contract_copy_authorized -or
            -not (Has-Property $c3Approval 'verified_real_data') -or -not [bool]$c3Approval.verified_real_data) {
            throw 'GATE_C_LITE_STOP_C3_REAL_COPY_NOT_AUTHORIZED'
        }
        if ($TestOnly) { throw 'GATE_C_LITE_STOP_C3_REAL_DATA_CANNOT_BE_TEST_ONLY' }
    } else {
        if (-not $TestOnly -or -not (Has-Property $c3Approval 'isolated') -or -not [bool]$c3Approval.isolated -or
            -not (Has-Property $c3Approval 'production_use') -or [bool]$c3Approval.production_use) {
            throw 'GATE_C_LITE_STOP_C3_FIXTURE_NOT_ISOLATED'
        }
    }

    $installFull = Full $InstallRoot
    $runtimeFull = Full $RuntimeRoot
    $opsFull = Full $OpsRoot
    $packageFull = Full $PackagePath
    $productionFull = Full $ProductionRuntimeRoot
    if ($runtimeFull -eq $opsFull -or $runtimeFull -eq $installFull -or $opsFull -eq $installFull) {
        throw 'GATE_C_LITE_STOP_ROOTS_NOT_SEPARATE'
    }
    if ($runtimeFull -eq $productionFull -or $opsFull -eq $productionFull) {
        throw 'GATE_C_LITE_STOP_ACCEPTANCE_EQUALS_PRODUCTION'
    }
    if ($runtimeFull.StartsWith($installFull + '\', [System.StringComparison]::OrdinalIgnoreCase) -or
        $opsFull.StartsWith($installFull + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'GATE_C_LITE_STOP_ACCEPTANCE_ROOT_INSIDE_SOURCE'
    }
    Require-Path $InstallRoot 'INSTALL_ROOT'
    Require-Path (Join-Path $InstallRoot '.git') 'SOURCE_GIT'
    Require-Path $PackagePath 'PACKAGE'
    Require-EmptyOrMissing $RuntimeRoot 'RUNTIME_ROOT'
    Require-EmptyOrMissing $OpsRoot 'OPS_ROOT'
    if ($RestoreRoot -and (Test-Path -LiteralPath $RestoreRoot)) { Require-EmptyOrMissing $RestoreRoot 'RESTORE_ROOT' }

    $actualSha = ((& git -C $InstallRoot rev-parse --verify HEAD 2>$null) -join [Environment]::NewLine).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $actualSha -ne $ExpectedSourceSha) {
        throw "GATE_C_LITE_STOP_SOURCE_SHA_$actualSha"
    }
    $sourceStatus = (& git -C $InstallRoot status --porcelain --untracked-files=all 2>$null) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0 -or $sourceStatus.Trim().Length -gt 0) {
        throw 'GATE_C_LITE_STOP_SOURCE_NOT_CLEAN'
    }
    $manifestPath = Join-Path $PackagePath 'manifest.json'
    Require-Path $manifestPath 'PACKAGE_MANIFEST'
    $manifestSha = Sha $manifestPath
    if ($manifestSha -ne $ExpectedManifestSha) { throw 'GATE_C_LITE_STOP_PACKAGE_MANIFEST_SHA' }
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    if ([string]$manifest.code.approved_git_sha -ne $ExpectedSourceSha) { throw 'GATE_C_LITE_STOP_PACKAGE_SOURCE_BINDING' }
    if ([string]$manifest.artifacts.ea_ex5.sha256 -ne $ExpectedEx5Sha) { throw 'GATE_C_LITE_STOP_PACKAGE_EX5_BINDING' }
    if ([string]$manifest.artifacts.ea_preset.sha256 -ne $ExpectedPresetSha) { throw 'GATE_C_LITE_STOP_PACKAGE_PRESET_BINDING' }

    $verify = Run-Python @('-m', 'agent.phase3', 'verify-forward-package', '--package-path', $packageFull, '--expected-git-sha', $ExpectedSourceSha, '--expected-trusted-manifest-digest', $TrustedManifestDigest)
    if ($verify.exit_code -ne 0) { throw "GATE_C_LITE_STOP_PACKAGE_VERIFY_$($verify.text)" }
    $result.package_verification = 'PASS'

    $bootstrapScript = Join-Path $PSScriptRoot 'bootstrap_forward_node.ps1'
    Require-Path $bootstrapScript 'BOOTSTRAP_SCRIPT'
    & $bootstrapScript -InstallRoot $installFull -RuntimeRoot $runtimeFull -OpsRoot $opsFull -PackagePath $packageFull -ExpectedGitSha $ExpectedSourceSha -ExpectedTrustedManifestDigest $TrustedManifestDigest -PythonPath $PythonPath
    if ($LASTEXITCODE -ne 0) { throw 'GATE_C_LITE_STOP_BOOTSTRAP_FAILED' }
    $configPath = Join-Path $runtimeFull 'config\forward.json'
    Require-Path $configPath 'RUNTIME_CONFIG'
    $result.c1_bootstrap = 'PASS'

    $statusFile = Join-Path $opsFull 'gate-c-lite-status-runtime.json'
    $healthFile = Join-Path $opsFull 'gate-c-lite-health.json'
    $status = Run-Python @('-m', 'agent.phase3', 'status-runtime', '--runtime-config', $configPath, '--json')
    if ($status.exit_code -ne 0) { throw "GATE_C_LITE_STOP_STATUS_$($status.text)" }
    $status.text | Set-Content -LiteralPath $statusFile -Encoding UTF8
    $statusJson = Parse-JsonOutput $status 'STATUS'
    $health = Run-Python @('-m', 'agent.phase3', 'ops-health', '--runtime-config', $configPath, '--ops-root', $opsFull)
    if ($health.exit_code -ne 0) { throw "GATE_C_LITE_STOP_HEALTH_$($health.text)" }
    $health.text | Set-Content -LiteralPath $healthFile -Encoding UTF8
    $healthJson = Parse-JsonOutput $health 'HEALTH'
    if ([bool]$statusJson.live_execution_enabled -or [string]$statusJson.execution_mode -ne 'NONE') {
        throw 'GATE_C_LITE_STOP_STATUS_SAFETY'
    }
    if ([bool]$statusJson.collector_running -or $null -ne $statusJson.run_id) {
        throw 'GATE_C_LITE_STOP_UNEXPECTED_ACTIVE_RUNTIME'
    }
    if ([string]$statusJson.code_sha -ne $ExpectedSourceSha) {
        throw 'GATE_C_LITE_STOP_STATUS_SOURCE_IDENTITY'
    }
    if ([string]$healthJson.health_status -eq 'CRITICAL') { throw 'GATE_C_LITE_STOP_HEALTH_CRITICAL' }
    $result.c2_health = 'PASS'
    $result.health_state = [string]$healthJson.health_status
    $result.state_identity = [ordered]@{
        source_sha = [string]$statusJson.code_sha
        run_id = $statusJson.run_id
        collector_running = [bool]$statusJson.collector_running
        source_offset = $statusJson.source_offset
        telemetry_status = [string]$statusJson.telemetry_status
    }

    $c3Ready = $true
    $c3RuntimePath = Full ([string]$statusJson.telemetry_source)
    $declaredC3RuntimePath = Full ([string]$c3Approval.runtime_path)
    $result.c3_data_source = [ordered]@{
        mode = [string]$c3Approval.mode
        declared_runtime_path = $declaredC3RuntimePath
        runtime_path = $c3RuntimePath
        evidence_path = [string]$c3Approval.evidence_path
    }
    if ($c3RuntimePath -ne $declaredC3RuntimePath -or
        -not $c3RuntimePath.StartsWith($runtimeFull + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        $result.c3_block_reason = 'C3_DATA_SOURCE_NOT_IN_ACCEPTANCE_RUNTIME'
        $c3Ready = $false
    } elseif (-not (Test-Path -LiteralPath $c3RuntimePath -PathType Leaf)) {
        $result.c3_block_reason = 'C3_DATA_SOURCE_NOT_AVAILABLE'
        $c3Ready = $false
    } elseif ((Sha $c3RuntimePath) -ne ([string]$c3Approval.runtime_sha256).ToLowerInvariant()) {
        $result.c3_block_reason = 'C3_DATA_SOURCE_CHECKSUM_MISMATCH'
        $c3Ready = $false
    } elseif ((Get-Item -LiteralPath $c3RuntimePath).Length -le 0 -or $null -eq $statusJson.source_offset) {
        $result.c3_block_reason = 'C3_DATA_SOURCE_CHECKPOINT_NOT_AVAILABLE'
        $c3Ready = $false
    } elseif ([int64]$statusJson.raw_observation_count -le 0) {
        $result.c3_block_reason = 'C3_DATA_SOURCE_REAL_RECORD_NOT_VERIFIED'
        $c3Ready = $false
    }
    if (-not $c3Ready) {
        $result.c3_backup_restore = 'BLOCKED'
    } else {
        $backupBase = if ($BackupRoot) { Full $BackupRoot } else { Full (Join-Path $opsFull 'backups') }
        $restoreBase = if ($RestoreRoot) { Full $RestoreRoot } else { Full (Join-Path $opsFull 'isolated-restore') }
        Require-EmptyOrMissing $restoreBase 'RESTORE_ROOT'
        try {
            $backupId = 'gate-c-lite-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
            $backup = Run-Python @('-m', 'agent.phase3', 'backup-forward-runtime', '--runtime-config', $configPath, '--ops-root', $opsFull, '--backup-root', $backupBase, '--backup-id', $backupId)
            $backupJson = Parse-JsonOutput $backup 'BACKUP'
            if ([string]$backupJson.status -ne 'BACKUP_VALID') {
                throw "GATE_C_LITE_STOP_BACKUP_NOT_VALID_$($backup.text)"
            }
            $backupPath = Full ([string]$backupJson.backup_path)
            $verified = Run-Python @('-m', 'agent.phase3', 'verify-forward-backup', '--backup-path', $backupPath, '--source-path', $c3RuntimePath)
            $verifiedJson = Parse-JsonOutput $verified 'BACKUP_VERIFY'
            if ([string]$verifiedJson.status -ne 'BACKUP_VALID') { throw 'GATE_C_LITE_STOP_BACKUP_VERIFY' }
            $restore = Run-Python @('-m', 'agent.phase3', 'restore-forward-backup', '--backup-path', $backupPath, '--target-root', $restoreBase, '--mode', 'isolated')
            $restoreJson = Parse-JsonOutput $restore 'RESTORE'
            if ([string]$restoreJson.status -ne 'RESTORE_VALIDATED_ISOLATED') { throw 'GATE_C_LITE_STOP_RESTORE' }
            $backupManifest = Get-Content -Raw -LiteralPath (Join-Path $backupPath 'backup_manifest.json') | ConvertFrom-Json
            $restoreManifest = Get-Content -Raw -LiteralPath (Join-Path $restoreBase 'restore_manifest.json') | ConvertFrom-Json
            if ([string]$restoreManifest.verification.status -ne 'BACKUP_VALID' -or
                [string]$restoreManifest.verification.source_identity -ne [string]$backupManifest.source.identity -or
                [int64]$restoreManifest.verification.checkpoint_offset_bytes -ne [int64]$backupManifest.source.checkpoint_offset_bytes) {
                throw 'GATE_C_LITE_STOP_RESTORE_IDENTITY_COMPARE'
            }
            $result.c3_backup_restore = if ($TestOnly) { 'TEST_ONLY_PASS' } else { 'PASS' }
            $result.backup_restore = [ordered]@{
                backup_path = $backupPath
                verify_status = [string]$verifiedJson.status
                restore_status = [string]$restoreJson.status
                source_identity = [string]$backupManifest.source.identity
                checkpoint_offset_bytes = [int64]$backupManifest.source.checkpoint_offset_bytes
                sqlite_integrity = [string]$restoreJson.database_integrity
                fixture_only = [bool]$TestOnly
            }
        } catch {
            $result.c3_backup_restore = 'BLOCKED'
            $result.c3_block_reason = $_.Exception.Message
        }
    }

    $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    if ([string]$config.execution_authority -ne 'NONE' -or [string]$config.trade_control_authority -ne 'NONE' -or
        [bool]$config.live_execution_enabled -or [string]$config.execution_mode -ne 'NONE') {
        throw 'GATE_C_LITE_STOP_CONFIG_SAFETY'
    }
    $authorizationPath = Join-Path $runtimeFull 'config\forward_authorization.json'
    $runPath = Join-Path $runtimeFull 'state\current_run.json'
    if (Test-Path -LiteralPath $authorizationPath -or Test-Path -LiteralPath $runPath) {
        throw 'GATE_C_LITE_STOP_AUTHORIZATION_OR_RUN_CREATED'
    }
    if (-not (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue)) {
        throw 'GATE_C_LITE_STOP_SCHEDULER_QUERY_UNAVAILABLE'
    }
    $matchingTasks = @(Get-ScheduledTask | Where-Object { $_.TaskName -match '(?i)(build.?bot|phase3|forward)' })
    if ($matchingTasks.Count -gt 0) { throw 'GATE_C_LITE_STOP_SCHEDULER_TASK_PRESENT' }
    $result.c4_safety = if ($TestOnly) { 'TEST_ONLY_PASS' } else { 'PASS' }
    $result.safety.scheduler_matching_tasks = @()
    $result.safety.production_runtime_root = $productionFull
    $result.safety.production_runtime_touched_by_runner = $false
    if ([string]$result.c3_backup_restore -eq 'BLOCKED') {
        $result.gate_c_lite = 'BLOCKED'
        $result.notes = 'C3 blocked because eligible verified data/checkpoint or backup/restore evidence was unavailable.'
        Write-Result $result
        Write-Error "GATE_C_LITE=BLOCKED $($result.c3_block_reason)"
        exit 2
    }
    $result.gate_c_lite = if ($TestOnly) { 'TEST_ONLY_PASS' } else { 'PRODUCTION_SMOKE_PASS' }
    $result.notes = if ($TestOnly) { 'Fixture/test-only result; not production acceptance.' } else { 'Bounded MSI smoke only; deferred tests remain open.' }
    Write-Result $result
    Write-Output "GATE_C_LITE=$($result.gate_c_lite)"
    exit 0
}
catch {
    $result.error = $_.Exception.Message
    if ([string]$result.c1_bootstrap -eq 'NOT_RUN') { $result.c1_bootstrap = 'BLOCKED' }
    if ([string]$result.c2_health -eq 'NOT_RUN') { $result.c2_health = 'BLOCKED' }
    if ([string]$result.c3_backup_restore -eq 'NOT_RUN') { $result.c3_backup_restore = 'BLOCKED' }
    if ([string]$result.c4_safety -eq 'NOT_RUN') { $result.c4_safety = 'BLOCKED' }
    $result.gate_c_lite = 'BLOCKED'
    $result.merge_ready = 'NO'
    $result.activation_ready = 'NO'
    Write-Result $result
    Write-Error "GATE_C_LITE=BLOCKED $($result.error)"
    exit 2
}
