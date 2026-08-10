param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"

function Invoke-Utf8JsonGet {
    param([string]$Path)
    $Client = New-Object System.Net.WebClient
    try {
        $Bytes = $Client.DownloadData("$BaseUrl$Path")
        return [System.Text.Encoding]::UTF8.GetString(
            $Bytes
        ) | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

function Invoke-Utf8JsonPost {
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

function Assert-HttpStatus {
    param(
        [string]$Path,
        [int]$ExpectedStatus
    )
    try {
        $null = Invoke-Utf8JsonGet -Path $Path
    }
    catch [System.Net.WebException] {
        $Response = $_.Exception.Response
        if (
            $null -ne $Response -and
            [int]$Response.StatusCode -eq $ExpectedStatus
        ) {
            return
        }
        throw
    }
    throw "Expected HTTP $ExpectedStatus from $Path"
}

function Assert-OpenQuery {
    param(
        [object]$Payload,
        [string]$Source,
        [int]$Maximum
    )
    $Events = @($Payload.events)
    if (
        [string]$Payload.filters.status -ne "OPEN" -or
        [int]$Payload.count -ne $Events.Count -or
        $Events.Count -gt $Maximum -or
        $Payload.read_only -ne $true
    ) {
        throw "$Source open-event result is invalid"
    }
    foreach ($Event in $Events) {
        if (
            [string]$Event.status -ne "OPEN" -and
            [string]$Event.disposition_status -ne "OPEN"
        ) {
            throw "$Source returned a non-open event"
        }
    }
}

Write-Host (
    "Checking event disposition filters at " +
    "$BaseUrl"
)

Assert-HttpStatus `
    -Path "/api/v1/events?status=DELETED" `
    -ExpectedStatus 422

$Direct = Invoke-Utf8JsonGet -Path (
    "/api/v1/events?limit=20&minutes=1440&status=OPEN"
)
Assert-OpenQuery `
    -Payload $Direct `
    -Source "Direct API" `
    -Maximum 20
if ([int]$Direct.count -lt 1) {
    throw "No OPEN event is available for acceptance"
}

$Summary = Invoke-Utf8JsonGet -Path (
    "/api/v1/events/summary/recent?" +
    "minutes=1440&recent_limit=10&status=OPEN"
)
if (
    [string]$Summary.filters.status -ne "OPEN" -or
    [int]$Summary.total_events -lt [int]$Direct.count -or
    @($Summary.recent_events).Count -gt 10 -or
    $Summary.read_only -ne $true
) {
    throw "Open-event summary is invalid"
}
foreach ($Event in @($Summary.recent_events)) {
    if ([string]$Event.status -ne "OPEN") {
        throw "Open-event summary contains another disposition"
    }
}

$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$QueryTool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "event.query"
    }
)
$SummaryTool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "event.summarize"
    }
)
if (
    $QueryTool.Count -ne 1 -or
    $SummaryTool.Count -ne 1 -or
    $QueryTool[0].annotations.riskLevel -ne "L0" -or
    $QueryTool[0].annotations.readOnlyHint -ne $true -or
    $QueryTool[0].annotations.requiresConfirmation -ne $false -or
    $SummaryTool[0].annotations.riskLevel -ne "L0" -or
    $SummaryTool[0].annotations.readOnlyHint -ne $true -or
    $SummaryTool[0].annotations.requiresConfirmation -ne $false -or
    @($QueryTool[0].inputSchema.properties.status.enum) -notcontains (
        "OPEN"
    ) -or
    @($QueryTool[0].inputSchema.properties.status.enum) -notcontains (
        "ACKNOWLEDGED"
    )
) {
    throw "Event disposition filter schema is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.query/invoke" `
    -Payload @{
        limit = 20
        minutes = 1440
        status = "OPEN"
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "event.query"
) {
    throw "Harness open-event query failed"
}
Assert-OpenQuery `
    -Payload $Harness.result `
    -Source "Harness" `
    -Maximum 20

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "Show open events" }
$Results = @($Task.tool_results)
$WriteCalls = @(
    $Results | Where-Object {
        $_.tool_name -in @(
            "event.acknowledge",
            "system.cleanup_retained_data",
            "camera.restart",
            "camera.capture_snapshot",
            "report.generate"
        )
    }
)
if (
    $Task.status -ne "COMPLETED" -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "event.query" -or
    $Results[0].status -ne "SUCCEEDED" -or
    $WriteCalls.Count -ne 0 -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent open-event query failed"
}
Assert-OpenQuery `
    -Payload $Results[0].result `
    -Source "Agent" `
    -Maximum 5

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $null -ne $Checkpoint.pending_confirmation
) {
    throw "Open-event checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-status-filter"' -or
    $Dashboard -notmatch '<option value="OPEN">' -or
    $Dashboard -notmatch '<option value="ACKNOWLEDGED">' -or
    $Javascript -notmatch 'eventStatusFilter' -or
    $Javascript -notmatch 'parameters.set\("status", status\)'
) {
    throw "Dashboard disposition filter assets are incomplete"
}

$McpTools = @(
    $Tools.tools | Where-Object {
        $_.annotations.readOnlyHint -eq $true -and
        $_.annotations.riskLevel -eq "L0" -and
        $_.annotations.autoExecute -eq $true -and
        $_.annotations.requiresConfirmation -eq $false
    }
)
if ($McpTools.Count -ne 25) {
    throw "MCP read-only tool count is not 25"
}

Write-Host ""
Write-Host "Event Disposition Filter acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($QueryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $QueryTool[0].annotations.requiresConfirmation
)
Write-Host "Filter: OPEN"
Write-Host "Window minutes: 1440"
Write-Host "Direct open events: $($Direct.count)"
Write-Host "Summary open events: $($Summary.total_events)"
Write-Host "Harness open events: $($Harness.result.count)"
Write-Host "Agent open events: $($Results[0].result.count)"
Write-Host "Invalid status rejected: HTTP 422"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard disposition filter: ready"
Write-Host "Event Disposition Filter smoke test passed."
