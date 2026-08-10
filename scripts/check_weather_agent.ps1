param(
    [Parameter(Mandatory = $true)]
    [ValidateLength(2, 80)]
    [string]$Location,
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-JsonPost {
    param(
        [string]$Uri,
        [hashtable]$Body
    )
    $Json = $Body | ConvertTo-Json -Depth 10 -Compress
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    $Client.Headers["Content-Type"] =
        "application/json; charset=utf-8"
    $Bytes = $Client.UploadData(
        $Uri,
        "POST",
        $Utf8.GetBytes($Json)
    )
    return (
        $Utf8.GetString($Bytes) |
            ConvertFrom-Json
    )
}

function Invoke-JsonGet {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    $Bytes = $Client.DownloadData($Uri)
    return (
        $Utf8.GetString($Bytes) |
            ConvertFrom-Json
    )
}

Write-Host "Checking external current weather at $BaseUrl"
if (
    $Location.Trim() -eq "你的城市" -or
    $Location.Trim().ToLowerInvariant() -eq "your city"
) {
    throw "Replace the documentation placeholder with a concrete city, for example Chengdu"
}
$EncodedLocation = [Uri]::EscapeDataString($Location)
$Direct = Invoke-JsonGet `
    -Uri "$BaseUrl/api/v1/weather/current?location=$EncodedLocation"

if (
    $Direct.provider -ne "open-meteo" -or
    -not $Direct.external_request -or
    -not $Direct.read_only -or
    $null -eq $Direct.current.temperature_c
) {
    throw "Direct weather result is invalid"
}

$Task = Invoke-JsonPost `
    -Uri "$BaseUrl/api/v1/agent/tasks" `
    -Body @{ message = "current weather in $Location" }
$WeatherTools = @(
    $Task.tool_results |
        Where-Object { $_.tool_name -eq "weather.get_current" }
)
if (
    $Task.status -ne "COMPLETED" -or
    $WeatherTools.Count -ne 1 -or
    $WeatherTools[0].status -ne "SUCCEEDED"
) {
    throw "Agent did not complete one weather tool call"
}
$Result = $WeatherTools[0].result
if (
    -not $Result.external_request -or
    -not $Result.read_only -or
    $null -eq $Result.current.temperature_c
) {
    throw "Agent weather result is invalid"
}

$WebClient = New-Object System.Net.WebClient
$WebClient.Encoding = [System.Text.Encoding]::UTF8
$Html = $WebClient.DownloadString("$BaseUrl/dashboard")
$Javascript = $WebClient.DownloadString(
    "$BaseUrl/dashboard/assets/dashboard.js"
)
if (
    $Html -notmatch 'id="weather-prompt"' -or
    $Html -notmatch 'id="mcp-runtime-status"' -or
    $Javascript -notmatch "agentModelMode"
) {
    throw "Dashboard weather or model-switch assets are incomplete"
}

Write-Host
Write-Host "Weather Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Model: $($Task.model)"
Write-Host "Tool: weather.get_current $($WeatherTools[0].status)"
Write-Host "Risk: L0"
Write-Host "Confirmation required: False"
Write-Host "Provider: $($Result.provider)"
Write-Host "Location: $($Result.location.name)"
Write-Host "Temperature: $($Result.current.temperature_c) C"
Write-Host "Condition: $($Result.current.condition)"
Write-Host "External request: $($Result.external_request)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard weather prompt: ready"
Write-Host "Weather Agent smoke test passed."
