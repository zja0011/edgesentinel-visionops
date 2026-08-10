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

function Assert-ReferenceBaselines {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Profile = $Payload.reference_baselines
    $Baselines = @($Profile.baselines)
    if (
        $null -eq $Profile -or
        [string]$Profile.status -ne "AVAILABLE" -or
        [int]$Profile.window_minutes -ne 60 -or
        [string]$Profile.timezone -ne "Asia/Shanghai" -or
        [int]$Profile.current_total -ne
            [int]$Payload.total_events -or
        [int]$Profile.baseline_count -ne 2 -or
        $Baselines.Count -ne 2 -or
        $Profile.complete -ne $true
    ) {
        throw "$Source reference profile metadata is invalid"
    }

    $ExpectedLabels = @(
        "SAME_TIME_YESTERDAY",
        "SAME_TIME_LAST_WEEK"
    )
    $ExpectedOffsets = @(1440, 10080)
    $CurrentSince = [DateTimeOffset]::Parse(
        [string]$Payload.window.since_timestamp
    )
    for ($Index = 0; $Index -lt 2; $Index += 1) {
        $Baseline = $Baselines[$Index]
        if (
            [string]$Baseline.label -ne
                $ExpectedLabels[$Index] -or
            [int]$Baseline.minutes -ne 60 -or
            [int]$Baseline.offset_minutes -ne
                $ExpectedOffsets[$Index] -or
            [string]$Baseline.timezone -ne "Asia/Shanghai"
        ) {
            throw "$Source reference baseline identity is invalid"
        }
        $Since = [DateTimeOffset]::Parse(
            [string]$Baseline.since_timestamp
        )
        $Until = [DateTimeOffset]::Parse(
            [string]$Baseline.until_timestamp
        )
        if (
            [Math]::Abs(
                ($Until - $Since).TotalMinutes - 60.0
            ) -gt 0.01 -or
            [Math]::Abs(
                ($CurrentSince - $Since).TotalMinutes -
                [double]$ExpectedOffsets[$Index]
            ) -gt 0.01 -or
            $Until -gt $CurrentSince
        ) {
            throw "$Source reference baseline boundary is invalid"
        }
    }

    $ExpectedAverage = [Math]::Round(
        (
            [int]$Baselines[0].total_events +
            [int]$Baselines[1].total_events
        ) / 2.0,
        2
    )
    $ExpectedChange = [Math]::Round(
        [int]$Payload.total_events - $ExpectedAverage,
        2
    )
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
        [Math]::Abs(
            [double]$Profile.baseline_average_total -
            $ExpectedAverage
        ) -gt 0.01 -or
        [Math]::Abs(
            [double]$Profile.change_from_average -
            $ExpectedChange
        ) -gt 0.01 -or
        [string]$Profile.direction -ne $ExpectedDirection
    ) {
        throw "$Source reference profile arithmetic is invalid"
    }
    if ($ExpectedAverage -gt 0) {
        $ExpectedPercent = [Math]::Round(
            ($ExpectedChange / $ExpectedAverage) * 100.0,
            2
        )
        if (
            [Math]::Abs(
                [double]$Profile.percent_change_from_average -
                $ExpectedPercent
            ) -gt 0.01
        ) {
            throw "$Source reference percent is invalid"
        }
    }
    elseif (
        $null -ne $Profile.percent_change_from_average
    ) {
        throw "$Source zero reference average must have null percent"
    }
    return $Profile
}

Write-Host (
    "Checking yesterday and last-week event baselines at " +
    "$BaseUrl"
)

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=60&recent_limit=5" +
    "&include_reference_baselines=true" +
    "&object_class=bottle&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectProfile = Assert-ReferenceBaselines `
    -Payload $Direct `
    -Source "Direct API"

$InvalidStatus = Get-ExpectedHttpStatus `
    -Path (
        "/api/v1/events/summary/recent?" +
        "minutes=60&include_reference_baselines=maybe"
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
    throw "Reference baseline tool policy is invalid"
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
    throw "Harness reference baseline failed"
}
$HarnessProfile = Assert-ReferenceBaselines `
    -Payload $Harness.result `
    -Source "Harness"

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Compare open INFO bottle events from the last 60 " +
            "minutes " +
            "with the same time yesterday and the same time " +
            "last week"
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
    throw "Agent reference baseline failed"
}
$AgentProfile = Assert-ReferenceBaselines `
    -Payload $Results[0].result `
    -Source "Agent"

foreach ($Candidate in @(
    $HarnessProfile,
    $AgentProfile
)) {
    if (
        [int]$Candidate.current_total -ne
            [int]$DirectProfile.current_total -or
        [double]$Candidate.baseline_average_total -ne
            [double]$DirectProfile.baseline_average_total -or
        [int]$Candidate.baselines[0].total_events -ne
            [int]$DirectProfile.baselines[0].total_events -or
        [int]$Candidate.baselines[1].total_events -ne
            [int]$DirectProfile.baselines[1].total_events
    ) {
        throw "Direct, Harness, and Agent profiles differ"
    }
}
if (
    [string]$Task.answer -notmatch
        [Regex]::Escape([string]$AgentProfile.direction)
) {
    throw "Agent answer omits reference profile direction"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
$CheckpointProfile = Assert-ReferenceBaselines `
    -Payload $Checkpoint.tool_results[0].result `
    -Source "Checkpoint"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [string]$CheckpointProfile.baselines[0].
        since_timestamp -ne
        [string]$AgentProfile.baselines[0].
            since_timestamp -or
    [string]$CheckpointProfile.baselines[1].
        since_timestamp -ne
        [string]$AgentProfile.baselines[1].
            since_timestamp
) {
    throw "Reference baseline checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-summary"' -or
    $Javascript -notmatch 'payload\.reference_baselines' -or
    $Javascript -notmatch 'referenceBaselineText'
) {
    throw "Dashboard reference baseline assets are incomplete"
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
Write-Host "Event Reference Baselines acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host "Window minutes: $($DirectProfile.window_minutes)"
Write-Host (
    "Yesterday events: " +
    $DirectProfile.baselines[0].total_events
)
Write-Host (
    "Last-week events: " +
    $DirectProfile.baselines[1].total_events
)
Write-Host (
    "Baseline average: " +
    $DirectProfile.baseline_average_total
)
Write-Host "Current events: $($DirectProfile.current_total)"
Write-Host (
    "Change from average: " +
    $DirectProfile.change_from_average
)
Write-Host "Direction: $($DirectProfile.direction)"
Write-Host "Equal non-overlapping windows: True"
Write-Host "Bounded baseline count: $($DirectProfile.baseline_count)"
Write-Host (
    "Invalid boolean rejected: HTTP " +
    $InvalidStatus
)
Write-Host (
    "Direct/Harness/Agent reference profiles match: True"
)
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard reference baseline assets: ready"
Write-Host "Event Reference Baselines smoke test passed."
