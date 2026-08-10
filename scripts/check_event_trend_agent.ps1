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

function Assert-Trend {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Buckets = @($Payload.timeline.buckets)
    $BucketTotal = 0
    $Previous = ""
    foreach ($Bucket in $Buckets) {
        $Start = [string]$Bucket.start
        $Count = [int]$Bucket.count
        if (
            $Start -notmatch (
                '^\d{4}-\d{2}-\d{2}T\d{2}:' +
                '\d{2}:00\.000\+08:00$'
            ) -or
            $Count -lt 0 -or
            (
                -not [string]::IsNullOrWhiteSpace($Previous) -and
                [string]::CompareOrdinal($Start, $Previous) -le 0
            )
        ) {
            throw "$Source contains an invalid trend bucket"
        }
        $Previous = $Start
        $BucketTotal += $Count
    }
    if (
        [int]$Payload.window.minutes -ne 1440 -or
        [string]$Payload.window.timezone -ne "Asia/Shanghai" -or
        [int]$Payload.timeline.bucket_minutes -ne 60 -or
        [string]$Payload.timeline.timezone -ne "Asia/Shanghai" -or
        $Buckets.Count -ne 25 -or
        $BucketTotal -ne [int]$Payload.total_events -or
        [string]$Payload.filters.status -ne "OPEN" -or
        [string]$Payload.filters.severity -ne "INFO" -or
        $Payload.read_only -ne $true
    ) {
        throw "$Source event trend contract is invalid"
    }
    return @{
        BucketCount = $Buckets.Count
        BucketTotal = $BucketTotal
        PeakCount = [int](
            $Buckets |
                Measure-Object -Property count -Maximum
        ).Maximum
    }
}

Write-Host (
    "Checking bounded Beijing-time event trends at " +
    "$BaseUrl"
)

Assert-HttpStatus `
    -Path (
        "/api/v1/events/summary/recent?" +
        "minutes=1440&bucket_minutes=20"
    ) `
    -ExpectedStatus 422

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=1440&recent_limit=5&bucket_minutes=60" +
    "&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectStats = Assert-Trend `
    -Payload $Direct `
    -Source "Direct API"

$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$SummaryTool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "event.summarize"
    }
)
$BucketEnum = @(
    $SummaryTool[0].inputSchema.properties.bucket_minutes.enum
)
if (
    $SummaryTool.Count -ne 1 -or
    $SummaryTool[0].annotations.riskLevel -ne "L0" -or
    $SummaryTool[0].annotations.readOnlyHint -ne $true -or
    $SummaryTool[0].annotations.requiresConfirmation -ne $false -or
    $BucketEnum.Count -ne 3 -or
    $BucketEnum -notcontains 15 -or
    $BucketEnum -notcontains 30 -or
    $BucketEnum -notcontains 60
) {
    throw "Event trend schema or policy is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.summarize/invoke" `
    -Payload @{
        minutes = 1440
        recent_limit = 5
        bucket_minutes = 60
        status = "OPEN"
        severity = "INFO"
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "event.summarize"
) {
    throw "Harness event trend failed"
}
$HarnessStats = Assert-Trend `
    -Payload $Harness.result `
    -Source "Harness"
if (
    $Harness.result.total_events -ne $Direct.total_events -or
    $HarnessStats.BucketTotal -ne $DirectStats.BucketTotal
) {
    throw "Direct and Harness trend totals differ"
}

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Summarize open INFO events from the last " +
            "1440 minutes as a trend"
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
    throw "Agent event trend failed"
}
$AgentStats = Assert-Trend `
    -Payload $Results[0].result `
    -Source "Agent"
if ($AgentStats.BucketTotal -ne $DirectStats.BucketTotal) {
    throw "Agent and direct trend totals differ"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    @(
        $Checkpoint.tool_results[0].result.timeline.buckets
    ).Count -ne $DirectStats.BucketCount
) {
    throw "Event trend checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
$Stylesheet = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.css"
if (
    $Dashboard -notmatch 'id="event-trend"' -or
    $Javascript -notmatch (
        'parameters.set\("bucket_minutes", "60"\)'
    ) -or
    $Javascript -notmatch 'event-trend-bar' -or
    $Stylesheet -notmatch '\.event-trend' -or
    $Stylesheet -notmatch '\.event-trend-bar'
) {
    throw "Dashboard event trend assets are incomplete"
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
Write-Host "Event Trend acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host "Window minutes: 1440"
Write-Host "Bucket minutes: 60"
Write-Host "Timezone: Asia/Shanghai"
Write-Host "Buckets: $($DirectStats.BucketCount)"
Write-Host "Total events: $($Direct.total_events)"
Write-Host "Bucket total: $($DirectStats.BucketTotal)"
Write-Host "Peak bucket count: $($DirectStats.PeakCount)"
Write-Host "Invalid bucket rejected: HTTP 422"
Write-Host "Direct/Harness/Agent totals match: True"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard trend assets: ready"
Write-Host "Event Trend smoke test passed."
