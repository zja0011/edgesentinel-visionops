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

if ($Minutes -lt 1 -or $Minutes -gt 1440) {
    throw "Minutes must be between 1 and 1440"
}

Write-Host "Checking bounded recent-event queries at $BaseUrl"

$EncodedClass = [Uri]::EscapeDataString("bottle")
$Direct = Invoke-Utf8Get -Path (
    "/api/v1/events?minutes=$Minutes" +
    "&object_class=$EncodedClass&limit=5"
)
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$ToolDefinition = @(
    $Tools.tools | Where-Object { $_.name -eq "event.query" }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false -or
    [int]$ToolDefinition[0].inputSchema.properties.minutes.minimum -ne 1 -or
    [int]$ToolDefinition[0].inputSchema.properties.minutes.maximum -ne 1440
) {
    throw "event.query time-window schema or policy is invalid"
}

if (
    [int]$Direct.window.minutes -ne $Minutes -or
    $Direct.window.timezone -ne "Asia/Shanghai" -or
    $Direct.read_only -ne $true -or
    [int]$Direct.count -gt 5
) {
    $Direct | ConvertTo-Json -Depth 10
    throw "Direct event-window response is invalid"
}

$Since = [DateTimeOffset]::Parse(
    [string]$Direct.window.since_timestamp
)
foreach ($EventRecord in @($Direct.events)) {
    if (
        [DateTimeOffset]::Parse(
            [string]$EventRecord.timestamp
        ) -lt $Since
    ) {
        throw "Direct API returned an event outside the window"
    }
}

$Harness = Invoke-Utf8Post `
    -Path "/api/v1/harness/tools/event.query/invoke" `
    -Payload @{
        minutes = $Minutes
        object_class = "bottle"
        limit = 5
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    [int]$Harness.result.window.minutes -ne $Minutes -or
    $Harness.result.read_only -ne $true
) {
    $Harness | ConvertTo-Json -Depth 10
    throw "Harness event-window query failed"
}

$Task = Invoke-Utf8Post `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Query bottle events from the last " +
            "${Minutes} minutes"
        )
    }
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "event.query" -or
    $Results[0].status -ne "SUCCEEDED" -or
    [int]$Results[0].result.window.minutes -ne $Minutes -or
    $Results[0].result.read_only -ne $true -or
    -not ([string]$Task.answer).Contains([string]$Minutes)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent event-window query failed"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [int]$Checkpoint.tool_results[0].result.window.minutes -ne (
        $Minutes
    )
) {
    throw "Agent event-window checkpoint does not match"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-minutes-filter"' -or
    $Dashboard -notmatch 'value="1440"' -or
    $Javascript -notmatch 'eventMinutesFilter' -or
    $Javascript -notmatch 'parameters\.set\("minutes", minutes\)'
) {
    throw "Dashboard event-window assets are incomplete"
}

Write-Host ""
Write-Host "Event Window acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Window minutes: $Minutes"
Write-Host "Timezone: $($Results[0].result.window.timezone)"
Write-Host "Since: $($Results[0].result.window.since_timestamp)"
Write-Host "Queried at: $($Results[0].result.window.queried_at)"
Write-Host "Direct event count: $($Direct.count)"
Write-Host "Harness event count: $($Harness.result.count)"
Write-Host "Agent event count: $($Results[0].result.count)"
Write-Host "Read only: $($Results[0].result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard time-window filter: ready"
Write-Host "Event Window smoke test passed."
