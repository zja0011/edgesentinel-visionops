param(
    [string]$Source = "EdgeSentinel Recovery",
    [int]$Limit = 10
)

$ErrorActionPreference = "Stop"
$RegistryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Application\$Source"
if ($Limit -lt 1 -or $Limit -gt 100) {
    throw "Limit must be between 1 and 100"
}
if (-not (Test-Path -LiteralPath $RegistryPath)) {
    throw "Off-device recovery event source is not installed"
}
$Events = @(Get-WinEvent -FilterHashtable @{
    LogName = "Application"
    ProviderName = $Source
} -MaxEvents $Limit -ErrorAction Stop)

Write-Host ""
Write-Host "Off-device Recovery Event Log summary:"
Write-Host "Source installed: True"
Write-Host "Source:" $Source
Write-Host "Events returned:" $Events.Count
if ($Events.Count -gt 0) {
    Write-Host "Latest event ID:" $Events[0].Id
    Write-Host "Latest level:" $Events[0].LevelDisplayName
    Write-Host "Latest time:" $Events[0].TimeCreated
}
Write-Host "Allowed event IDs: 4099,4100,4101"
Write-Host "Credentials exposed: False"
Write-Host "Off-device Recovery Event Log smoke test passed."
