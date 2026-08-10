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

function Get-Binary {
    param([string]$Path)

    $Client = New-Object System.Net.WebClient
    try {
        return $Client.DownloadData("$BaseUrl$Path")
    }
    finally {
        $Client.Dispose()
    }
}

Write-Host "Checking Dashboard Event Center at $BaseUrl/dashboard"

$Events = (
    Get-Utf8Text `
        -Path "/api/v1/events?object_class=bottle&camera_id=camera_01&limit=10"
) | ConvertFrom-Json
$EventItems = @($Events.events)
if ($EventItems.Count -lt 1) {
    throw "No bottle events are available for Event Center testing"
}
foreach ($Event in $EventItems) {
    if (
        $Event.object_class -ne "bottle" -or
        $Event.camera_id -ne "camera_01"
    ) {
        throw "Filtered event results contain an unexpected event"
    }
}

$Selected = $EventItems[0]
$Detail = (
    Get-Utf8Text `
        -Path "/api/v1/events/$($Selected.event_id)"
) | ConvertFrom-Json
if (
    $Detail.event_id -ne $Selected.event_id -or
    $Detail.timestamp -notmatch "\+08:00$" -or
    $Detail.object_class -ne "bottle"
) {
    throw "Event detail response validation failed"
}

$EvidencePath = $Detail.evidence_urls.primary
if ([string]::IsNullOrWhiteSpace([string]$EvidencePath)) {
    throw "Selected event has no primary evidence URL"
}
$Evidence = Get-Binary -Path $EvidencePath
if (
    $Evidence.Length -lt 1000 -or
    $Evidence[0] -ne 0xFF -or
    $Evidence[1] -ne 0xD8
) {
    throw "Event evidence is not a valid non-empty JPEG"
}

$Html = Get-Utf8Text -Path "/dashboard"
$JavaScript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Html -notmatch "event-filter-form" -or
    $Html -notmatch "event-detail-backdrop" -or
    $JavaScript -notmatch "buildEventUrl" -or
    $JavaScript -notmatch "openEventDetail"
) {
    throw "Dashboard Event Center assets are incomplete"
}

Write-Host ""
Write-Host "Event Center acceptance summary:"
Write-Host "Filtered object class: bottle"
Write-Host "Filtered camera: camera_01"
Write-Host "Filtered event count: $($EventItems.Count)"
Write-Host "Detail event ID: $($Detail.event_id)"
Write-Host "Detail event type: $($Detail.event_type)"
Write-Host "Evidence bytes: $($Evidence.Length)"
Write-Host "Event Center smoke test passed."
