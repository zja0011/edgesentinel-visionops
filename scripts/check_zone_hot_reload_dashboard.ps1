param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [switch]$RequireReload,
    [switch]$RequireFactoryDefaults
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

Write-Host "Checking zone hot reload at $BaseUrl/dashboard"

$Zones = $null
$People = $null
$Matched = $false
for ($Attempt = 1; $Attempt -le 20; $Attempt += 1) {
    $Zones = Get-Utf8Json -Path "/api/v1/zones"
    $People = Get-Utf8Json -Path "/api/v1/vision/people"
    if (
        $null -ne $People.zone_config -and
        $People.zone_config.version -eq $Zones.config_version
    ) {
        $Matched = $true
        break
    }
    Start-Sleep -Seconds 1
}

if (
    -not $Matched -or
    $People.zone_config.enabled -ne $true -or
    $People.zone_config.status -ne "active" -or
    $People.zone_config.version -notmatch "^[0-9a-f]{64}$" -or
    $People.zone_config.check_interval_frames -ne 30
) {
    @{
        zones = $Zones
        people = $People
    } | ConvertTo-Json -Depth 10
    throw "Vision runtime did not synchronize the zone configuration"
}
if (
    $RequireReload -and
    [int]$People.zone_config.reload_count -lt 1
) {
    throw "The vision runtime has not observed a live reload"
}

$FactoryDefaultsActive = "not checked"
if ($RequireFactoryDefaults) {
    $Defaults = Get-Utf8Json -Path "/api/v1/zones/defaults"
    $CurrentZonesJson = ConvertTo-Json `
        -InputObject @($Zones.zones) `
        -Depth 10 `
        -Compress
    $DefaultZonesJson = ConvertTo-Json `
        -InputObject @($Defaults.zones) `
        -Depth 10 `
        -Compress
    if ($CurrentZonesJson -cne $DefaultZonesJson) {
        throw "The active zone configuration is not the factory default"
    }
    $FactoryDefaultsActive = "True"
}

$Html = Get-Utf8Text -Path "/dashboard"
$JavaScript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Html -notmatch "zone-runtime-status" -or
    $JavaScript -notmatch "updateZoneRuntimeStatus" -or
    $JavaScript -notmatch "people\.zone_config"
) {
    throw "Dashboard hot-reload status assets are incomplete"
}

$ShortVersion = $Zones.config_version.Substring(0, 12)
Write-Host ""
Write-Host "Zone Hot Reload acceptance summary:"
Write-Host "Runtime status: $($People.zone_config.status)"
Write-Host "API config version: $ShortVersion..."
Write-Host "Runtime config version: $($People.zone_config.version.Substring(0, 12))..."
Write-Host "Versions match: $Matched"
Write-Host "Check interval frames: $($People.zone_config.check_interval_frames)"
Write-Host "Reload count: $($People.zone_config.reload_count)"
Write-Host "Last reload frame: $($People.zone_config.last_reload_frame)"
Write-Host "Factory defaults active: $FactoryDefaultsActive"
Write-Host "Restart required: False"
Write-Host "Dashboard synchronization assets: ready"
Write-Host "Zone Hot Reload smoke test passed."
