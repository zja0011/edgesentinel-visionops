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

Write-Host "Checking Dashboard zone draft editor at $BaseUrl/dashboard"

$Payload = (Get-Utf8Text -Path "/api/v1/zones") |
    ConvertFrom-Json
$Zones = @($Payload.zones)
$ExpectedReadOnly = -not [bool]$Payload.save_enabled
if (
    $Payload.coordinate_space -ne "normalized" -or
    $Payload.read_only -ne $ExpectedReadOnly -or
    $Payload.count -ne 2 -or
    $Zones.Count -ne 2
) {
    $Payload | ConvertTo-Json -Depth 10
    throw "Zone API contract validation failed"
}

foreach ($Zone in $Zones) {
    $Points = @($Zone.polygon)
    if ($Points.Count -lt 3) {
        throw "A configured zone has fewer than three points"
    }
    foreach ($Point in $Points) {
        if (
            $Point.Count -ne 2 -or
            $Point[0] -lt 0 -or
            $Point[0] -gt 1 -or
            $Point[1] -lt 0 -or
            $Point[1] -gt 1
        ) {
            throw "A zone point is outside normalized coordinates"
        }
    }
}

$Left = $Zones | Where-Object { $_.id -eq "left_zone" }
$Right = $Zones | Where-Object { $_.id -eq "right_zone" }
if ($null -eq $Left -or $null -eq $Right) {
    throw "Expected left_zone and right_zone"
}
$LeftMaxX = (
    @($Left.polygon | ForEach-Object { [double]$_[0] }) |
        Measure-Object -Maximum
).Maximum
$RightMinX = (
    @($Right.polygon | ForEach-Object { [double]$_[0] }) |
        Measure-Object -Minimum
).Minimum
$NeutralBand = [math]::Round(
    ([double]$RightMinX - [double]$LeftMaxX) * 100,
    1
)

$Html = Get-Utf8Text -Path "/dashboard"
$JavaScript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Html -notmatch "zone-canvas" -or
    $Html -notmatch "zone-draw-toggle" -or
    $JavaScript -notmatch "drawZoneCanvas" -or
    $JavaScript -notmatch "addDraftPoint"
) {
    throw "Dashboard zone editor assets are incomplete"
}

Write-Host ""
Write-Host "Zone Dashboard acceptance summary:"
Write-Host "Coordinate space: $($Payload.coordinate_space)"
Write-Host "Read only: $($Payload.read_only)"
Write-Host "Save enabled: $($Payload.save_enabled)"
Write-Host "Zone count: $($Payload.count)"
Write-Host "Zone IDs: $($Zones.id -join ', ')"
Write-Host "Neutral band: $NeutralBand%"
Write-Host "Draft editor assets: ready"
Write-Host "Zone Dashboard smoke test passed."
