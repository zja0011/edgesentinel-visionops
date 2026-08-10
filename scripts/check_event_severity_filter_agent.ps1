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

function Assert-OpenInfoQuery {
    param(
        [object]$Payload,
        [string]$Source,
        [int]$Maximum
    )
    $Events = @($Payload.events)
    if (
        [string]$Payload.filters.status -ne "OPEN" -or
        [string]$Payload.filters.severity -ne "INFO" -or
        [int]$Payload.count -ne $Events.Count -or
        $Events.Count -gt $Maximum -or
        $Payload.read_only -ne $true
    ) {
        throw "$Source OPEN INFO result is invalid"
    }
    foreach ($Event in $Events) {
        $Disposition = [string]$Event.status
        if ([string]::IsNullOrWhiteSpace($Disposition)) {
            $Disposition = [string]$Event.disposition_status
        }
        if (
            $Disposition -ne "OPEN" -or
            [string]$Event.severity -ne "INFO"
        ) {
            throw "$Source returned an event outside the filter"
        }
    }
}

Write-Host (
    "Checking event severity filters at " +
    "$BaseUrl"
)

Assert-HttpStatus `
    -Path "/api/v1/events?severity=UNKNOWN" `
    -ExpectedStatus 422

$Direct = Invoke-Utf8JsonGet -Path (
    "/api/v1/events?limit=20&minutes=1440" +
    "&status=OPEN&severity=INFO"
)
Assert-OpenInfoQuery `
    -Payload $Direct `
    -Source "Direct API" `
    -Maximum 20
if ([int]$Direct.count -lt 1) {
    throw "No OPEN INFO event is available for acceptance"
}

$Summary = Invoke-Utf8JsonGet -Path (
    "/api/v1/events/summary/recent?" +
    "minutes=1440&recent_limit=10" +
    "&status=OPEN&severity=INFO"
)
if (
    [string]$Summary.filters.status -ne "OPEN" -or
    [string]$Summary.filters.severity -ne "INFO" -or
    [int]$Summary.total_events -lt [int]$Direct.count -or
    @($Summary.recent_events).Count -gt 10 -or
    $Summary.read_only -ne $true
) {
    throw "OPEN INFO event summary is invalid"
}
foreach ($Event in @($Summary.recent_events)) {
    if (
        [string]$Event.status -ne "OPEN" -or
        [string]$Event.severity -ne "INFO"
    ) {
        throw "Event summary contains an event outside the filter"
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
$ExpectedSeverities = @(
    "INFO",
    "MEDIUM",
    "HIGH",
    "CRITICAL"
)
if (
    $QueryTool.Count -ne 1 -or
    $SummaryTool.Count -ne 1 -or
    $QueryTool[0].annotations.riskLevel -ne "L0" -or
    $QueryTool[0].annotations.readOnlyHint -ne $true -or
    $QueryTool[0].annotations.requiresConfirmation -ne $false -or
    $SummaryTool[0].annotations.riskLevel -ne "L0" -or
    $SummaryTool[0].annotations.readOnlyHint -ne $true -or
    $SummaryTool[0].annotations.requiresConfirmation -ne $false
) {
    throw "Event severity filter policy is invalid"
}
foreach ($Severity in $ExpectedSeverities) {
    if (
        @(
            $QueryTool[0].inputSchema.properties.severity.enum
        ) -notcontains $Severity -or
        @(
            $SummaryTool[0].inputSchema.properties.severity.enum
        ) -notcontains $Severity
    ) {
        throw "Event severity filter schema is incomplete"
    }
}

$Harness = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.query/invoke" `
    -Payload @{
        limit = 20
        minutes = 1440
        status = "OPEN"
        severity = "INFO"
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "event.query"
) {
    throw "Harness OPEN INFO query failed"
}
Assert-OpenInfoQuery `
    -Payload $Harness.result `
    -Source "Harness" `
    -Maximum 20

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "Show open INFO events" }
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
    throw "Agent OPEN INFO query failed"
}
Assert-OpenInfoQuery `
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
    throw "Event severity checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-severity-filter"' -or
    $Dashboard -notmatch '<option value="INFO">' -or
    $Dashboard -notmatch '<option value="MEDIUM">' -or
    $Dashboard -notmatch '<option value="HIGH">' -or
    $Dashboard -notmatch '<option value="CRITICAL">' -or
    $Javascript -notmatch 'eventSeverityFilter' -or
    $Javascript -notmatch (
        'parameters.set\("severity", severity\)'
    )
) {
    throw "Dashboard severity filter assets are incomplete"
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
Write-Host "Event Severity Filter acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($QueryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $QueryTool[0].annotations.requiresConfirmation
)
Write-Host "Filter: OPEN + INFO"
Write-Host "Window minutes: 1440"
Write-Host "Direct matching events: $($Direct.count)"
Write-Host "Summary matching events: $($Summary.total_events)"
Write-Host "Harness matching events: $($Harness.result.count)"
Write-Host "Agent matching events: $($Results[0].result.count)"
Write-Host "Invalid severity rejected: HTTP 422"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard severity filter: ready"
Write-Host "Event Severity Filter smoke test passed."
