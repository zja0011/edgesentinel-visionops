param(
    [string]$BackupId = "",
    [string]$StorePath = "",
    [string]$KeyFile = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $StorePath) {
    $StorePath = Join-Path $ProjectRoot "data\recovery\off-device"
}
$StorePath = [IO.Path]::GetFullPath($StorePath)
$StatusPath = Join-Path $StorePath "restore-drill-status.json"
$TemporaryStatusPath = "$StatusPath.tmp"
$Utf8NoBom = New-Object Text.UTF8Encoding($false)

function Assert-RegularFile {
    param([string]$Path, [string]$Description)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Description is unavailable"
    }
    $Item = Get-Item -LiteralPath $Path -Force
    if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "$Description cannot be a reparse point"
    }
}

if (-not (Test-Path -LiteralPath $StorePath -PathType Container)) {
    throw "Off-device recovery store is unavailable"
}
if ((Get-Item -LiteralPath $StorePath -Force).Attributes -band
    [IO.FileAttributes]::ReparsePoint) {
    throw "Off-device recovery store cannot be a reparse point"
}
foreach ($Path in @($StatusPath, $TemporaryStatusPath)) {
    if ((Test-Path -LiteralPath $Path) -and
        ((Get-Item -LiteralPath $Path -Force).Attributes -band
            [IO.FileAttributes]::ReparsePoint)) {
        throw "Recovery drill status cannot be a reparse point"
    }
}

$Candidates = @(Get-ChildItem -LiteralPath $StorePath -Force -File |
    Where-Object { $_.Name -match '^dr_[0-9a-f]{32}\.esdr\.json$' } |
    ForEach-Object {
        $Metadata = Get-Content -LiteralPath $_.FullName -Raw |
            ConvertFrom-Json
        if ([string]$Metadata.backup_id -notmatch '^dr_[0-9a-f]{32}$' -or
            $_.Name -ne ([string]$Metadata.backup_id + ".esdr.json")) {
            throw "Off-device recovery metadata identity is invalid"
        }
        [PSCustomObject]@{
            BackupId = [string]$Metadata.backup_id
            CreatedAt = [DateTimeOffset]::Parse(
                [string]$Metadata.created_at
            )
            MetadataPath = $_.FullName
            ArtifactPath = Join-Path $StorePath (
                [string]$Metadata.artifact_file
            )
        }
    } |
    Sort-Object CreatedAt -Descending)
if ($Candidates.Count -eq 0) {
    throw "No encrypted off-device recovery backup is available"
}
if ($BackupId) {
    if ($BackupId -notmatch '^dr_[0-9a-f]{32}$') {
        throw "BackupId is invalid"
    }
    $Selected = @($Candidates | Where-Object {
        $_.BackupId -eq $BackupId
    })
    if ($Selected.Count -ne 1) {
        throw "Requested encrypted recovery backup is unavailable"
    }
    $Recovery = $Selected[0]
}
else {
    $Recovery = $Candidates[0]
}
Assert-RegularFile $Recovery.MetadataPath "Recovery metadata"
Assert-RegularFile $Recovery.ArtifactPath "Encrypted recovery artifact"

$PythonArguments = @(
    "-m", "apps.recovery_export", "drill",
    "--artifact", $Recovery.ArtifactPath,
    "--metadata", $Recovery.MetadataPath
)
if ($KeyFile) {
    $KeyFile = [IO.Path]::GetFullPath($KeyFile)
    Assert-RegularFile $KeyFile "Recovery export key file"
    $PythonArguments += @("--key-file", $KeyFile)
}

$StartedAt = [DateTimeOffset]::Now
$DrillId = "rdr_" + [Guid]::NewGuid().ToString("N")
$Result = $null
$Succeeded = $false
try {
    Set-Location -LiteralPath $ProjectRoot
    $Output = @(& python @PythonArguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Isolated recovery drill process failed"
    }
    $Result = ([string]::Join("`n", $Output) | ConvertFrom-Json)
    if ([string]$Result.status -ne "PASS" -or
        [string]$Result.mode -ne "ISOLATED_RESTORE_DRILL" -or
        -not [bool]$Result.isolated -or
        [bool]$Result.production_modified -or
        [bool]$Result.credentials_included -or
        [bool]$Result.plaintext_persisted -or
        [int64]$Result.restored_file_count -ne [int64]$Result.file_count -or
        [int64]$Result.post_restore_verified_files -ne
            [int64]$Result.file_count) {
        throw "Isolated recovery drill result is invalid"
    }
    $Succeeded = $true
}
finally {
    $FinishedAt = [DateTimeOffset]::Now
    $Status = [ordered]@{
        schema_version = "1.0"
        status = $(if ($Succeeded) { "PASS" } else { "FAILED" })
        drill_id = $DrillId
        mode = "ISOLATED_RESTORE_DRILL"
        started_at = $StartedAt.ToString("o")
        finished_at = $FinishedAt.ToString("o")
        duration_seconds = [Math]::Round(
            ($FinishedAt - $StartedAt).TotalSeconds,
            3
        )
        backup_id = $(if ($Result) { $Result.backup_id } else {
            $Recovery.BackupId
        })
        backup_created_at = $Recovery.CreatedAt.ToString("o")
        artifact_sha256 = $(if ($Result) {
            $Result.artifact_sha256
        } else { $null })
        manifest_sha256 = $(if ($Result) {
            $Result.manifest_sha256
        } else { $null })
        file_count = $(if ($Result) { $Result.file_count } else { $null })
        restored_file_count = $(if ($Result) {
            $Result.restored_file_count
        } else { $null })
        post_restore_verified_files = $(if ($Result) {
            $Result.post_restore_verified_files
        } else { $null })
        sqlite_consistent = $(if ($Result) {
            [bool]$Result.sqlite_consistent
        } else { $false })
        isolated = $true
        production_modified = $false
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
}

Write-Host ""
Write-Host "Off-device Isolated Recovery Drill summary:"
Write-Host "Status:" $Status.status
Write-Host "Drill ID:" $Status.drill_id
Write-Host "Backup ID:" $Status.backup_id
Write-Host "Files restored:" $Status.restored_file_count
Write-Host "Post-restore verified files:" $Status.post_restore_verified_files
Write-Host "SQLite consistent:" $Status.sqlite_consistent
Write-Host "Isolated: True"
Write-Host "Production modified: False"
Write-Host "Credentials exposed: False"
Write-Host "Plaintext persisted: False"
Write-Host "Off-device Isolated Recovery Drill passed."
