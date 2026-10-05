[CmdletBinding()]
param(
    # Thư mục FILE_COMMON chứa luồng opportunity của EA.
    [string]$SourceDir = (Join-Path $env:APPDATA 'MetaQuotes\Terminal\Common\Files\phase3\opportunities'),
    [string]$DestinationRoot = 'D:\Trading\build-bot-runtime\phase4-data',
    # Chỉ chụp các stream thu dữ liệu Phase 4; V26/V63 đã có collector riêng.
    [string[]]$MagicNumbers = @('26072701', '26072702', '26072703')
)

# Chụp snapshot read-only các file JSONL đang được EA append và ghi hash vào manifest append-only.
# Snapshot chứng minh dữ liệu đã tồn tại tại thời điểm chụp (known-at), phục vụ Phase 4 design §6.3/§6.6.
# Script không sửa, không xóa và không cắt file nguồn.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$stamp = (Get-Date).ToUniversalTime()
$day = $stamp.ToString('yyyyMMdd')
$snapshotDir = Join-Path $DestinationRoot (Join-Path 'snapshots' $day)
$manifestPath = Join-Path $DestinationRoot 'manifest.csv'
New-Item -ItemType Directory -Force -Path $snapshotDir | Out-Null
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Set-Content -LiteralPath $manifestPath -Encoding UTF8 -Value 'snapshot_utc,file_name,size_bytes,line_count,sha256,snapshot_path'
}

$results = @()
foreach ($magic in $MagicNumbers) {
    $pattern = "Mentor_RSI_MTF_${magic}_*.jsonl"
    foreach ($file in @(Get-ChildItem -LiteralPath $SourceDir -Filter $pattern -File -ErrorAction SilentlyContinue)) {
        $target = Join-Path $snapshotDir $file.Name
        # EA giữ file mở với share read/write; đọc bằng FileShare.ReadWrite để không chặn EA ghi tiếp.
        $reader = [System.IO.File]::Open($file.FullName, 'Open', 'Read', 'ReadWrite')
        try {
            $writer = [System.IO.File]::Open($target, 'Create', 'Write', 'None')
            try {
                $reader.CopyTo($writer)
            } finally {
                $writer.Dispose()
            }
        } finally {
            $reader.Dispose()
        }
        $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
        $size = (Get-Item -LiteralPath $target).Length
        $lines = 0
        foreach ($line in [System.IO.File]::ReadLines($target)) {
            if ($line.Trim()) { $lines++ }
        }
        $row = '{0},{1},{2},{3},{4},{5}' -f $stamp.ToString('o'), $file.Name, $size, $lines, $hash, $target
        Add-Content -LiteralPath $manifestPath -Encoding UTF8 -Value $row
        $results += [pscustomobject]@{ file = $file.Name; size_bytes = $size; line_count = $lines; sha256 = $hash }
    }
}

[pscustomobject]@{
    status = $(if ($results.Count -gt 0) { 'SNAPSHOT_WRITTEN' } else { 'NO_SOURCE_FILES' })
    snapshot_utc = $stamp.ToString('o')
    snapshot_dir = $snapshotDir
    files = $results
} | ConvertTo-Json -Depth 4
