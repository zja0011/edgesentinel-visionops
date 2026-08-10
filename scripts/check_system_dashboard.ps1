param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"

function Get-Utf8Text {
    param([string]$Path)

    $Client = New-Object System.Net.WebClient
    try {
        $Bytes = $Client.DownloadData("$BaseUrl$Path")
        return [System.Text.Encoding]::UTF8.GetString($Bytes)
    }
    finally {
        $Client.Dispose()
    }
}

Write-Host "Checking Jetson system metrics at $BaseUrl"

$Status = (Get-Utf8Text -Path "/api/v1/system/status") |
    ConvertFrom-Json
$JavaScript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"

if (
    $Status.status -ne "ok" -or
    $null -eq $Status.load_average -or
    $Status.load_average.one_minute -lt 0 -or
    $Status.load_average.cpu_count -lt 1 -or
    $null -eq $Status.memory -or
    $Status.memory.used_percent -lt 0 -or
    $Status.memory.used_percent -gt 100 -or
    $null -eq $Status.disk -or
    $Status.disk.used_percent -lt 0 -or
    $Status.disk.used_percent -gt 100 -or
    $Status.uptime_seconds -le 0 -or
    $Status.timestamp -notmatch "\+08:00$" -or
    $JavaScript -notmatch "renderSystem"
) {
    $Status | ConvertTo-Json -Depth 8
    throw "System Dashboard acceptance check failed"
}

$Temperature = "unavailable"
if (
    $null -ne $Status.temperature -and
    $null -ne $Status.temperature.max_celsius
) {
    $Temperature = "$($Status.temperature.max_celsius) C"
}

Write-Host ""
Write-Host "System Dashboard acceptance summary:"
Write-Host "Status: $($Status.status)"
Write-Host "Load average: $($Status.load_average.one_minute)"
Write-Host "CPU count: $($Status.load_average.cpu_count)"
Write-Host "Memory used: $($Status.memory.used_percent)%"
Write-Host "Disk used: $($Status.disk.used_percent)%"
Write-Host "Uptime seconds: $($Status.uptime_seconds)"
Write-Host "Maximum temperature: $Temperature"
Write-Host "Timestamp: $($Status.timestamp)"
Write-Host "System Dashboard smoke test passed."
