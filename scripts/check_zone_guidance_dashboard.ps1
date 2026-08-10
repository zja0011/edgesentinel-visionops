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

Write-Host "Checking zone drawing guidance at $BaseUrl/dashboard"

$Current = (Get-Utf8Text -Path "/api/v1/zones") |
    ConvertFrom-Json
$Defaults = (Get-Utf8Text -Path "/api/v1/zones/defaults") |
    ConvertFrom-Json
if (
    $Defaults.source -ne "factory_default" -or
    $Defaults.read_only -ne $true -or
    $Defaults.coordinate_space -ne "normalized" -or
    $Defaults.default_version -notmatch "^[0-9a-f]{64}$" -or
    $Defaults.count -ne 2
) {
    $Defaults | ConvertTo-Json -Depth 10
    throw "Factory-default zone contract validation failed"
}

$Left = @($Defaults.zones) |
    Where-Object { $_.id -eq "left_zone" }
$Right = @($Defaults.zones) |
    Where-Object { $_.id -eq "right_zone" }
if ($null -eq $Left -or $null -eq $Right) {
    throw "Factory defaults are missing left_zone or right_zone"
}
if (
    $Left.anchor -ne "bottom_center" -or
    $Right.anchor -ne "bottom_center"
) {
    throw "Expected bottom_center anchors in factory defaults"
}
$LeftMaximumY = (
    @($Left.polygon | ForEach-Object { [double]$_[1] }) |
        Measure-Object -Maximum
).Maximum
$RightMaximumY = (
    @($Right.polygon | ForEach-Object { [double]$_[1] }) |
        Measure-Object -Maximum
).Maximum
if ($LeftMaximumY -ne 1.0 -or $RightMaximumY -ne 1.0) {
    throw "Factory-default person zones must reach y=1.0"
}

$Html = Get-Utf8Text -Path "/dashboard"
$JavaScript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Html -notmatch "zone-snap-bottom" -or
    $Html -notmatch "zone-restore-default" -or
    $Html -notmatch "zone-anchor-guidance" -or
    $JavaScript -notmatch "isDraftAnchorSafe" -or
    $JavaScript -notmatch "snapDraftBottom" -or
    $JavaScript -notmatch "restoreSelectedZoneDefault"
) {
    throw "Zone drawing guidance assets are incomplete"
}

Write-Host ""
Write-Host "Zone Guidance acceptance summary:"
Write-Host "Current zone count: $($Current.count)"
Write-Host "Default source: $($Defaults.source)"
Write-Host "Default zone count: $($Defaults.count)"
Write-Host "Default zone IDs: $($Defaults.zones.id -join ', ')"
Write-Host "Left anchor: $($Left.anchor)"
Write-Host "Left maximum Y: $LeftMaximumY"
Write-Host "Right maximum Y: $RightMaximumY"
Write-Host "Anchor warning assets: ready"
Write-Host "Bottom snap assets: ready"
Write-Host "Restore-default assets: ready"
Write-Host "Server configuration changed: False"
Write-Host "Zone Guidance smoke test passed."
