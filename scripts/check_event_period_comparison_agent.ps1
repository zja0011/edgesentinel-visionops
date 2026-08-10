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
    catch [System.Net.WebException] {
        $Response = $_.Exception.Response
        if ($null -eq $Response) {
            throw
        }
        $Status = [int]$Response.StatusCode
        $Reader = New-Object System.IO.StreamReader(
            $Response.GetResponseStream(),
            [System.Text.Encoding]::UTF8
        )
        try {
            $ErrorBody = $Reader.ReadToEnd()
        }
        finally {
            $Reader.Dispose()
        }
        throw "POST $Path failed: HTTP $Status $ErrorBody"
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

function Assert-Comparison {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Comparison = $Payload.comparison
    $Current = [int]$Comparison.current_total
    $Previous = [int]$Comparison.previous_total
    $Change = [int]$Comparison.absolute_change
    $ExpectedChange = $Current - $Previous
    $ExpectedDirection = if ($ExpectedChange -gt 0) {
        "INCREASE"
    }
    elseif ($ExpectedChange -lt 0) {
        "DECREASE"
    }
    else {
        "UNCHANGED"
    }
    if (
        [int]$Payload.window.minutes -ne 1440 -or
        [string]$Payload.window.timezone -ne "Asia/Shanghai" -or
        $Current -ne [int]$Payload.total_events -or
        $Change -ne $ExpectedChange -or
        [string]$Comparison.direction -ne $ExpectedDirection -or
        [int]$Comparison.previous_window.minutes -ne 1440 -or
        [string]$Comparison.previous_window.timezone -ne (
            "Asia/Shanghai"
        ) -or
        [string]$Comparison.previous_window.until_timestamp -ne (
            [string]$Payload.window.since_timestamp
        ) -or
        [string]$Payload.filters.status -ne "OPEN" -or
        [string]$Payload.filters.severity -ne "INFO" -or
        $Payload.read_only -ne $true
    ) {
        throw "$Source period comparison contract is invalid"
    }
    $PreviousStart = [DateTimeOffset]::Parse(
        [string]$Comparison.previous_window.since_timestamp
    )
    $PreviousEnd = [DateTimeOffset]::Parse(
        [string]$Comparison.previous_window.until_timestamp
    )
    if (
        ($PreviousEnd - $PreviousStart).TotalMinutes -ne 1440
    ) {
        throw "$Source previous window is not 1440 minutes"
    }
    if ($Previous -eq 0) {
        if ($null -ne $Comparison.percent_change) {
            throw "$Source zero baseline percent must be null"
        }
    }
    else {
        $ExpectedPercent = [Math]::Round(
            ($ExpectedChange / [double]$Previous) * 100.0,
            2
        )
        if (
            [Math]::Abs(
                [double]$Comparison.percent_change -
                $ExpectedPercent
            ) -gt 0.01
        ) {
            throw "$Source percent change is invalid"
        }
    }
    return @{
        Current = $Current
        Previous = $Previous
        Change = $Change
        Direction = $ExpectedDirection
        Percent = $Comparison.percent_change
    }
}

Write-Host (
    "Checking equal-window event comparisons at " +
    "$BaseUrl"
)

Assert-HttpStatus `
    -Path (
        "/api/v1/events/summary/recent?" +
        "minutes=1440&compare_previous=maybe"
    ) `
    -ExpectedStatus 422

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=1440&recent_limit=5&compare_previous=true" +
    "&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectStats = Assert-Comparison `
    -Payload $Direct `
    -Source "Direct API"

$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$SummaryTool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "event.summarize"
    }
)
if (
    $SummaryTool.Count -ne 1 -or
    $SummaryTool[0].annotations.riskLevel -ne "L0" -or
    $SummaryTool[0].annotations.readOnlyHint -ne $true -or
    $SummaryTool[0].annotations.requiresConfirmation -ne $false -or
    [string]$SummaryTool[0].inputSchema.properties.compare_previous.type -ne
        "boolean"
) {
    throw "Period comparison schema or policy is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.summarize/invoke" `
    -Payload @{
        minutes = 1440
        recent_limit = 5
        compare_previous = $true
        status = "OPEN"
        severity = "INFO"
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "event.summarize"
) {
    throw "Harness period comparison failed"
}
$HarnessStats = Assert-Comparison `
    -Payload $Harness.result `
    -Source "Harness"
if (
    $HarnessStats.Current -ne $DirectStats.Current -or
    $HarnessStats.Previous -ne $DirectStats.Previous
) {
    throw "Direct and Harness comparisons differ"
}

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Event comparison for open INFO events from " +
            "the last 1440 minutes"
        )
    }
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
    $Results[0].tool_name -ne "event.summarize" -or
    $Results[0].status -ne "SUCCEEDED" -or
    $WriteCalls.Count -ne 0 -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent period comparison failed"
}
$AgentStats = Assert-Comparison `
    -Payload $Results[0].result `
    -Source "Agent"
if (
    $AgentStats.Current -ne $DirectStats.Current -or
    $AgentStats.Previous -ne $DirectStats.Previous
) {
    throw "Direct and Agent comparisons differ"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [int]$Checkpoint.tool_results[0].result.comparison.current_total -ne
        $DirectStats.Current -or
    [int]$Checkpoint.tool_results[0].result.comparison.previous_total -ne
        $DirectStats.Previous
) {
    throw "Period comparison checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-summary"' -or
    $Javascript -notmatch (
        'parameters.set\("compare_previous", "true"\)'
    ) -or
    $Javascript -notmatch 'comparison.direction' -or
    $Javascript -notmatch 'comparison.absolute_change'
) {
    throw "Dashboard period comparison assets are incomplete"
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
Write-Host "Event Period Comparison acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host "Current window minutes: 1440"
Write-Host "Previous window minutes: 1440"
Write-Host "Current events: $($DirectStats.Current)"
Write-Host "Previous events: $($DirectStats.Previous)"
Write-Host "Absolute change: $($DirectStats.Change)"
Write-Host "Percent change: $($DirectStats.Percent)"
Write-Host "Direction: $($DirectStats.Direction)"
Write-Host "Invalid boolean rejected: HTTP 422"
Write-Host "Direct/Harness/Agent comparisons match: True"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard comparison assets: ready"
Write-Host "Event Period Comparison smoke test passed."
