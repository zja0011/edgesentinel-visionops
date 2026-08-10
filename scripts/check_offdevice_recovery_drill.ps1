param(
    [double]$MaximumDrillAgeDays = 45.0,
    [string]$StorePath = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $StorePath) {
    $StorePath = Join-Path $ProjectRoot "data\recovery\off-device"
}
$StorePath = [IO.Path]::GetFullPath($StorePath)
$StatusPath = Join-Path $StorePath "restore-drill-status.json"
if ($MaximumDrillAgeDays -lt 1 -or $MaximumDrillAgeDays -gt 366) {
    throw "MaximumDrillAgeDays must be between 1 and 366"
}
foreach ($Path in @($StorePath, $StatusPath)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Off-device recovery drill status is unavailable"
    }
    if ((Get-Item -LiteralPath $Path -Force).Attributes -band
        [IO.FileAttributes]::ReparsePoint) {
        throw "Off-device recovery drill status cannot traverse a reparse point"
    }
}
$Status = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
$FinishedAt = [DateTimeOffset]::Parse([string]$Status.finished_at)
$DrillAgeDays = [Math]::Round(
    ([DateTimeOffset]::Now - $FinishedAt).TotalDays,
    3
)
$Issues = New-Object System.Collections.Generic.List[string]
if ([string]$Status.status -ne "PASS") {
    $Issues.Add("LAST_RESTORE_DRILL_FAILED")
}
if ($DrillAgeDays -lt -0.004 -or $DrillAgeDays -gt $MaximumDrillAgeDays) {
    $Issues.Add("RESTORE_DRILL_STALE")
}
if ([string]$Status.mode -ne "ISOLATED_RESTORE_DRILL" -or
    -not [bool]$Status.isolated -or
    [bool]$Status.production_modified) {
    $Issues.Add("RESTORE_DRILL_BOUNDARY_INVALID")
}
if ([int64]$Status.restored_file_count -le 0 -or
    [int64]$Status.restored_file_count -ne
        [int64]$Status.post_restore_verified_files -or
    -not [bool]$Status.sqlite_consistent) {
    $Issues.Add("RESTORE_DRILL_VERIFICATION_INVALID")
}
if ([bool]$Status.credentials_exposed -or
    [bool]$Status.plaintext_persisted) {
    $Issues.Add("RESTORE_DRILL_SECURITY_INVALID")
}

Write-Host ""
Write-Host "Off-device Recovery Drill Health summary:"
Write-Host "Status:" $(if ($Issues.Count -eq 0) { "PASS" } else { "FAIL" })
Write-Host "Drill ID:" $Status.drill_id
Write-Host "Backup ID:" $Status.backup_id
Write-Host "Drill age days:" $DrillAgeDays
Write-Host "Maximum drill age days:" $MaximumDrillAgeDays
Write-Host "Files restored:" $Status.restored_file_count
Write-Host "Post-restore verified files:" $Status.post_restore_verified_files
Write-Host "SQLite consistent:" $Status.sqlite_consistent
Write-Host "Production modified: False"
Write-Host "Credentials exposed: False"
Write-Host "Plaintext persisted: False"
Write-Host "Issues:" $Issues.Count
if ($Issues.Count -gt 0) {
    Write-Host "Issue codes:" ([string]::Join(",", $Issues.ToArray()))
    throw "Off-device recovery drill health check failed"
}
Write-Host "Off-device Recovery Drill Health smoke test passed."
