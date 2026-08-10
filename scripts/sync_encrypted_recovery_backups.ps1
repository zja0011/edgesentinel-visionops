param(
    [string]$RemoteHost = "192.168.1.101",
    [string]$RemoteUser = "nvidia",
    [string]$IdentityFile = "",
    [switch]$BatchMode,
    [switch]$RestrictedProtocol,
    [switch]$LocalOnly,
    [switch]$VerifyContent,
    [int]$KeepCount = 4,
    [long]$MaximumBytes = 536870912,
    [switch]$ApplyRetention,
    [string]$Confirmation = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath(
    (Split-Path -Parent $PSScriptRoot)
)
$DataPath = [System.IO.Path]::GetFullPath(
    (Join-Path $ProjectRoot "data")
)
$RecoveryPath = [System.IO.Path]::GetFullPath(
    (Join-Path $DataPath "recovery")
)
$StorePath = [System.IO.Path]::GetFullPath(
    (Join-Path $RecoveryPath "off-device")
)
$RemoteDirectory = "/home/nvidia/edgesentinel-recovery-exports/encrypted"
$MarkerPath = Join-Path $StorePath ".edgesentinel-offdevice-store"
$LockPath = Join-Path $StorePath ".sync.lock"
$AuditPath = Join-Path $StorePath "sync-audit.jsonl"
$MarkerContent = "edgesentinel-offdevice-store-v1"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if ($KeepCount -lt 1 -or $KeepCount -gt 100) {
    throw "KeepCount must be between 1 and 100"
}
if ($MaximumBytes -lt 1048576 -or $MaximumBytes -gt 1099511627776) {
    throw "MaximumBytes must be between 1 MiB and 1 TiB"
}
if ($RemoteHost -notmatch '^[A-Za-z0-9.-]+$' -or
    $RemoteUser -notmatch '^[A-Za-z0-9._-]+$') {
    throw "Remote SSH identity is invalid"
}
if ($ApplyRetention -and $Confirmation -ne "APPLY_OFF_DEVICE_RETENTION") {
    throw "ApplyRetention requires confirmation APPLY_OFF_DEVICE_RETENTION"
}

function Test-ReparsePoint {
    param([string]$Path)
    $Item = Get-Item -LiteralPath $Path -Force
    return [bool]($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Assert-TrustedStorePath {
    foreach ($Path in @($ProjectRoot, $DataPath, $RecoveryPath, $StorePath)) {
        if ((Test-Path -LiteralPath $Path) -and (Test-ReparsePoint $Path)) {
            throw "Off-device store path cannot traverse a reparse point"
        }
    }
}

function Assert-RecoveryMetadataContract {
    param(
        [object]$Metadata,
        [string]$MetadataName,
        [string]$ExpectedBackupId = ""
    )
    $RequiredProperties = @(
        "schema_version", "backup_id", "created_at", "encryption",
        "authentication", "kdf", "iterations", "artifact_file",
        "artifact_bytes", "artifact_sha256", "hmac_sha256",
        "manifest_sha256", "credentials_included",
        "absolute_paths_included", "plaintext_persisted"
    )
    $PropertyNames = @($Metadata.PSObject.Properties.Name)
    foreach ($Property in $RequiredProperties) {
        if ($Property -notin $PropertyNames) {
            throw "Recovery metadata is missing a required property: $Property"
        }
    }
    $BackupId = [string]$Metadata.backup_id
    if ($BackupId -notmatch '^dr_[0-9a-f]{32}$' -or
        ($ExpectedBackupId -and $BackupId -ne $ExpectedBackupId)) {
        throw "Recovery metadata backup ID is invalid"
    }
    if ($MetadataName -ne "$BackupId.esdr.json" -or
        [string]$Metadata.artifact_file -ne "$BackupId.esdr" -or
        [string]$Metadata.schema_version -ne "1.0" -or
        [string]$Metadata.encryption -ne "AES-256-CBC" -or
        [string]$Metadata.authentication -ne "HMAC-SHA256" -or
        [string]$Metadata.kdf -ne "PBKDF2-HMAC-SHA256" -or
        [int]$Metadata.iterations -ne 200000 -or
        [long]$Metadata.artifact_bytes -le 0 -or
        $Metadata.credentials_included -ne $false -or
        $Metadata.absolute_paths_included -ne $false -or
        $Metadata.plaintext_persisted -ne $false -or
        [string]$Metadata.artifact_sha256 -notmatch '^[0-9a-f]{64}$' -or
        [string]$Metadata.hmac_sha256 -notmatch '^[0-9a-f]{64}$' -or
        [string]$Metadata.manifest_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw "Recovery metadata security contract is invalid: $BackupId"
    }
    try {
        return [DateTimeOffset]::Parse([string]$Metadata.created_at)
    }
    catch {
        throw "Encrypted recovery creation time is invalid: $BackupId"
    }
}

function Get-ArtifactRecord {
    param([string]$MetadataPath)
    $MetadataItem = Get-Item -LiteralPath $MetadataPath -Force
    if (Test-ReparsePoint $MetadataPath) {
        throw "Recovery metadata cannot be a reparse point"
    }
    try {
        $Metadata = [IO.File]::ReadAllText($MetadataItem.FullName, $Utf8NoBom) |
            ConvertFrom-Json
    }
    catch {
        throw "Recovery metadata is invalid: $($MetadataItem.Name)"
    }
    $BackupId = [string]$Metadata.backup_id
    $CreatedAt = Assert-RecoveryMetadataContract `
        $Metadata $MetadataItem.Name
    $ArtifactPath = Join-Path $StorePath ([string]$Metadata.artifact_file)
    if (-not (Test-Path -LiteralPath $ArtifactPath -PathType Leaf) -or
        (Test-ReparsePoint $ArtifactPath)) {
        throw "Encrypted recovery artifact is missing or unsafe: $BackupId"
    }
    $ArtifactItem = Get-Item -LiteralPath $ArtifactPath -Force
    if ($ArtifactItem.Length -ne [long]$Metadata.artifact_bytes) {
        throw "Encrypted recovery artifact size mismatch: $BackupId"
    }
    $ActualHash = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash
    if ($ActualHash -ne ([string]$Metadata.artifact_sha256).ToUpperInvariant()) {
        throw "Encrypted recovery artifact SHA-256 mismatch: $BackupId"
    }
    return [PSCustomObject]@{
        BackupId = $BackupId
        CreatedAt = $CreatedAt
        ArtifactPath = $ArtifactItem.FullName
        MetadataPath = $MetadataItem.FullName
        ArtifactBytes = [long]$ArtifactItem.Length
        ArtifactSha256 = ([string]$Metadata.artifact_sha256).ToLowerInvariant()
        ManifestSha256 = ([string]$Metadata.manifest_sha256).ToLowerInvariant()
    }
}

function Get-StoreRecords {
    $MetadataFiles = @(Get-ChildItem -LiteralPath $StorePath -Force -File |
        Where-Object { $_.Name -match '^dr_[0-9a-f]{32}\.esdr\.json$' })
    $Records = @($MetadataFiles | ForEach-Object {
        Get-ArtifactRecord $_.FullName
    })
    $Artifacts = @(Get-ChildItem -LiteralPath $StorePath -Force -File |
        Where-Object { $_.Name -match '^dr_[0-9a-f]{32}\.esdr$' })
    if ($Artifacts.Count -ne $Records.Count) {
        throw "Off-device store contains an incomplete encrypted pair"
    }
    return $Records
}

function Get-RetentionPlan {
    param([object[]]$Records)
    $Sorted = @($Records | Sort-Object CreatedAt -Descending)
    $Retained = New-Object System.Collections.Generic.List[object]
    $Candidates = New-Object System.Collections.Generic.List[object]
    [long]$RunningBytes = 0
    for ($Index = 0; $Index -lt $Sorted.Count; $Index++) {
        $Record = $Sorted[$Index]
        $WithinCount = $Index -lt $KeepCount
        $WithinBytes = ($RunningBytes + $Record.ArtifactBytes) -le $MaximumBytes
        if ($Index -eq 0 -or ($WithinCount -and $WithinBytes)) {
            $Retained.Add($Record)
            $RunningBytes += $Record.ArtifactBytes
        }
        else {
            $Candidates.Add($Record)
        }
    }
    return [PSCustomObject]@{
        Retained = @($Retained.ToArray())
        Candidates = @($Candidates.ToArray())
        RetainedBytes = $RunningBytes
        CapacityExceeded = $RunningBytes -gt $MaximumBytes
    }
}

function Invoke-ContentVerification {
    param([object[]]$Records)
    foreach ($Record in $Records) {
        Write-Host "Verifying encrypted content for $($Record.BackupId)..."
        & python -m apps.recovery_export verify `
            --artifact $Record.ArtifactPath `
            --metadata $Record.MetadataPath
        if ($LASTEXITCODE -ne 0) {
            throw "Encrypted content verification failed: $($Record.BackupId)"
        }
    }
}

function Invoke-RestrictedDownload {
    param(
        [string]$RemoteIdentity,
        [object[]]$SshOptions,
        [string]$Name,
        [string]$Destination
    )
    if ($Name -notmatch '^dr_[0-9a-f]{32}\.esdr(?:\.json)?$') {
        throw "Restricted recovery filename is invalid"
    }
    $EncodedLines = @(& ssh @SshOptions $RemoteIdentity "read $Name")
    if ($LASTEXITCODE -ne 0) {
        throw "Restricted recovery download failed: $Name"
    }
    try {
        $Encoded = [string]::Join("", $EncodedLines)
        $Bytes = [Convert]::FromBase64String($Encoded)
        [IO.File]::WriteAllBytes($Destination, $Bytes)
    }
    catch {
        throw "Restricted recovery payload is invalid: $Name"
    }
}

function Open-SyncLock {
    for ($Attempt = 0; $Attempt -lt 2; $Attempt++) {
        try {
            return New-Object IO.FileStream(
                $LockPath,
                [IO.FileMode]::CreateNew,
                [IO.FileAccess]::Write,
                [IO.FileShare]::None
            )
        }
        catch {
            if ($Attempt -gt 0 -or -not (Test-Path -LiteralPath $LockPath)) {
                throw "Another off-device recovery sync is already running"
            }
            if (Test-ReparsePoint $LockPath) {
                throw "Off-device recovery sync lock cannot be a reparse point"
            }
            $Probe = $null
            try {
                $Probe = New-Object IO.FileStream(
                    $LockPath,
                    [IO.FileMode]::Open,
                    [IO.FileAccess]::ReadWrite,
                    [IO.FileShare]::None
                )
            }
            catch {
                throw "Another off-device recovery sync is already running"
            }
            finally {
                if ($Probe) {
                    $Probe.Dispose()
                }
            }
            Remove-Item -LiteralPath $LockPath -Force
        }
    }
    throw "Off-device recovery sync lock acquisition failed"
}

Assert-TrustedStorePath
New-Item -ItemType Directory -Force -Path $StorePath | Out-Null
Assert-TrustedStorePath
Set-Location -LiteralPath $ProjectRoot
if (Test-Path -LiteralPath $MarkerPath) {
    if ([IO.File]::ReadAllText($MarkerPath, $Utf8NoBom).Trim() -ne $MarkerContent) {
        throw "Off-device store marker is invalid"
    }
}
else {
    [IO.File]::WriteAllText($MarkerPath, $MarkerContent + "`n", $Utf8NoBom)
}

$LockStream = $null
$LockAcquired = $false
$StagePath = $null
$Pulled = New-Object System.Collections.Generic.List[string]
$Skipped = New-Object System.Collections.Generic.List[string]
$RemoteCount = 0
try {
    $LockStream = Open-SyncLock
    $LockAcquired = $true
    $LockRecord = [ordered]@{
        schema_version = "1.0"
        pid = $PID
        started_at = [DateTimeOffset]::Now.ToString("o")
    }
    $LockBytes = $Utf8NoBom.GetBytes(
        (($LockRecord | ConvertTo-Json -Compress) + "`n")
    )
    $LockStream.Write($LockBytes, 0, $LockBytes.Length)
    $LockStream.Flush()

    if (-not $LocalOnly) {
        $SshOptions = @(
            "-n",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=15",
            "-o", "ConnectionAttempts=1",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=2"
        )
        $ScpOptions = @(
            "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=15",
            "-o", "ConnectionAttempts=1",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=2"
        )
        if ($BatchMode) {
            $SshOptions += @("-o", "BatchMode=yes")
            $ScpOptions += @("-o", "BatchMode=yes")
        }
        if ($IdentityFile) {
            $ResolvedIdentity = (Resolve-Path -LiteralPath $IdentityFile).Path
            $SshOptions += @("-i", $ResolvedIdentity)
            $ScpOptions += @("-i", $ResolvedIdentity)
        }
        $RemoteIdentity = "$RemoteUser@$RemoteHost"
        $RemoteCommand = $(if ($RestrictedProtocol) {
            "list"
        }
        else {
            "find $RemoteDirectory -maxdepth 1 -type f -name 'dr_*.esdr.json' -printf '%f\n'"
        })
        $RemoteNames = @(& ssh @SshOptions $RemoteIdentity $RemoteCommand)
        if ($LASTEXITCODE -ne 0) {
            throw "Remote encrypted recovery discovery failed"
        }
        $RemoteNames = @($RemoteNames | Where-Object { $_ } | Sort-Object -Unique)
        foreach ($Name in $RemoteNames) {
            if ($Name -notmatch '^dr_[0-9a-f]{32}\.esdr\.json$') {
                throw "Remote recovery metadata filename is invalid"
            }
        }
        $RemoteCount = $RemoteNames.Count
        $StagePath = Join-Path $StorePath (".staging-" + [Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $StagePath | Out-Null
        foreach ($Name in $RemoteNames) {
            $BackupId = $Name.Substring(0, 35)
            $ArtifactName = "$BackupId.esdr"
            $StageMetadata = Join-Path $StagePath $Name
            $StageArtifact = Join-Path $StagePath $ArtifactName
            if ($RestrictedProtocol) {
                Invoke-RestrictedDownload $RemoteIdentity $SshOptions $Name $StageMetadata
            }
            else {
                & scp @ScpOptions "${RemoteIdentity}:${RemoteDirectory}/$Name" $StageMetadata
                if ($LASTEXITCODE -ne 0) {
                    throw "Remote recovery metadata download failed: $BackupId"
                }
            }
            $StagedMetadata = [IO.File]::ReadAllText($StageMetadata, $Utf8NoBom) |
                ConvertFrom-Json
            $null = Assert-RecoveryMetadataContract `
                $StagedMetadata $Name $BackupId
            $TargetMetadata = Join-Path $StorePath $Name
            $TargetArtifact = Join-Path $StorePath $ArtifactName
            if (Test-Path -LiteralPath $TargetMetadata) {
                $null = Get-ArtifactRecord $TargetMetadata
                $StagedMetadataHash = (Get-FileHash `
                    -LiteralPath $StageMetadata -Algorithm SHA256).Hash
                $TargetMetadataHash = (Get-FileHash `
                    -LiteralPath $TargetMetadata -Algorithm SHA256).Hash
                if ($StagedMetadataHash -ne $TargetMetadataHash) {
                    throw "Existing off-device backup conflicts with remote: $BackupId"
                }
                $Skipped.Add($BackupId)
                continue
            }
            if (Test-Path -LiteralPath $TargetArtifact) {
                throw "Unpaired local encrypted artifact blocks sync: $BackupId"
            }
            if ($RestrictedProtocol) {
                Invoke-RestrictedDownload $RemoteIdentity $SshOptions $ArtifactName $StageArtifact
            }
            else {
                & scp @ScpOptions "${RemoteIdentity}:${RemoteDirectory}/$ArtifactName" $StageArtifact
                if ($LASTEXITCODE -ne 0) {
                    throw "Remote encrypted artifact download failed: $BackupId"
                }
            }
            $StageHash = (Get-FileHash -LiteralPath $StageArtifact -Algorithm SHA256).Hash
            if ($StageHash -ne ([string]$StagedMetadata.artifact_sha256).ToUpperInvariant()) {
                throw "Downloaded encrypted artifact SHA-256 mismatch: $BackupId"
            }
            Move-Item -LiteralPath $StageArtifact -Destination $TargetArtifact
            Move-Item -LiteralPath $StageMetadata -Destination $TargetMetadata
            $Pulled.Add($BackupId)
        }
    }

    $Records = @(Get-StoreRecords)
    if ($Records.Count -eq 0) {
        throw "Off-device recovery store contains no verified encrypted pairs"
    }
    if ($VerifyContent) {
        Invoke-ContentVerification $Records
    }
    $Plan = Get-RetentionPlan $Records
    $Deleted = New-Object System.Collections.Generic.List[string]
    if ($ApplyRetention) {
        foreach ($Candidate in $Plan.Candidates) {
            Remove-Item -LiteralPath $Candidate.ArtifactPath -Force
            Remove-Item -LiteralPath $Candidate.MetadataPath -Force
            $Deleted.Add($Candidate.BackupId)
        }
        $Records = @(Get-StoreRecords)
        $Plan = Get-RetentionPlan $Records
    }

    $Audit = [ordered]@{
        schema_version = "1.0"
        timestamp = [DateTimeOffset]::Now.ToString("o")
        mode = $(if ($LocalOnly) { "LOCAL_ONLY" } else { "SSH_PULL" })
        transport = $(if ($LocalOnly) { "LOCAL" } elseif ($RestrictedProtocol) { "RESTRICTED_SSH" } else { "SSH_SCP" })
        remote_host = $(if ($LocalOnly) { $null } else { $RemoteHost })
        remote_exports = $RemoteCount
        pulled_backup_ids = @($Pulled.ToArray())
        skipped_backup_ids = @($Skipped.ToArray())
        artifact_downloads = $Pulled.Count
        verified_pairs = $Records.Count
        content_verified = [bool]$VerifyContent
        keep_count = $KeepCount
        maximum_bytes = $MaximumBytes
        retained_bytes = $Plan.RetainedBytes
        retention_candidates = @($Plan.Candidates | ForEach-Object { $_.BackupId })
        retention_applied = [bool]$ApplyRetention
        deleted_backup_ids = @($Deleted.ToArray())
        credentials_included = $false
        plaintext_persisted = $false
    }
    [IO.File]::AppendAllText(
        $AuditPath,
        (($Audit | ConvertTo-Json -Depth 6 -Compress) + "`n"),
        $Utf8NoBom
    )

    Write-Host ""
    Write-Host "Encrypted Off-device Recovery Sync summary:"
    Write-Host "Mode:" $Audit.mode
    Write-Host "Transport:" $Audit.transport
    Write-Host "Remote exports discovered:" $RemoteCount
    Write-Host "Pulled backups:" $Pulled.Count
    Write-Host "Already present:" $Skipped.Count
    Write-Host "Artifact downloads:" $Pulled.Count
    Write-Host "Verified encrypted pairs:" $Records.Count
    Write-Host "Content verification:" ([bool]$VerifyContent)
    Write-Host "Retention keep count:" $KeepCount
    Write-Host "Retention maximum bytes:" $MaximumBytes
    Write-Host "Retained bytes:" $Plan.RetainedBytes
    Write-Host "Retention candidates:" $Plan.Candidates.Count
    Write-Host "Retention applied:" ([bool]$ApplyRetention)
    Write-Host "Deleted backups:" $Deleted.Count
    Write-Host "Capacity exceeded by newest backup:" $Plan.CapacityExceeded
    Write-Host "Credentials included: False"
    Write-Host "Plaintext persisted: False"
    Write-Host "Audit:" $AuditPath
    Write-Host "Encrypted Off-device Recovery Sync smoke test passed."
}
finally {
    if ($LockStream) {
        $LockStream.Dispose()
    }
    if ($StagePath -and (Test-Path -LiteralPath $StagePath)) {
        Remove-Item -LiteralPath $StagePath -Recurse -Force
    }
    if ($LockAcquired -and (Test-Path -LiteralPath $LockPath)) {
        Remove-Item -LiteralPath $LockPath -Force
    }
}
