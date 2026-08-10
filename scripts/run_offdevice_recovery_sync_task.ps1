param(
    [string]$IdentityFile = "",
    [string]$RemoteHost = "192.168.1.101",
    [string]$RemoteUser = "nvidia",
    [double]$MaximumBackupAgeHours = 192.0,
    [double]$MaximumDrillAgeDays = 45.0,
    [int]$MaximumEncryptedBackups = 4,
    [long]$MaximumEncryptedBytes = 536870912
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$SyncScript = Join-Path $PSScriptRoot "sync_encrypted_recovery_backups.ps1"
$DataPath = Join-Path $ProjectRoot "data"
$RecoveryPath = Join-Path $DataPath "recovery"
$StorePath = Join-Path $RecoveryPath "off-device"
$StatusPath = Join-Path $StorePath "scheduled-sync-status.json"
$TemporaryStatusPath = "$StatusPath.tmp"
$AlertPath = Join-Path $StorePath "recovery-health-alert.json"
$TemporaryAlertPath = "$AlertPath.tmp"
$DrillStatusPath = Join-Path $StorePath "restore-drill-status.json"
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
$EventLogSource = "EdgeSentinel Recovery"
$EventSourceRegistryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Application\$EventLogSource"

function Assert-SafeStatusPath {
    foreach ($Path in @($ProjectRoot, $DataPath, $RecoveryPath, $StorePath)) {
        if (Test-Path -LiteralPath $Path) {
            $Item = Get-Item -LiteralPath $Path -Force
            if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Scheduled synchronization status path cannot traverse a reparse point"
            }
        }
    }
    foreach ($Path in @(
        $StatusPath, $TemporaryStatusPath, $AlertPath, $TemporaryAlertPath,
        $DrillStatusPath
    )) {
        if ((Test-Path -LiteralPath $Path) -and
            ((Get-Item -LiteralPath $Path -Force).Attributes -band
                [IO.FileAttributes]::ReparsePoint)) {
            throw "Scheduled synchronization status file cannot be a reparse point"
        }
    }
}

if ($MaximumBackupAgeHours -lt 1 -or $MaximumBackupAgeHours -gt 720 -or
    $MaximumDrillAgeDays -lt 1 -or $MaximumDrillAgeDays -gt 366 -or
    $MaximumEncryptedBackups -lt 1 -or $MaximumEncryptedBackups -gt 100 -or
    $MaximumEncryptedBytes -lt 104857600 -or
    $MaximumEncryptedBytes -gt 10737418240) {
    throw "Recovery age targets are outside the supported bounds"
}

if (-not $IdentityFile) {
    $IdentityFile = Join-Path $env:LOCALAPPDATA `
        "EdgeSentinel\recovery-sync\id_ed25519"
}
$IdentityFile = [IO.Path]::GetFullPath($IdentityFile)
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "Scheduled recovery synchronization identity is missing"
}
if ((Get-Item -LiteralPath $IdentityFile -Force).Attributes -band
    [IO.FileAttributes]::ReparsePoint) {
    throw "Scheduled recovery synchronization identity cannot be a reparse point"
}

$StartedAt = [DateTimeOffset]::Now
$Succeeded = $false
$Failure = $null
$ExitCode = 1
$LatestBackupId = $null
$LatestBackupCreatedAt = $null
$LatestBackupAgeHours = $null
$LatestDrillId = $null
$LatestDrillFinishedAt = $null
$LatestDrillAgeDays = $null
$EncryptedBackupCount = 0
$EncryptedBackupBytes = 0
$FailureCode = "RECOVERY_SYNC_FAILED"
Assert-SafeStatusPath
$PreviousAlertState = $null
if (Test-Path -LiteralPath $AlertPath -PathType Leaf) {
    try {
        $PreviousAlert = Get-Content -LiteralPath $AlertPath -Raw |
            ConvertFrom-Json
        $PreviousAlertState = [string]$PreviousAlert.state
    }
    catch {
        $PreviousAlertState = "INVALID"
    }
}
try {
    Set-Location -LiteralPath $ProjectRoot
    $SyncArguments = @{
        RemoteHost = $RemoteHost
        RemoteUser = $RemoteUser
        IdentityFile = $IdentityFile
        BatchMode = $true
        RestrictedProtocol = $true
    }
    & $SyncScript @SyncArguments
    $FailureCode = "RECOVERY_POINT_VALIDATION_FAILED"
    $Candidates = @(Get-ChildItem -LiteralPath $StorePath -Force -File |
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
                CreatedAt = [DateTimeOffset]::Parse(
                    [string]$Metadata.created_at
                )
                ArtifactBytes = [int64]$Metadata.artifact_bytes
            }
        } |
        Sort-Object CreatedAt -Descending)
    if ($Candidates.Count -eq 0) {
        throw "Scheduled recovery synchronization found no recovery point"
    }
    $EncryptedBackupCount = $Candidates.Count
    $EncryptedBackupBytes = [int64](
        ($Candidates | Measure-Object -Property ArtifactBytes -Sum).Sum
    )
    $FailureCode = "RECOVERY_CAPACITY_EXCEEDED"
    if ($EncryptedBackupCount -gt $MaximumEncryptedBackups -or
        $EncryptedBackupBytes -gt $MaximumEncryptedBytes) {
        throw "Encrypted recovery capacity exceeds the demo threshold"
    }
    $FailureCode = "RECOVERY_POINT_VALIDATION_FAILED"
    $LatestBackupId = $Candidates[0].BackupId
    $LatestBackupCreatedAt = $Candidates[0].CreatedAt
    $Now = [DateTimeOffset]::Now
    if ($LatestBackupCreatedAt -gt $Now.AddMinutes(5)) {
        throw "Latest encrypted recovery point timestamp is in the future"
    }
    $LatestBackupAgeHours = [Math]::Round(
        [Math]::Max(0, ($Now - $LatestBackupCreatedAt).TotalHours),
        3
    )
    if ($LatestBackupAgeHours -gt $MaximumBackupAgeHours) {
        throw "Latest encrypted recovery point exceeds the freshness target"
    }
    $FailureCode = "RESTORE_DRILL_INVALID"
    if (-not (Test-Path -LiteralPath $DrillStatusPath -PathType Leaf)) {
        throw "Isolated recovery drill status is unavailable"
    }
    $DrillStatus = Get-Content -LiteralPath $DrillStatusPath -Raw |
        ConvertFrom-Json
    if ([string]$DrillStatus.status -ne "PASS" -or
        [string]$DrillStatus.mode -ne "ISOLATED_RESTORE_DRILL" -or
        -not [bool]$DrillStatus.isolated -or
        [bool]$DrillStatus.production_modified -or
        [bool]$DrillStatus.credentials_exposed -or
        [bool]$DrillStatus.plaintext_persisted -or
        -not [bool]$DrillStatus.sqlite_consistent -or
        [int64]$DrillStatus.restored_file_count -le 0 -or
        [int64]$DrillStatus.restored_file_count -ne
            [int64]$DrillStatus.post_restore_verified_files) {
        throw "Isolated recovery drill result is invalid"
    }
    $LatestDrillId = [string]$DrillStatus.drill_id
    if ($LatestDrillId -notmatch '^rdr_[0-9a-f]{32}$') {
        throw "Isolated recovery drill identity is invalid"
    }
    $LatestDrillFinishedAt = [DateTimeOffset]::Parse(
        [string]$DrillStatus.finished_at
    )
    if ($LatestDrillFinishedAt -gt $Now.AddMinutes(5)) {
        throw "Isolated recovery drill timestamp is in the future"
    }
    $LatestDrillAgeDays = [Math]::Round(
        [Math]::Max(0, ($Now - $LatestDrillFinishedAt).TotalDays),
        3
    )
    if ($LatestDrillAgeDays -gt $MaximumDrillAgeDays) {
        throw "Isolated recovery drill exceeds the freshness target"
    }
    $FailureCode = $null
    $Succeeded = $true
    $ExitCode = 0
}
catch {
    $Failure = $_.Exception.Message
    Write-Error "Scheduled encrypted recovery synchronization failed: $Failure"
}
finally {
    Assert-SafeStatusPath
    New-Item -ItemType Directory -Force -Path $StorePath | Out-Null
    $FinishedAt = [DateTimeOffset]::Now
    $EventLogDelivery = "NOT_REQUIRED"
    $EventLogFailure = $null
    $ShouldWriteEvent = (-not $Succeeded) -or
        ($PreviousAlertState -eq "ACTIVE")
    if ($ShouldWriteEvent) {
        if (Test-Path -LiteralPath $EventSourceRegistryPath) {
            try {
                if ($Succeeded) {
                    $EventType = "Information"
                    $EventId = 4100
                    $EventMessage = "EdgeSentinel off-device recovery health cleared. backup_id=$LatestBackupId drill_id=$LatestDrillId"
                }
                else {
                    $EventType = "Error"
                    $EventId = 4101
                    $EventMessage = "EdgeSentinel off-device recovery health failed. code=$FailureCode"
                }
                Write-EventLog -LogName Application `
                    -Source $EventLogSource `
                    -EntryType $EventType `
                    -EventId $EventId `
                    -Message $EventMessage
                $EventLogDelivery = "WRITTEN"
            }
            catch {
                $EventLogDelivery = "FAILED"
                $EventLogFailure = "EVENT_LOG_WRITE_FAILED"
            }
        }
        else {
            $EventLogDelivery = "UNAVAILABLE"
            $EventLogFailure = "EVENT_SOURCE_NOT_INSTALLED"
        }
    }
    $Status = [ordered]@{
        schema_version = "1.0"
        status = $(if ($Succeeded) { "SUCCEEDED" } else { "FAILED" })
        started_at = $StartedAt.ToString("o")
        finished_at = $FinishedAt.ToString("o")
        duration_seconds = [Math]::Round(
            ($FinishedAt - $StartedAt).TotalSeconds,
            3
        )
        remote_host = $RemoteHost
        remote_user = $RemoteUser
        transport = "RESTRICTED_SSH"
        batch_mode = $true
        retention_applied = $false
        latest_backup_id = $LatestBackupId
        latest_backup_created_at = $(if ($LatestBackupCreatedAt) {
            $LatestBackupCreatedAt.ToString("o")
        } else { $null })
        latest_backup_age_hours = $LatestBackupAgeHours
        maximum_backup_age_hours = $MaximumBackupAgeHours
        encrypted_backup_count = $EncryptedBackupCount
        encrypted_backup_bytes = $EncryptedBackupBytes
        maximum_encrypted_backups = $MaximumEncryptedBackups
        maximum_encrypted_bytes = $MaximumEncryptedBytes
        latest_drill_id = $LatestDrillId
        latest_drill_finished_at = $(if ($LatestDrillFinishedAt) {
            $LatestDrillFinishedAt.ToString("o")
        } else { $null })
        latest_drill_age_days = $LatestDrillAgeDays
        maximum_drill_age_days = $MaximumDrillAgeDays
        failure_code = $FailureCode
        failure = $Failure
        event_log_delivery = $EventLogDelivery
        event_log_failure = $EventLogFailure
        credentials_exposed = $false
        plaintext_persisted = $false
    }
    [IO.File]::WriteAllText(
        $TemporaryStatusPath,
        (($Status | ConvertTo-Json -Depth 4) + "`n"),
        $Utf8NoBom
    )
    Move-Item -LiteralPath $TemporaryStatusPath `
        -Destination $StatusPath -Force
    $Alert = [ordered]@{
        schema_version = "1.0"
        state = $(if ($Succeeded) { "CLEARED" } else { "ACTIVE" })
        checked_at = $FinishedAt.ToString("o")
        code = $(if ($Succeeded) { "RECOVERY_HEALTHY" } else { $FailureCode })
        reason = $Failure
        latest_backup_id = $LatestBackupId
        latest_backup_age_hours = $LatestBackupAgeHours
        maximum_backup_age_hours = $MaximumBackupAgeHours
        encrypted_backup_count = $EncryptedBackupCount
        encrypted_backup_bytes = $EncryptedBackupBytes
        maximum_encrypted_backups = $MaximumEncryptedBackups
        maximum_encrypted_bytes = $MaximumEncryptedBytes
        latest_drill_id = $LatestDrillId
        latest_drill_age_days = $LatestDrillAgeDays
        maximum_drill_age_days = $MaximumDrillAgeDays
        event_log_delivery = $EventLogDelivery
        event_log_failure = $EventLogFailure
        credentials_exposed = $false
        plaintext_persisted = $false
    }
    [IO.File]::WriteAllText(
        $TemporaryAlertPath,
        (($Alert | ConvertTo-Json -Depth 4) + "`n"),
        $Utf8NoBom
    )
    Move-Item -LiteralPath $TemporaryAlertPath `
        -Destination $AlertPath -Force
}
exit $ExitCode
