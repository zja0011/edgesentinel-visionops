param(
    [ValidateSet("install", "status", "run", "remove")]
    [string]$Action = "status",
    [string]$DailyAt = "03:00",
    [string]$IdentityFile = "",
    [string]$TaskName = "EdgeSentinel Off-device Recovery Sync",
    [string]$Confirmation = "",
    [switch]$Preview
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Runner = Join-Path $PSScriptRoot "run_offdevice_recovery_sync_task.ps1"
$StatusPath = Join-Path $ProjectRoot `
    "data\recovery\off-device\scheduled-sync-status.json"
$PowerShellPath = Join-Path $PSHOME "powershell.exe"
$CurrentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($Preview -and $Action -ne "install") {
    throw "Preview is supported only with Action install"
}

if (-not $IdentityFile) {
    $IdentityFile = Join-Path $env:LOCALAPPDATA `
        "EdgeSentinel\recovery-sync\id_ed25519"
}
$IdentityFile = [IO.Path]::GetFullPath($IdentityFile)
try {
    $ScheduleTime = [DateTime]::ParseExact(
        $DailyAt,
        "HH:mm",
        [Globalization.CultureInfo]::InvariantCulture
    )
}
catch {
    throw "DailyAt must use 24-hour HH:mm format"
}

function Get-ExpectedTaskArguments {
    return ('-NoProfile -NonInteractive -WindowStyle Hidden ' +
        '-ExecutionPolicy Bypass -File "{0}" -IdentityFile "{1}"' -f
        $Runner, $IdentityFile)
}

function Show-SyncStatus {
    $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $Installed = $null -ne $Task
    Write-Host "Off-device recovery synchronization task installed:" $Installed
    Write-Host "Task name:" $TaskName
    if (-not $Installed) {
        return
    }
    $Info = Get-ScheduledTaskInfo -TaskName $TaskName
    $ExpectedArguments = Get-ExpectedTaskArguments
    $ActionValid = $Task.Actions.Count -eq 1 -and
        $Task.Actions[0].Execute -eq $PowerShellPath -and
        $Task.Actions[0].Arguments -eq $ExpectedArguments
    $PrincipalValid = $false
    try {
        $CurrentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $TaskAccount = New-Object Security.Principal.NTAccount(
            [string]$Task.Principal.UserId
        )
        $TaskSid = $TaskAccount.Translate(
            [Security.Principal.SecurityIdentifier]
        ).Value
        $PrincipalValid = $TaskSid -eq $CurrentSid -and
            [string]$Task.Principal.LogonType -eq "Interactive" -and
            [string]$Task.Principal.RunLevel -eq "Limited"
    }
    catch {
        $PrincipalValid = $false
    }
    $LastResult = [int64]$Info.LastTaskResult
    $LastResultText = switch ($LastResult) {
        0 { "SUCCEEDED (0)" }
        267009 { "RUNNING (267009)" }
        267011 { "NOT_YET_RUN (267011)" }
        2147946720 { "STOPPED_OR_REQUEST_REFUSED (2147946720)" }
        default { "FAILED_OR_STOPPED ($LastResult)" }
    }
    Write-Host "State:" $Task.State
    Write-Host "Last run:" $(if ($LastResult -eq 267011) { "never" } else { $Info.LastRunTime })
    Write-Host "Last result:" $LastResultText
    Write-Host "Next run:" $Info.NextRunTime
    Write-Host "Action verified:" $ActionValid
    Write-Host "Principal verified:" $PrincipalValid
    Write-Host "Windows password stored: False"
    Write-Host "Runs before user logon: False"
    Write-Host "Retention deletion enabled: False"
    if (Test-Path -LiteralPath $StatusPath -PathType Leaf) {
        $LastStatus = Get-Content -LiteralPath $StatusPath -Raw |
            ConvertFrom-Json
        Write-Host "Last synchronization status:" $LastStatus.status
        Write-Host "Last synchronization finished:" $LastStatus.finished_at
        if ($LastStatus.PSObject.Properties.Name -contains "latest_backup_id") {
            Write-Host "Latest backup ID:" $LastStatus.latest_backup_id
            Write-Host "Latest backup age hours:" $LastStatus.latest_backup_age_hours
            Write-Host "Maximum backup age hours:" $LastStatus.maximum_backup_age_hours
        }
        if ($LastStatus.PSObject.Properties.Name -contains "latest_drill_id") {
            Write-Host "Latest drill ID:" $LastStatus.latest_drill_id
            Write-Host "Latest drill age days:" $LastStatus.latest_drill_age_days
            Write-Host "Maximum drill age days:" $LastStatus.maximum_drill_age_days
        }
        if ($LastStatus.PSObject.Properties.Name -contains "encrypted_backup_count") {
            Write-Host "Encrypted backup count:" $LastStatus.encrypted_backup_count
            Write-Host "Maximum encrypted backups:" $LastStatus.maximum_encrypted_backups
            Write-Host "Encrypted backup bytes:" $LastStatus.encrypted_backup_bytes
            Write-Host "Maximum encrypted bytes:" $LastStatus.maximum_encrypted_bytes
        }
    }
    else {
        Write-Host "Last synchronization status: not yet run"
    }
    if (-not $ActionValid -or -not $PrincipalValid) {
        throw "Installed recovery synchronization task is inconsistent"
    }
}

switch ($Action) {
    "install" {
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            throw "Recovery synchronization task already exists; refusing to overwrite"
        }
        if (-not (Test-Path -LiteralPath $Runner -PathType Leaf) -or
            -not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
            throw "Recovery synchronization task assets are incomplete"
        }
        $Drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($ProjectRoot))
        if ($Drive.DriveType -eq [IO.DriveType]::Network) {
            throw "Recovery synchronization task cannot run from a mapped network drive"
        }
        $TaskActionArguments = @{
            Execute = $PowerShellPath
            Argument = (Get-ExpectedTaskArguments)
            WorkingDirectory = $ProjectRoot
        }
        $TaskAction = New-ScheduledTaskAction @TaskActionArguments
        $Triggers = @(
            (New-ScheduledTaskTrigger -Daily -At $ScheduleTime),
            (New-ScheduledTaskTrigger -AtLogOn -User $CurrentIdentity)
        )
        $PrincipalArguments = @{
            UserId = $CurrentIdentity
            LogonType = "Interactive"
            RunLevel = "Limited"
        }
        $Principal = New-ScheduledTaskPrincipal @PrincipalArguments
        $SettingsArguments = @{
            StartWhenAvailable = $true
            ExecutionTimeLimit = (New-TimeSpan -Minutes 30)
            MultipleInstances = "IgnoreNew"
            AllowStartIfOnBatteries = $true
            DontStopIfGoingOnBatteries = $true
        }
        $Settings = New-ScheduledTaskSettingsSet @SettingsArguments
        $DefinitionArguments = @{
            Action = $TaskAction
            Trigger = $Triggers
            Principal = $Principal
            Settings = $Settings
            Description = "Pull verified encrypted EdgeSentinel recovery exports through a restricted SSH key."
        }
        $Definition = New-ScheduledTask @DefinitionArguments
        if ($Preview) {
            Write-Host "Off-device recovery synchronization task preview: ready"
            Write-Host "Task registered: False"
            Write-Host "Daily schedule:" $DailyAt
            Write-Host "Login catch-up trigger: enabled"
            Write-Host "Run identity:" $CurrentIdentity
            Write-Host "Logon type: Interactive"
            Write-Host "Run level: Limited"
            Write-Host "Windows password stored: False"
            Write-Host "Retention deletion enabled: False"
            break
        }
        Register-ScheduledTask -TaskName $TaskName `
            -InputObject $Definition | Out-Null
        Write-Host "Off-device recovery synchronization task installed."
        Write-Host "Daily schedule:" $DailyAt
        Write-Host "Login catch-up trigger: enabled"
        Write-Host "Run identity:" $CurrentIdentity
        Write-Host "Windows password stored: False"
        Write-Host "Retention deletion enabled: False"
        Show-SyncStatus
    }
    "status" {
        Show-SyncStatus
    }
    "run" {
        if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
            throw "Recovery synchronization task is not installed"
        }
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "Off-device recovery synchronization task started."
        Write-Host "Use -Action status after it completes."
    }
    "remove" {
        if ($Confirmation -ne "REMOVE_OFFDEVICE_RECOVERY_SYNC_TASK") {
            throw "Task removal requires confirmation REMOVE_OFFDEVICE_RECOVERY_SYNC_TASK"
        }
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Off-device recovery synchronization task removed."
        Write-Host "Private key removed: False"
        Write-Host "Downloaded backups removed: False"
    }
}
