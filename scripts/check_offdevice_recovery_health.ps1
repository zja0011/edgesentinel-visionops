param(
    [double]$MaximumSyncAgeHours = 30.0,
    [double]$MaximumBackupAgeHours = 192.0,
    [double]$MaximumDrillAgeDays = 45.0,
    [int]$MaximumEncryptedBackups = 4,
    [long]$MaximumEncryptedBytes = 536870912,
    [string]$TaskName = "EdgeSentinel Off-device Recovery Sync",
    [switch]$RequireEventLog,
    [string]$EventLogSource = "EdgeSentinel Recovery"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$StorePath = Join-Path $ProjectRoot "data\recovery\off-device"
$StatusPath = Join-Path $StorePath "scheduled-sync-status.json"
$AlertPath = Join-Path $StorePath "recovery-health-alert.json"
$DrillStatusPath = Join-Path $StorePath "restore-drill-status.json"
$EventSourceRegistryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Application\$EventLogSource"

if ($MaximumSyncAgeHours -lt 1 -or $MaximumSyncAgeHours -gt 168 -or
    $MaximumBackupAgeHours -lt 1 -or $MaximumBackupAgeHours -gt 720 -or
    $MaximumDrillAgeDays -lt 1 -or $MaximumDrillAgeDays -gt 366 -or
    $MaximumEncryptedBackups -lt 1 -or $MaximumEncryptedBackups -gt 100 -or
    $MaximumEncryptedBytes -lt 104857600 -or
    $MaximumEncryptedBytes -gt 10737418240) {
    throw "Recovery health age targets are outside the supported bounds"
}
foreach ($Path in @(
    $ProjectRoot, $StorePath, $StatusPath, $AlertPath, $DrillStatusPath
)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Recovery health state is incomplete: $Path"
    }
    if ((Get-Item -LiteralPath $Path -Force).Attributes -band
        [IO.FileAttributes]::ReparsePoint) {
        throw "Recovery health state cannot traverse a reparse point"
    }
}

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$TaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
$Status = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
$Alert = Get-Content -LiteralPath $AlertPath -Raw | ConvertFrom-Json
$DrillStatus = Get-Content -LiteralPath $DrillStatusPath -Raw |
    ConvertFrom-Json
$Now = [DateTimeOffset]::Now
$FinishedAt = [DateTimeOffset]::Parse([string]$Status.finished_at)
$BackupCreatedAt = [DateTimeOffset]::Parse(
    [string]$Status.latest_backup_created_at
)
$SyncAgeHours = [Math]::Round(($Now - $FinishedAt).TotalHours, 3)
$BackupAgeHours = [Math]::Round(($Now - $BackupCreatedAt).TotalHours, 3)
$DrillFinishedAt = [DateTimeOffset]::Parse(
    [string]$DrillStatus.finished_at
)
$DrillAgeDays = [Math]::Round(($Now - $DrillFinishedAt).TotalDays, 3)
$CapacityRecords = @(Get-ChildItem -LiteralPath $StorePath -Force -File |
    Where-Object { $_.Name -match '^dr_[0-9a-f]{32}\.esdr\.json$' } |
    ForEach-Object {
        $Metadata = Get-Content -LiteralPath $_.FullName -Raw |
            ConvertFrom-Json
        $BackupId = [string]$Metadata.backup_id
        $ArtifactPath = Join-Path $StorePath (
            [string]$Metadata.artifact_file
        )
        if ($BackupId -notmatch '^dr_[0-9a-f]{32}$' -or
            $_.Name -ne ($BackupId + ".esdr.json") -or
            [string]$Metadata.artifact_file -ne ($BackupId + ".esdr") -or
            [int64]$Metadata.artifact_bytes -le 0 -or
            [bool]$Metadata.credentials_included -or
            [bool]$Metadata.plaintext_persisted -or
            -not (Test-Path -LiteralPath $ArtifactPath -PathType Leaf) -or
            ((Get-Item -LiteralPath $ArtifactPath -Force).Attributes -band
                [IO.FileAttributes]::ReparsePoint) -or
            (Get-Item -LiteralPath $ArtifactPath).Length -ne
                [int64]$Metadata.artifact_bytes) {
            throw "Encrypted recovery capacity metadata is invalid"
        }
        [PSCustomObject]@{
            BackupId = $BackupId
            ArtifactBytes = [int64]$Metadata.artifact_bytes
        }
    })
$EncryptedBackupCount = $CapacityRecords.Count
$EncryptedBackupBytes = [int64](
    ($CapacityRecords | Measure-Object -Property ArtifactBytes -Sum).Sum
)
$Issues = New-Object System.Collections.Generic.List[string]

if ([string]$Status.status -ne "SUCCEEDED") {
    $Issues.Add("LAST_SYNC_FAILED")
}
if ($SyncAgeHours -lt -0.083 -or $SyncAgeHours -gt $MaximumSyncAgeHours) {
    $Issues.Add("SYNC_STATUS_STALE")
}
if ($BackupAgeHours -lt -0.083 -or
    $BackupAgeHours -gt $MaximumBackupAgeHours) {
    $Issues.Add("RECOVERY_POINT_STALE")
}
if ($EncryptedBackupCount -gt $MaximumEncryptedBackups) {
    $Issues.Add("RECOVERY_CAPACITY_COUNT_EXCEEDED")
}
if ($EncryptedBackupBytes -gt $MaximumEncryptedBytes) {
    $Issues.Add("RECOVERY_CAPACITY_BYTES_EXCEEDED")
}
if ([string]$DrillStatus.status -ne "PASS") {
    $Issues.Add("LAST_RESTORE_DRILL_FAILED")
}
if ($DrillAgeDays -lt -0.004 -or $DrillAgeDays -gt $MaximumDrillAgeDays) {
    $Issues.Add("RESTORE_DRILL_STALE")
}
if ([string]$DrillStatus.mode -ne "ISOLATED_RESTORE_DRILL" -or
    -not [bool]$DrillStatus.isolated -or
    [bool]$DrillStatus.production_modified -or
    [bool]$DrillStatus.credentials_exposed -or
    [bool]$DrillStatus.plaintext_persisted -or
    -not [bool]$DrillStatus.sqlite_consistent -or
    [int64]$DrillStatus.restored_file_count -le 0 -or
    [int64]$DrillStatus.restored_file_count -ne
        [int64]$DrillStatus.post_restore_verified_files) {
    $Issues.Add("RESTORE_DRILL_VERIFICATION_INVALID")
}
if ([string]$Alert.state -ne "CLEARED") {
    $Issues.Add("RECOVERY_ALERT_ACTIVE")
}
if ($RequireEventLog -and -not (Test-Path -LiteralPath $EventSourceRegistryPath)) {
    $Issues.Add("EVENT_LOG_SOURCE_UNAVAILABLE")
}
if ([string]$Alert.event_log_delivery -eq "FAILED") {
    $Issues.Add("EVENT_LOG_DELIVERY_FAILED")
}
if ($Task.State -notin @("Ready", "Running")) {
    $Issues.Add("SCHEDULED_TASK_UNAVAILABLE")
}
if ($Task.State -ne "Running" -and [int64]$TaskInfo.LastTaskResult -ne 0) {
    $Issues.Add("SCHEDULED_TASK_LAST_RUN_FAILED")
}

Write-Host ""
Write-Host "Off-device Recovery Health summary:"
Write-Host "Status:" $(if ($Issues.Count -eq 0) { "PASS" } else { "FAIL" })
Write-Host "Task state:" $Task.State
Write-Host "Task last result:" $TaskInfo.LastTaskResult
Write-Host "Last sync status:" $Status.status
Write-Host "Sync age hours:" $SyncAgeHours
Write-Host "Latest backup ID:" $Status.latest_backup_id
Write-Host "Backup age hours:" $BackupAgeHours
Write-Host "Maximum sync age hours:" $MaximumSyncAgeHours
Write-Host "Maximum backup age hours:" $MaximumBackupAgeHours
Write-Host "Encrypted backup count:" $EncryptedBackupCount
Write-Host "Maximum encrypted backups:" $MaximumEncryptedBackups
Write-Host "Encrypted backup bytes:" $EncryptedBackupBytes
Write-Host "Maximum encrypted bytes:" $MaximumEncryptedBytes
Write-Host "Latest drill ID:" $DrillStatus.drill_id
Write-Host "Drill age days:" $DrillAgeDays
Write-Host "Maximum drill age days:" $MaximumDrillAgeDays
Write-Host "Drill status:" $DrillStatus.status
Write-Host "Alert state:" $Alert.state
Write-Host "Event log required:" ([bool]$RequireEventLog)
Write-Host "Event source installed:" (Test-Path -LiteralPath $EventSourceRegistryPath)
Write-Host "Event log delivery:" $Alert.event_log_delivery
Write-Host "Issues:" $Issues.Count
Write-Host "Credentials exposed: False"
Write-Host "Plaintext persisted: False"
if ($Issues.Count -gt 0) {
    Write-Host "Issue codes:" ([string]::Join(",", $Issues.ToArray()))
    throw "Off-device recovery health check failed"
}
Write-Host "Off-device Recovery Health smoke test passed."
