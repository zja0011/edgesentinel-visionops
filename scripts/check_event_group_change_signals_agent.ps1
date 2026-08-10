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

function Assert-GroupSignals {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Comparison = $Payload.comparison
    $Contributors = $Comparison.contributors
    $Signals = $Comparison.significant_contributors
    if ($null -eq $Contributors -or $null -eq $Signals) {
        throw "$Source group signal collections are missing"
    }
    $Dimensions = @(
        "by_event_type",
        "by_severity",
        "by_object_class",
        "by_zone"
    )
    foreach ($Dimension in $Dimensions) {
        $AllRows = @(
            $Contributors.PSObject.Properties[
                $Dimension
            ].Value
        )
        $SignalRows = @(
            $Signals.PSObject.Properties[
                $Dimension
            ].Value
        )
        if ($AllRows.Count -gt 20 -or $SignalRows.Count -gt 20) {
            throw "$Source group signals are not bounded"
        }
        foreach ($Signal in $SignalRows) {
            $Current = [int]$Signal.current_count
            $Previous = [int]$Signal.previous_count
            $Change = [int]$Signal.absolute_change
            if (
                $Signal.threshold_exceeded -ne $true -or
                $Change -ne ($Current - $Previous) -or
                [Math]::Abs($Change) -lt 10 -or
                [string]$Signal.status -notin @(
                    "SIGNIFICANT_CHANGE",
                    "NEW_ACTIVITY"
                )
            ) {
                throw "$Source significant row is invalid"
            }
            if ($Previous -eq 0) {
                if (
                    $Current -lt 10 -or
                    $null -ne $Signal.percent_change
                ) {
                    throw "$Source new-activity row is invalid"
                }
            }
            elseif (
                [Math]::Abs(
                    [double]$Signal.percent_change
                ) -lt 25.0
            ) {
                throw "$Source percent signal is below threshold"
            }
            $Match = @(
                $AllRows | Where-Object {
                    [string]$_.name -eq [string]$Signal.name
                }
            )
            if (
                $Match.Count -ne 1 -or
                [int]$Match[0].absolute_change -ne $Change -or
                $Match[0].threshold_exceeded -ne $true
            ) {
                throw "$Source signal is absent from contributors"
            }
        }
    }

    $EventSignals = @($Signals.by_event_type)
    if (
        [int]$Comparison.significant_event_type_count -ne
            $EventSignals.Count
    ) {
        throw "$Source event-type signal count is invalid"
    }
    $Largest = (
        $Comparison.largest_significant_event_type_change
    )
    if ($EventSignals.Count -eq 0) {
        if ($null -ne $Largest) {
            throw "$Source largest significant change must be null"
        }
    }
    elseif (
        $null -eq $Largest -or
        [string]$Largest.name -ne
            [string]$EventSignals[0].name -or
        [int]$Largest.absolute_change -ne
            [int]$EventSignals[0].absolute_change
    ) {
        throw "$Source largest significant change is invalid"
    }
    return @{
        EventTypeCount = $EventSignals.Count
        Largest = $Largest
    }
}

Write-Host (
    "Checking per-group event change signals at " +
    "$BaseUrl"
)

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=1440&recent_limit=5&compare_previous=true" +
    "&change_threshold_percent=25" +
    "&change_threshold_events=10" +
    "&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectSignals = Assert-GroupSignals `
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
    throw "Group signal tool policy is invalid"
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
    throw "Harness group signal analysis failed"
}
$HarnessSignals = Assert-GroupSignals `
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
    $WriteCalls.Count -ne 0 -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent group signal analysis failed"
}
$AgentSignals = Assert-GroupSignals `
    -Payload $Results[0].result `
    -Source "Agent"

foreach ($Candidate in @(
    $HarnessSignals,
    $AgentSignals
)) {
    if (
        [int]$Candidate.EventTypeCount -ne
            [int]$DirectSignals.EventTypeCount
    ) {
        throw "Direct, Harness, and Agent signal counts differ"
    }
    if (
        $null -ne $DirectSignals.Largest -and
        [string]$Candidate.Largest.name -ne
            [string]$DirectSignals.Largest.name
    ) {
        throw "Direct, Harness, and Agent largest signals differ"
    }
}
if (
    $null -ne $DirectSignals.Largest -and
    [string]$Task.answer -notmatch [Regex]::Escape(
        [string]$DirectSignals.Largest.name
    )
) {
    throw "Agent answer omits largest group signal"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [int]$Checkpoint.tool_results[0].result.comparison.
        significant_event_type_count -ne
        [int]$DirectSignals.EventTypeCount
) {
    throw "Group signal checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
$HasEventSummary = (
    $Dashboard -match 'id="event-summary"'
)
$HasSignalCount = (
    $Javascript -match 'significant_event_type_count'
)
$HasSignalRenderer = (
    $Javascript -match 'significantContributorText'
)
if (
    -not $HasEventSummary -or
    -not $HasSignalCount -or
    -not $HasSignalRenderer
) {
    throw (
        "Dashboard group signal assets are incomplete: " +
        "summary=$HasEventSummary " +
        "count=$HasSignalCount " +
        "renderer=$HasSignalRenderer"
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

$LargestName = if ($null -ne $DirectSignals.Largest) {
    $DirectSignals.Largest.name
}
else {
    "none"
}
$LargestChange = if ($null -ne $DirectSignals.Largest) {
    $DirectSignals.Largest.absolute_change
}
else {
    0
}
Write-Host ""
Write-Host "Event Group Change Signals acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host "Minimum absolute change: 10"
Write-Host "Minimum percent change: 25"
Write-Host (
    "Significant event types: " +
    $DirectSignals.EventTypeCount
)
Write-Host "Largest significant type: $LargestName"
Write-Host "Largest significant change: $LargestChange"
Write-Host "All signals satisfy thresholds: True"
Write-Host "Signals retained in contributors: True"
Write-Host "Direct/Harness/Agent group signals match: True"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard group signal assets: ready"
Write-Host "Event Group Change Signals smoke test passed."
