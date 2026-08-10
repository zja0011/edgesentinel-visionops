param(
    [ValidateSet("install", "status", "remove")]
    [string]$Action = "status",
    [string]$Source = "EdgeSentinel Recovery",
    [string]$Confirmation = "",
    [switch]$Preview
)

$ErrorActionPreference = "Stop"
$LogName = "Application"
$RegistryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\$LogName\$Source"
$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
$IsAdministrator = $Principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if ($Source -notmatch '^[A-Za-z0-9 ._-]{3,64}$') {
    throw "Event source name is invalid"
}
if ($Preview -and $Action -ne "install") {
    throw "Preview is supported only with Action install"
}

switch ($Action) {
    "status" {
        $Installed = Test-Path -LiteralPath $RegistryPath
        Write-Host "Off-device recovery event source installed:" $Installed
        Write-Host "Source:" $Source
        Write-Host "Log:" $LogName
        Write-Host "Administrator session:" $IsAdministrator
        Write-Host "Credentials exposed: False"
    }
    "install" {
        if (Test-Path -LiteralPath $RegistryPath) {
            throw "Recovery event source already exists; refusing to overwrite"
        }
        if ($Preview) {
            Write-Host "Off-device recovery event source preview: ready"
            Write-Host "Source registered: False"
            Write-Host "Required elevation: Administrator"
            Write-Host "Log:" $LogName
            Write-Host "Event IDs: 4099 install, 4100 cleared, 4101 active"
            Write-Host "Credentials exposed: False"
            break
        }
        if (-not $IsAdministrator) {
            throw "Event source installation requires an elevated PowerShell"
        }
        New-EventLog -LogName $LogName -Source $Source
        Write-EventLog -LogName $LogName -Source $Source `
            -EntryType Information -EventId 4099 `
            -Message "EdgeSentinel off-device recovery event source installed."
        Write-Host "Off-device recovery event source installed."
        Write-Host "Source:" $Source
        Write-Host "Log:" $LogName
        Write-Host "Installation event ID: 4099"
        Write-Host "Credentials exposed: False"
    }
    "remove" {
        if ($Confirmation -ne "REMOVE_OFFDEVICE_RECOVERY_EVENT_SOURCE") {
            throw "Event source removal requires confirmation REMOVE_OFFDEVICE_RECOVERY_EVENT_SOURCE"
        }
        if (-not $IsAdministrator) {
            throw "Event source removal requires an elevated PowerShell"
        }
        if (Test-Path -LiteralPath $RegistryPath) {
            Remove-EventLog -Source $Source
        }
        Write-Host "Off-device recovery event source removed."
        Write-Host "Recovery backups removed: False"
        Write-Host "Synchronization task removed: False"
    }
}
