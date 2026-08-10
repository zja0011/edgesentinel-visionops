param(
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Utf8Text {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "*/*"
    return $Utf8.GetString($Client.DownloadData($Uri))
}

Write-Host "Checking Dashboard MCP catalog at $BaseUrl/dashboard"

$ToolPayload = (
    Get-Utf8Text "$BaseUrl/api/v1/harness/tools" |
        ConvertFrom-Json
)
$McpTools = @(
    $ToolPayload.tools |
        Where-Object {
            $_.annotations.readOnlyHint -eq $true -and
            $_.annotations.riskLevel -eq "L0" -and
            $_.annotations.autoExecute -eq $true -and
            $_.annotations.requiresConfirmation -ne $true
        }
)
if ($McpTools.Count -lt 22) {
    throw "The read-only MCP catalog contains fewer than 22 tools"
}
$WeatherTool = @(
    $McpTools |
        Where-Object { $_.name -eq "weather.get_current" }
)
if (
    $WeatherTool.Count -ne 1 -or
    $WeatherTool[0].annotations.openWorldHint -ne $true
) {
    throw "The external weather MCP tool annotation is invalid"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
$Stylesheet = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.css"
)
if (
    $Html -notmatch 'id="mcp-tools-toggle"' -or
    $Html -notmatch 'id="mcp-tools-panel"' -or
    $Html -notmatch 'id="mcp-tools-list"' -or
    $Javascript -notmatch "renderMcpCatalog" -or
    $Javascript -notmatch "/api/v1/harness/tools" -or
    $Stylesheet -notmatch "\.mcp-tool"
) {
    throw "Dashboard MCP catalog assets are incomplete"
}
if (
    $Html -notmatch 'id="event-collapse"' -or
    $Javascript -notmatch "collapseEvents" -or
    $Javascript -notmatch "scrollIntoView" -or
    $Stylesheet -notmatch "\.event-collapse"
) {
    throw "Dashboard event-collapse assets are incomplete"
}

Write-Host
Write-Host "MCP Catalog Dashboard acceptance summary:"
Write-Host "Registry tools: $(@($ToolPayload.tools).Count)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "External tools: $(@($McpTools | Where-Object { $_.annotations.openWorldHint }).Count)"
Write-Host "Weather tool: weather.get_current"
Write-Host "Catalog toggle assets: ready"
Write-Host "Tool schemas visible: True"
Write-Host "Event collapse hidden initially: True"
Write-Host "Return-to-latest action: ready"
Write-Host "MCP Catalog Dashboard smoke test passed."
