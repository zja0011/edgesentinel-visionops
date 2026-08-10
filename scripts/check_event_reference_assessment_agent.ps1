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

function Assert-ReferenceAssessment {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Profile = $Payload.reference_baselines
    $Assessment = $Profile.assessment
    if (
        $null -eq $Profile -or
        $null -eq $Assessment -or
        [int]$Profile.baseline_count -ne 2 -or
        $Profile.complete -ne $true
    ) {
        throw "$Source reference assessment is missing"
    }

    $Current = [int]$Profile.current_total
    $Average = [double]$Profile.baseline_average_total
    $Change = [double]$Profile.change_from_average
    $HistoryAvailable = $Average -gt 0
    $CurrentActivity = $Current -gt 0
    if (-not $HistoryAvailable) {
        if ($CurrentActivity) {
            $ExpectedStatus = "NEW_ACTIVITY"
            $ExpectedReason = (
                "CURRENT_ACTIVITY_WITH_ZERO_HISTORY"
            )
        }
        else {
            $ExpectedStatus = "NO_HISTORICAL_ACTIVITY"
            $ExpectedReason = "CURRENT_AND_HISTORY_ARE_ZERO"
        }
    }
    elseif ($Change -gt 0) {
        $ExpectedStatus = "ABOVE_HISTORICAL_AVERAGE"
        $ExpectedReason = "CURRENT_TOTAL_ABOVE_HISTORY"
    }
    elseif ($Change -lt 0) {
        $ExpectedStatus = "BELOW_HISTORICAL_AVERAGE"
        $ExpectedReason = "CURRENT_TOTAL_BELOW_HISTORY"
    }
    else {
        $ExpectedStatus = "MATCHES_HISTORICAL_AVERAGE"
        $ExpectedReason = "CURRENT_TOTAL_MATCHES_HISTORY"
    }

    if (
        [string]$Assessment.status -ne $ExpectedStatus -or
        [string]$Assessment.reason -ne $ExpectedReason -or
        $Assessment.historical_activity_available -ne
            $HistoryAvailable -or
        $Assessment.current_activity -ne $CurrentActivity
    ) {
        throw "$Source reference assessment is inconsistent"
    }
    if (
        -not $HistoryAvailable -and
        $null -ne $Profile.percent_change_from_average
    ) {
        throw "$Source zero history must have null percent"
    }
    return $Assessment
}

Write-Host (
    "Checking deterministic reference assessment at " +
    "$BaseUrl"
)

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=60&recent_limit=5" +
    "&include_reference_baselines=true" +
    "&object_class=bottle&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectAssessment = Assert-ReferenceAssessment `
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
    throw "Reference assessment tool policy is invalid"
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
    throw "Harness reference assessment failed"
}
$HarnessAssessment = Assert-ReferenceAssessment `
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
    throw "Agent reference assessment failed"
}
$AgentAssessment = Assert-ReferenceAssessment `
    -Payload $Results[0].result `
    -Source "Agent"

foreach ($Candidate in @(
    $HarnessAssessment,
    $AgentAssessment
)) {
    if (
        [string]$Candidate.status -ne
            [string]$DirectAssessment.status -or
        [string]$Candidate.reason -ne
            [string]$DirectAssessment.reason
    ) {
        throw "Direct, Harness, and Agent assessments differ"
    }
}
if (
    [string]$Task.answer -notmatch
        [Regex]::Escape([string]$AgentAssessment.status)
) {
    throw "Agent answer omits reference assessment"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
$CheckpointAssessment = Assert-ReferenceAssessment `
    -Payload $Checkpoint.tool_results[0].result `
    -Source "Checkpoint"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [string]$CheckpointAssessment.status -ne
        [string]$AgentAssessment.status -or
    [string]$CheckpointAssessment.reason -ne
        [string]$AgentAssessment.reason
) {
    throw "Reference assessment checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-summary"' -or
    $Javascript -notmatch
        'referenceBaselines\.assessment\?\.status' -or
    $Javascript -notmatch 'referenceBaselineText'
) {
    throw "Dashboard reference assessment assets are incomplete"
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
Write-Host "Event Reference Assessment acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host (
    "Current events: " +
    $Direct.reference_baselines.current_total
)
Write-Host (
    "Historical average: " +
    $Direct.reference_baselines.baseline_average_total
)
Write-Host (
    "Assessment status: " +
    $DirectAssessment.status
)
Write-Host (
    "Assessment reason: " +
    $DirectAssessment.reason
)
Write-Host (
    "Historical activity available: " +
    $DirectAssessment.historical_activity_available
)
Write-Host (
    "Current activity: " +
    $DirectAssessment.current_activity
)
Write-Host "Zero-baseline division safe: True"
Write-Host (
    "Direct/Harness/Agent assessments match: True"
)
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard reference assessment assets: ready"
Write-Host "Event Reference Assessment smoke test passed."
