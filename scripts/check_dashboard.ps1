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

function Get-Utf8Json {
    param([string]$Path)

    return (Get-Utf8Text -Path $Path) | ConvertFrom-Json
}

Write-Host "Checking EdgeSentinel Dashboard at $BaseUrl/dashboard"

$Health = Get-Utf8Json -Path "/health"
$People = Get-Utf8Json -Path "/api/v1/vision/people"
$Objects = Get-Utf8Json -Path "/api/v1/vision/objects"
$Events = Get-Utf8Json -Path "/api/v1/events?limit=6"
$Html = Get-Utf8Text -Path "/dashboard"
$Css = Get-Utf8Text -Path "/dashboard/assets/dashboard.css"
$JavaScript = Get-Utf8Text -Path "/dashboard/assets/dashboard.js"

if (
    $Health.status -ne "ok" -or
    $People.status -ne "available" -or
    $Objects.status -ne "available" -or
    $Events.count -lt 1 -or
    $Html -notmatch "EdgeSentinel" -or
    $Html -notmatch "event-list" -or
    $Css -notmatch "\.metrics" -or
    $JavaScript -notmatch "refreshDashboard"
) {
    throw "Dashboard acceptance check failed"
}

Write-Host ""
Write-Host "Dashboard acceptance summary:"
Write-Host "API status: $($Health.status)"
Write-Host "People: $($People.current_people) stale=$($People.stale)"
Write-Host "Objects: $($Objects.total_current)"
Write-Host "Recent events: $($Events.count)"
Write-Host "Dashboard HTML bytes: $([System.Text.Encoding]::UTF8.GetByteCount($Html))"
Write-Host "Dashboard CSS bytes: $([System.Text.Encoding]::UTF8.GetByteCount($Css))"
Write-Host "Dashboard JS bytes: $([System.Text.Encoding]::UTF8.GetByteCount($JavaScript))"
Write-Host "Dashboard URL: $BaseUrl/dashboard"
Write-Host "Dashboard smoke test passed."
