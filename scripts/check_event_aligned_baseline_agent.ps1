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

function Get-ExpectedHttpStatus {
    param(
        [string]$Path,
        [int]$ExpectedStatus
    )
    $Client = New-Object System.Net.WebClient
    try {
        $null = $Client.DownloadData("$BaseUrl$Path")
        throw "GET $Path unexpectedly succeeded"
    }
    catch [System.Net.WebException] {
        if ($null -eq $_.Exception.Response) {
            throw
        }
        $Status = [int]$_.Exception.Response.StatusCode
        if ($Status -ne $ExpectedStatus) {
            throw (
                "GET $Path returned HTTP $Status, expected " +
                "$ExpectedStatus"
            )
        }
        return $Status
    }
    finally {
        $Client.Dispose()
    }
}

function Assert-AlignedBaseline {
    param(
        [object]$Payload,
        [string]$Source
    )
    if ($null -eq $Payload.comparison) {
        throw "$Source comparison is missing"
    }
    $Current = $Payload.window
    $Previous = $Payload.comparison.previous_window
    if (
        [int]$Current.minutes -ne 60 -or
        [int]$Previous.minutes -ne 60 -or
        [int]$Previous.offset_minutes -ne 1440 -or
        [string]$Previous.alignment -ne "OFFSET" -or
        [string]$Previous.timezone -ne "Asia/Shanghai"
    ) {
        throw "$Source aligned window metadata is invalid"
    }

    $CurrentSince = [DateTimeOffset]::Parse(
        [string]$Current.since_timestamp
    )
    $PreviousSince = [DateTimeOffset]::Parse(
        [string]$Previous.since_timestamp
    )
    $PreviousUntil = [DateTimeOffset]::Parse(
        [string]$Previous.until_timestamp
    )
    $PreviousLength = (
        $PreviousUntil - $PreviousSince
    ).TotalMinutes
    $Offset = (
        $CurrentSince - $PreviousSince
    ).TotalMinutes
    if (
        [Math]::Abs($PreviousLength - 60.0) -gt 0.01 -or
        [Math]::Abs($Offset - 1440.0) -gt 0.01 -or
        $PreviousUntil -gt $CurrentSince
    ) {
        throw "$Source aligned window boundaries are invalid"
    }
    if (
        [int]$Payload.comparison.current_total -ne
            [int]$Payload.total_events
    ) {
        throw "$Source comparison arithmetic is invalid"
    }
    return $Previous
}

Write-Host (
    "Checking aligned event baselines at " +
    "$BaseUrl"
)

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=60&recent_limit=5&compare_previous=true" +
    "&comparison_offset_minutes=1440" +
    "&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectPrevious = Assert-AlignedBaseline `
    -Payload $Direct `
    -Source "Direct API"

$InvalidStatus = Get-ExpectedHttpStatus `
    -Path (
        "/api/v1/events/summary/recent?" +
        "minutes=60&compare_previous=true" +
        "&comparison_offset_minutes=59"
    ) `
    -ExpectedStatus 422

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
    $SummaryTool[0].annotations.requiresConfirmation -ne $false
) {
    throw "Aligned baseline tool policy is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.summarize/invoke" `
    -Payload @{
        minutes = 60
        recent_limit = 5
        compare_previous = $true
        comparison_offset_minutes = 1440
        status = "OPEN"
        severity = "INFO"
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "event.summarize"
) {
    throw "Harness aligned baseline failed"
}
$HarnessPrevious = Assert-AlignedBaseline `
    -Payload $Harness.result `
    -Source "Harness"

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Compare open INFO events from the last 60 minutes " +
            "with the same time yesterday"
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
    $WriteCalls.Count -ne 0
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent aligned baseline failed"
}
$AgentPrevious = Assert-AlignedBaseline `
    -Payload $Results[0].result `
    -Source "Agent"

foreach ($Candidate in @(
    $Harness.result,
    $Results[0].result
)) {
    if (
        [int]$Candidate.total_events -ne
            [int]$Direct.total_events -or
        [int]$Candidate.comparison.previous_total -ne
            [int]$Direct.comparison.previous_total -or
        [int]$Candidate.comparison.previous_window.
            offset_minutes -ne
            [int]$DirectPrevious.offset_minutes -or
        [string]$Candidate.comparison.previous_window.
            alignment -ne
            [string]$DirectPrevious.alignment
    ) {
        throw "Direct, Harness, and Agent baselines differ"
    }
}
if (
    [string]$Task.answer -notmatch "1440" -or
    [string]$Task.answer -notmatch "OFFSET"
) {
    throw "Agent answer omits aligned baseline metadata"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
$CheckpointPrevious = Assert-AlignedBaseline `
    -Payload $Checkpoint.tool_results[0].result `
    -Source "Checkpoint"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [string]$CheckpointPrevious.since_timestamp -ne
        [string]$AgentPrevious.since_timestamp -or
    [string]$CheckpointPrevious.until_timestamp -ne
        [string]$AgentPrevious.until_timestamp
) {
    throw "Aligned baseline checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-summary"' -or
    $Javascript -notmatch
        'comparison\?\.previous_window\?\.offset_minutes' -or
    $Javascript -notmatch 'comparisonAlignmentText'
) {
    throw "Dashboard aligned baseline assets are incomplete"
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
Write-Host "Event Aligned Baseline acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host "Current window minutes: $($Direct.window.minutes)"
Write-Host (
    "Comparison offset minutes: " +
    $DirectPrevious.offset_minutes
)
Write-Host "Alignment: $($DirectPrevious.alignment)"
Write-Host (
    "Previous window minutes: " +
    $DirectPrevious.minutes
)
Write-Host "Current events: $($Direct.total_events)"
Write-Host (
    "Previous events: " +
    $Direct.comparison.previous_total
)
Write-Host "Non-overlapping windows: True"
Write-Host (
    "Invalid short offset rejected: HTTP " +
    $InvalidStatus
)
Write-Host (
    "Direct/Harness/Agent aligned baselines match: True"
)
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard aligned baseline assets: ready"
Write-Host "Event Aligned Baseline smoke test passed."
