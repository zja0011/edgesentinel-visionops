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

function Assert-ReferenceConsistency {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Profile = $Payload.reference_baselines
    $Rows = @($Profile.baselines)
    $Consistency = $Profile.consistency
    if (
        $null -eq $Consistency -or
        $Rows.Count -ne 2 -or
        [int]$Profile.baseline_count -ne 2
    ) {
        throw "$Source reference consistency is missing"
    }

    $First = [int]$Rows[0].total_events
    $Second = [int]$Rows[1].total_events
    $Minimum = [Math]::Min($First, $Second)
    $Maximum = [Math]::Max($First, $Second)
    $Spread = $Maximum - $Minimum
    $Average = [double]$Profile.baseline_average_total
    $Threshold = 50
    if ($Average -eq 0) {
        $ExpectedPercent = $null
        $ExpectedStatus = "NO_HISTORICAL_ACTIVITY"
        $ExpectedReason = "BOTH_REFERENCE_TOTALS_ARE_ZERO"
    }
    else {
        $ExpectedPercent = [Math]::Round(
            ($Spread / $Average) * 100.0,
            2
        )
        if ($Spread -eq 0) {
            $ExpectedStatus = "STABLE"
            $ExpectedReason = "REFERENCE_TOTALS_MATCH"
        }
        elseif ($ExpectedPercent -le $Threshold) {
            $ExpectedStatus = "STABLE"
            $ExpectedReason = "SPREAD_WITHIN_THRESHOLD"
        }
        else {
            $ExpectedStatus = "VARIABLE"
            $ExpectedReason = "SPREAD_EXCEEDS_THRESHOLD"
        }
    }
    $ExpectedReliable = $ExpectedStatus -eq "STABLE"

    if (
        [int]$Consistency.minimum_total -ne $Minimum -or
        [int]$Consistency.maximum_total -ne $Maximum -or
        [int]$Consistency.spread -ne $Spread -or
        [int]$Consistency.maximum_stable_spread_percent -ne
            $Threshold -or
        [string]$Consistency.status -ne $ExpectedStatus -or
        [string]$Consistency.reason -ne $ExpectedReason -or
        $Consistency.reliable_for_average -ne
            $ExpectedReliable
    ) {
        throw "$Source reference consistency is invalid"
    }
    if ($null -eq $ExpectedPercent) {
        if ($null -ne $Consistency.spread_percent) {
            throw "$Source zero average spread must be null"
        }
    }
    elseif (
        [Math]::Abs(
            [double]$Consistency.spread_percent -
            $ExpectedPercent
        ) -gt 0.01
    ) {
        throw "$Source relative spread is invalid"
    }
    return $Consistency
}

Write-Host (
    "Checking dual-baseline consistency at " +
    "$BaseUrl"
)

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=60&recent_limit=5" +
    "&include_reference_baselines=true" +
    "&object_class=bottle&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectConsistency = Assert-ReferenceConsistency `
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
    $SummaryTool[0].annotations.requiresConfirmation -ne $false
) {
    throw "Reference consistency tool policy is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.summarize/invoke" `
    -Payload @{
        minutes = 60
        recent_limit = 5
        include_reference_baselines = $true
        object_class = "bottle"
        status = "OPEN"
        severity = "INFO"
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "event.summarize"
) {
    throw "Harness reference consistency failed"
}
$HarnessConsistency = Assert-ReferenceConsistency `
    -Payload $Harness.result `
    -Source "Harness"

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Compare open INFO bottle events from the last 60 " +
            "minutes with the same time yesterday and the same " +
            "time last week"
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
    throw "Agent reference consistency failed"
}
$AgentConsistency = Assert-ReferenceConsistency `
    -Payload $Results[0].result `
    -Source "Agent"

foreach ($Candidate in @(
    $HarnessConsistency,
    $AgentConsistency
)) {
    if (
        [string]$Candidate.status -ne
            [string]$DirectConsistency.status -or
        [string]$Candidate.reason -ne
            [string]$DirectConsistency.reason -or
        [int]$Candidate.spread -ne
            [int]$DirectConsistency.spread
    ) {
        throw "Direct, Harness, and Agent consistency differ"
    }
}
if (
    [string]$Task.answer -notmatch
        [Regex]::Escape([string]$AgentConsistency.status)
) {
    throw "Agent answer omits reference consistency"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
$CheckpointConsistency = Assert-ReferenceConsistency `
    -Payload $Checkpoint.tool_results[0].result `
    -Source "Checkpoint"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [string]$CheckpointConsistency.status -ne
        [string]$AgentConsistency.status -or
    [string]$CheckpointConsistency.reason -ne
        [string]$AgentConsistency.reason
) {
    throw "Reference consistency checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-summary"' -or
    $Javascript -notmatch
        'referenceBaselines\.consistency\?\.status' -or
    $Javascript -notmatch 'referenceBaselineText'
) {
    throw "Dashboard reference consistency assets are incomplete"
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
Write-Host "Event Reference Consistency acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host (
    "Yesterday events: " +
    $Direct.reference_baselines.baselines[0].total_events
)
Write-Host (
    "Last-week events: " +
    $Direct.reference_baselines.baselines[1].total_events
)
Write-Host "Minimum: $($DirectConsistency.minimum_total)"
Write-Host "Maximum: $($DirectConsistency.maximum_total)"
Write-Host "Spread: $($DirectConsistency.spread)"
Write-Host (
    "Spread percent: " +
    $DirectConsistency.spread_percent
)
Write-Host (
    "Maximum stable spread percent: " +
    $DirectConsistency.maximum_stable_spread_percent
)
Write-Host "Consistency status: $($DirectConsistency.status)"
Write-Host "Consistency reason: $($DirectConsistency.reason)"
Write-Host (
    "Reliable for average: " +
    $DirectConsistency.reliable_for_average
)
Write-Host "Bounded baseline count: 2"
Write-Host (
    "Direct/Harness/Agent consistency match: True"
)
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard reference consistency assets: ready"
Write-Host "Event Reference Consistency smoke test passed."
