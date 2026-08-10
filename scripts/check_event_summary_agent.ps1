param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [int]$Minutes = 1440
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

function Invoke-Utf8Get {
    param([string]$Path)
    return (Get-Utf8Text -Path $Path) | ConvertFrom-Json
}

function Invoke-Utf8Post {
    param(
        [string]$Path,
        [hashtable]$Payload
    )
    $Json = $Payload | ConvertTo-Json -Compress
    $Body = [System.Text.Encoding]::UTF8.GetBytes($Json)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Content-Type"] = (
            "application/json; charset=utf-8"
        )
        $Bytes = $Client.UploadData(
            "$BaseUrl$Path",
            "POST",
            $Body
        )
        return [System.Text.Encoding]::UTF8.GetString(
            $Bytes
        ) | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

function Test-Summary {
    param($Summary)
    $TypeTotal = 0
    foreach ($Item in @($Summary.counts.by_event_type)) {
        $TypeTotal += [int]$Item.count
    }
    $Raw = $Summary | ConvertTo-Json -Depth 12
    return (
        [int]$Summary.window.minutes -eq $Minutes -and
        $Summary.window.timezone -eq "Asia/Shanghai" -and
        $Summary.filters.object_class -eq "bottle" -and
        [int]$Summary.total_events -eq $TypeTotal -and
        @($Summary.recent_events).Count -le 5 -and
        $Summary.read_only -eq $true -and
        $Raw -notmatch '"details"' -and
        $Raw -notmatch '"evidence_path"'
    )
}

if ($Minutes -lt 1 -or $Minutes -gt 1440) {
    throw "Minutes must be between 1 and 1440"
}

Write-Host "Checking bounded event summaries at $BaseUrl"

$Direct = Invoke-Utf8Get -Path (
    "/api/v1/events/summary/recent?minutes=$Minutes" +
    "&object_class=bottle&recent_limit=5"
)
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "event.summarize"
    }
)
$McpTools = @(
    $Tools.tools | Where-Object {
        $_.annotations.readOnlyHint -eq $true -and
        $_.annotations.riskLevel -eq "L0" -and
        $_.annotations.autoExecute -eq $true -and
        $_.annotations.requiresConfirmation -eq $false
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false -or
    [int]$ToolDefinition[0].inputSchema.properties.minutes.maximum -ne 1440 -or
    [int]$ToolDefinition[0].inputSchema.properties.recent_limit.maximum -ne 10 -or
        $McpTools.Count -ne 25
) {
    throw "event.summarize schema or policy is invalid"
}
if (-not (Test-Summary -Summary $Direct)) {
    $Direct | ConvertTo-Json -Depth 12
    throw "Direct event summary is invalid"
}

$Harness = Invoke-Utf8Post `
    -Path "/api/v1/harness/tools/event.summarize/invoke" `
    -Payload @{
        minutes = $Minutes
        object_class = "bottle"
        recent_limit = 5
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    -not (Test-Summary -Summary $Harness.result)
) {
    $Harness | ConvertTo-Json -Depth 12
    throw "Harness event summary failed"
}

$Task = Invoke-Utf8Post `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Summarize bottle events from the last " +
            "${Minutes} minutes"
        )
    }
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "event.summarize" -or
    $Results[0].status -ne "SUCCEEDED" -or
    -not (Test-Summary -Summary $Results[0].result) -or
    -not ([string]$Task.answer).Contains([string]$Minutes)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent event summary failed"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.tool_results[0].tool_name -ne "event.summarize" -or
    [int]$Checkpoint.tool_results[0].result.total_events -ne (
        [int]$Results[0].result.total_events
    )
) {
    throw "Agent event summary checkpoint does not match"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-summary"' -or
    $Dashboard -notmatch '16[^<]*5[^<]*3' -or
    $Javascript -notmatch (
        'eventSummary: "/api/v1/events/summary/recent"'
    ) -or
    $Javascript -notmatch 'renderEventSummary' -or
    $Javascript -notmatch 'buildEventSummaryUrl'
) {
    throw "Dashboard event-summary assets are incomplete"
}

Write-Host ""
Write-Host "Event Summary acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Window minutes: $Minutes"
Write-Host "Object class: bottle"
Write-Host "Total events: $($Results[0].result.total_events)"
Write-Host "Event type groups: $(@($Results[0].result.counts.by_event_type).Count)"
Write-Host "Recent event headers: $(@($Results[0].result.recent_events).Count)"
Write-Host "Details exposed: False"
Write-Host "Evidence paths exposed: False"
Write-Host "Read only: $($Results[0].result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard event summary: ready"
Write-Host "Event Summary smoke test passed."
