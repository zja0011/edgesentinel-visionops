param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"

function Get-Utf8Json {
    param([string]$Path)

    $Client = New-Object System.Net.WebClient
    try {
        $Bytes = $Client.DownloadData("$BaseUrl$Path")
        $Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
        return $Text | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

function Get-LiveFrame {
    $Client = New-Object System.Net.WebClient
    try {
        $Timestamp = [DateTime]::UtcNow.Ticks
        $Bytes = $Client.DownloadData(
            "$BaseUrl/api/v1/vision/frame?t=$Timestamp"
        )
        return @{
            Bytes = $Bytes
            ContentType = $Client.ResponseHeaders["Content-Type"]
            Stale = $Client.ResponseHeaders["X-Vision-Frame-Stale"]
        }
    }
    finally {
        $Client.Dispose()
    }
}

Write-Host "Checking live Dashboard at $BaseUrl/dashboard"

$Health = Get-Utf8Json -Path "/health"
$PeopleBefore = Get-Utf8Json -Path "/api/v1/vision/people"
$Frame = Get-LiveFrame
Start-Sleep -Seconds 2
$PeopleAfter = Get-Utf8Json -Path "/api/v1/vision/people"

$IsJpeg = (
    $Frame.Bytes.Length -gt 1000 -and
    $Frame.Bytes[0] -eq 0xFF -and
    $Frame.Bytes[1] -eq 0xD8
)
if (
    $Health.status -ne "ok" -or
    $PeopleBefore.stale -ne $false -or
    $PeopleAfter.stale -ne $false -or
    $PeopleAfter.frame_id -le $PeopleBefore.frame_id -or
    $Frame.ContentType -notmatch "image/jpeg" -or
    $Frame.Stale -ne "false" -or
    -not $IsJpeg
) {
    throw "Live Dashboard acceptance check failed"
}

Write-Host ""
Write-Host "Live Dashboard acceptance summary:"
Write-Host "API status: $($Health.status)"
Write-Host "Frame ID: $($PeopleBefore.frame_id) -> $($PeopleAfter.frame_id)"
Write-Host "Vision stale: $($PeopleAfter.stale)"
Write-Host "People: $($PeopleAfter.current_people)"
Write-Host "JPEG content type: $($Frame.ContentType)"
Write-Host "JPEG bytes: $($Frame.Bytes.Length)"
Write-Host "Frame stale header: $($Frame.Stale)"
Write-Host "Dashboard URL: $BaseUrl/dashboard"
Write-Host "Live Dashboard smoke test passed."
