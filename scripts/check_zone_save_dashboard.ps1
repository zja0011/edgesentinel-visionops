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

Write-Host "Checking protected Dashboard zone saving at $BaseUrl/dashboard"

$Before = (Get-Utf8Text -Path "/api/v1/zones") |
    ConvertFrom-Json
if (
    $Before.save_enabled -ne $true -or
    $Before.read_only -ne $false -or
    $Before.config_version -notmatch "^[0-9a-f]{64}$" -or
    $Before.save_confirmation -ne "SAVE_ZONE_CONFIG"
) {
    $Before | ConvertTo-Json -Depth 10
    throw "Protected zone-save metadata validation failed"
}

$ProbeBody = @{
    expected_version = $Before.config_version
    confirmation = "SAVE_ZONE_CONFIG"
    coordinate_space = "normalized"
    zones = @($Before.zones)
} | ConvertTo-Json -Depth 10

$UnauthorizedStatus = 0
try {
    Invoke-RestMethod `
        -Uri "$BaseUrl/api/v1/zones" `
        -Method Put `
        -ContentType "application/json; charset=utf-8" `
        -Headers @{
            "X-EdgeSentinel-Config-Token" = "intentional-invalid-token"
        } `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($ProbeBody)) |
        Out-Null
    throw "An invalid administrator token was accepted"
}
catch {
    if ($null -ne $_.Exception.Response) {
        $UnauthorizedStatus = [int]$_.Exception.Response.StatusCode
    }
    if ($UnauthorizedStatus -ne 401) {
        throw
    }
}

$After = (Get-Utf8Text -Path "/api/v1/zones") |
    ConvertFrom-Json
if ($After.config_version -ne $Before.config_version) {
    throw "Unauthorized request changed the zone configuration"
}

$Html = Get-Utf8Text -Path "/dashboard"
$JavaScript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Html -notmatch "zone-save-form" -or
    $Html -notmatch "zone-admin-token" -or
    $Html -notmatch "SAVE_ZONE_CONFIG" -or
    $JavaScript -notmatch "saveZoneConfiguration" -or
    $JavaScript -notmatch "X-EdgeSentinel-Config-Token"
) {
    throw "Protected zone-save Dashboard assets are incomplete"
}

Write-Host ""
Write-Host "Protected Zone Save acceptance summary:"
Write-Host "Save enabled: $($Before.save_enabled)"
Write-Host "Read only: $($Before.read_only)"
Write-Host "Config version: $($Before.config_version.Substring(0, 12))..."
Write-Host "Invalid token rejected: HTTP $UnauthorizedStatus"
Write-Host "Unauthorized write changed config: False"
Write-Host "Version unchanged: True"
Write-Host "Backup/save editor assets: ready"
Write-Host "Protected Zone Save smoke test passed."
