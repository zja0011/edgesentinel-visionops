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

function Assert-Assessment {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Comparison = $Payload.comparison
    $Assessment = $Comparison.assessment
    if ($null -eq $Assessment) {
        throw "$Source change assessment is missing"
    }
    $Current = [int]$Comparison.current_total
    $Previous = [int]$Comparison.previous_total
    $Change = [int]$Comparison.absolute_change
    $MinimumEvents = [int]$Assessment.minimum_absolute_change
    $MinimumPercent = [double]$Assessment.minimum_percent_change
    if (
        $Change -ne ($Current - $Previous) -or
        $MinimumEvents -ne 10 -or
        $MinimumPercent -ne 25.0 -or
        [int]$Assessment.observed_absolute_change -ne $Change
    ) {
        throw "$Source change assessment values are invalid"
    }

    if ($Previous -eq 0) {
        $ExpectedExceeded = $Current -ge $MinimumEvents
        $ExpectedStatus = if ($ExpectedExceeded) {
            "NEW_ACTIVITY"
        }
        else {
            "INSUFFICIENT_BASELINE"
        }
        $ExpectedReason = if ($ExpectedExceeded) {
            "NEW_ACTIVITY_ABOVE_MINIMUM"
        }
        else {
            "BASELINE_ZERO_AND_ACTIVITY_BELOW_MINIMUM"
        }
        if ($null -ne $Assessment.observed_percent_change) {
            throw "$Source zero baseline percent must be null"
        }
    }
    else {
        $ObservedPercent = [double]$Comparison.percent_change
        $ExpectedExceeded = (
            [Math]::Abs($Change) -ge $MinimumEvents -and
            [Math]::Abs($ObservedPercent) -ge $MinimumPercent
        )
        $ExpectedStatus = if ($ExpectedExceeded) {
            "SIGNIFICANT_CHANGE"
        }
        else {
            "WITHIN_THRESHOLD"
        }
        $ExpectedReason = if ($ExpectedExceeded) {
            "ABSOLUTE_AND_PERCENT_THRESHOLDS_EXCEEDED"
        }
        elseif ([Math]::Abs($Change) -lt $MinimumEvents) {
            "ABSOLUTE_CHANGE_BELOW_MINIMUM"
        }
        else {
            "PERCENT_CHANGE_BELOW_MINIMUM"
        }
        if (
            [Math]::Abs(
                [double]$Assessment.observed_percent_change -
                $ObservedPercent
            ) -gt 0.01
        ) {
            throw "$Source observed percent is inconsistent"
        }
    }

    if (
        [bool]$Assessment.threshold_exceeded -ne
            [bool]$ExpectedExceeded -or
        [string]$Assessment.status -ne $ExpectedStatus -or
        [string]$Assessment.reason -ne $ExpectedReason
    ) {
        throw "$Source change assessment decision is invalid"
    }
    return $Assessment
}

Write-Host (
    "Checking deterministic event change assessment at " +
    "$BaseUrl"
)

Assert-HttpStatus `
    -Path (
        "/api/v1/events/summary/recent?" +
        "minutes=1440&compare_previous=true" +
        "&change_threshold_percent=0"
    ) `
    -ExpectedStatus 422

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=1440&recent_limit=5&compare_previous=true" +
    "&change_threshold_percent=25" +
    "&change_threshold_events=10" +
    "&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectAssessment = Assert-Assessment `
    -Payload $Direct `
    -Source "Direct API"

$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$SummaryTool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "event.summarize"
    }
)
$Schema = $SummaryTool[0].inputSchema.properties
if (
    $SummaryTool.Count -ne 1 -or
    $SummaryTool[0].annotations.riskLevel -ne "L0" -or
    $SummaryTool[0].annotations.readOnlyHint -ne $true -or
    $SummaryTool[0].annotations.requiresConfirmation -ne $false -or
    [int]$Schema.change_threshold_percent.default -ne 25 -or
    [int]$Schema.change_threshold_events.default -ne 10
) {
    throw "Change assessment schema or policy is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.summarize/invoke" `
    -Payload @{
        minutes = 1440
        recent_limit = 5
        compare_previous = $true
        change_threshold_percent = 25
        change_threshold_events = 10
        status = "OPEN"
        severity = "INFO"
    }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "event.summarize"
) {
    throw "Harness change assessment failed"
}
$HarnessAssessment = Assert-Assessment `
    -Payload $Harness.result `
    -Source "Harness"

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Event change assessment for open INFO events " +
            "in the last 1440 minutes"
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
    throw "Agent change assessment failed"
}
$AgentAssessment = Assert-Assessment `
    -Payload $Results[0].result `
    -Source "Agent"

foreach ($Candidate in @(
    $HarnessAssessment,
    $AgentAssessment
)) {
    if (
        [string]$Candidate.status -ne
            [string]$DirectAssessment.status -or
        [bool]$Candidate.threshold_exceeded -ne
            [bool]$DirectAssessment.threshold_exceeded -or
        [string]$Candidate.reason -ne
            [string]$DirectAssessment.reason
    ) {
        throw "Direct, Harness, and Agent assessments differ"
    }
}
if (
    [string]$Task.answer -notmatch
        [Regex]::Escape([string]$DirectAssessment.status)
) {
    throw "Agent answer does not explain assessment status"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
$CheckpointAssessment = (
    $Checkpoint.tool_results[0].result.comparison.assessment
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [string]$CheckpointAssessment.status -ne
        [string]$DirectAssessment.status -or
    [bool]$CheckpointAssessment.threshold_exceeded -ne
        [bool]$DirectAssessment.threshold_exceeded
) {
    throw "Change assessment checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
$HasEventSummary = (
    $Dashboard -match 'id="event-summary"'
)
$HasAssessment = (
    $Javascript -match 'comparison\?\.assessment'
)
$HasThresholdRenderer = (
    $Javascript -match 'changeAssessment\.threshold_exceeded'
)
if (
    -not $HasEventSummary -or
    -not $HasAssessment -or
    -not $HasThresholdRenderer
) {
    throw (
        "Dashboard assessment assets are incomplete: " +
        "summary=$HasEventSummary " +
        "assessment=$HasAssessment " +
        "renderer=$HasThresholdRenderer"
    )
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
Write-Host "Event Change Assessment acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host "Current events: $($Direct.comparison.current_total)"
Write-Host "Previous events: $($Direct.comparison.previous_total)"
Write-Host "Absolute change: $($Direct.comparison.absolute_change)"
Write-Host "Percent change: $($Direct.comparison.percent_change)"
Write-Host "Minimum absolute change: 10"
Write-Host "Minimum percent change: 25"
Write-Host "Assessment status: $($DirectAssessment.status)"
Write-Host (
    "Threshold exceeded: " +
    $DirectAssessment.threshold_exceeded
)
Write-Host "Reason: $($DirectAssessment.reason)"
Write-Host "Invalid threshold rejected: HTTP 422"
Write-Host "Direct/Harness/Agent assessments match: True"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard assessment assets: ready"
Write-Host "Event Change Assessment smoke test passed."
