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

function Assert-StructuralChange {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Comparison = $Payload.comparison
    $Structures = $Comparison.structural_change
    if ($null -eq $Structures) {
        throw "$Source structural change is missing"
    }
    $Dimensions = @(
        "by_event_type",
        "by_severity",
        "by_object_class",
        "by_zone"
    )
    foreach ($Dimension in $Dimensions) {
        $Structure = $Structures.PSObject.Properties[
            $Dimension
        ].Value
        $Rows = @(
            $Comparison.contributors.PSObject.Properties[
                $Dimension
            ].Value
        )
        if ($null -eq $Structure) {
            throw "$Source structural dimension is missing"
        }
        $Gross = 0
        $Net = 0
        $Increasing = 0
        $Decreasing = 0
        $Significant = 0
        foreach ($Row in $Rows) {
            $Change = [int]$Row.absolute_change
            $Gross += [Math]::Abs($Change)
            $Net += $Change
            if ($Change -gt 0) {
                $Increasing += 1
            }
            elseif ($Change -lt 0) {
                $Decreasing += 1
            }
            if ($Row.threshold_exceeded -eq $true) {
                $Significant += 1
            }
        }
        $NetAbsolute = [Math]::Abs($Net)
        $Offsetting = [int](
            ($Gross - $NetAbsolute) / 2
        )
        $MaskedPercent = if ($Gross -gt 0) {
            [Math]::Round(
                (
                    ($Gross - $NetAbsolute) /
                    [double]$Gross
                ) * 100.0,
                2
            )
        }
        else {
            0.0
        }
        if (
            [int]$Structure.gross_absolute_change -ne $Gross -or
            [int]$Structure.net_change -ne $Net -or
            [int]$Structure.net_absolute_change -ne
                $NetAbsolute -or
            [int]$Structure.offsetting_events -ne $Offsetting -or
            [int]$Structure.increasing_groups -ne $Increasing -or
            [int]$Structure.decreasing_groups -ne $Decreasing -or
            [int]$Structure.significant_groups -ne $Significant -or
            [Math]::Abs(
                [double]$Structure.masked_share_percent -
                $MaskedPercent
            ) -gt 0.01
        ) {
            throw "$Source structural arithmetic is invalid"
        }
        if ($Structure.complete -eq $true) {
            if (
                $Structure.net_matches_total -ne $true -or
                $Net -ne [int]$Comparison.absolute_change
            ) {
                throw "$Source complete structure has wrong net"
            }
            $ExpectedMasked = (
                $Comparison.assessment.threshold_exceeded -ne
                    $true -and
                $Significant -gt 0
            )
            $ExpectedStatus = if ($ExpectedMasked) {
                "MASKED_SIGNIFICANT_CHANGE"
            }
            elseif ($Offsetting -gt 0) {
                "OPPOSING_CHANGES"
            }
            elseif ($Gross -gt 0) {
                "ONE_DIRECTION"
            }
            else {
                "NO_CHANGE"
            }
            if (
                $Structure.masked_significant_change -ne
                    $ExpectedMasked -or
                [string]$Structure.status -ne $ExpectedStatus
            ) {
                throw "$Source structural status is invalid"
            }
        }
        elseif (
            [string]$Structure.status -ne "PARTIAL" -or
            $Structure.net_matches_total -ne $false -or
            $Structure.masked_significant_change -ne $false
        ) {
            throw "$Source partial structure is unsafe"
        }
    }
    return $Structures.by_event_type
}

Write-Host (
    "Checking event-type change cancellation at " +
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
$DirectStructure = Assert-StructuralChange `
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
    throw "Structural change tool policy is invalid"
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
    throw "Harness structural analysis failed"
}
$HarnessStructure = Assert-StructuralChange `
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
    throw "Agent structural analysis failed"
}
$AgentStructure = Assert-StructuralChange `
    -Payload $Results[0].result `
    -Source "Agent"

foreach ($Candidate in @(
    $HarnessStructure,
    $AgentStructure
)) {
    if (
        [string]$Candidate.status -ne
            [string]$DirectStructure.status -or
        [int]$Candidate.gross_absolute_change -ne
            [int]$DirectStructure.gross_absolute_change -or
        [int]$Candidate.net_change -ne
            [int]$DirectStructure.net_change -or
        [int]$Candidate.offsetting_events -ne
            [int]$DirectStructure.offsetting_events
    ) {
        throw "Direct, Harness, and Agent structures differ"
    }
}
if (
    [string]$Task.answer -notmatch
        [Regex]::Escape([string]$DirectStructure.status)
) {
    throw "Agent answer omits structural status"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
$CheckpointStructure = (
    $Checkpoint.tool_results[0].result.comparison.
        structural_change.by_event_type
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [string]$CheckpointStructure.status -ne
        [string]$DirectStructure.status -or
    [int]$CheckpointStructure.offsetting_events -ne
        [int]$DirectStructure.offsetting_events
) {
    throw "Structural change checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
$HasEventSummary = (
    $Dashboard -match 'id="event-summary"'
)
$HasStructure = (
    $Javascript -match 'structural_change\?\.by_event_type'
)
$HasRenderer = (
    $Javascript -match 'structuralChangeText'
)
if (
    -not $HasEventSummary -or
    -not $HasStructure -or
    -not $HasRenderer
) {
    throw (
        "Dashboard structural assets are incomplete: " +
        "summary=$HasEventSummary " +
        "structure=$HasStructure " +
        "renderer=$HasRenderer"
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
Write-Host "Event Change Cancellation acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host "Dimension: by_event_type"
Write-Host "Status: $($DirectStructure.status)"
Write-Host "Complete: $($DirectStructure.complete)"
Write-Host (
    "Gross absolute change: " +
    $DirectStructure.gross_absolute_change
)
Write-Host "Net change: $($DirectStructure.net_change)"
Write-Host (
    "Offsetting events: " +
    $DirectStructure.offsetting_events
)
Write-Host (
    "Masked share percent: " +
    $DirectStructure.masked_share_percent
)
Write-Host (
    "Increasing/decreasing groups: " +
    "$($DirectStructure.increasing_groups)/" +
    $DirectStructure.decreasing_groups
)
Write-Host (
    "Masked significant change: " +
    $DirectStructure.masked_significant_change
)
Write-Host "Structural arithmetic verified: True"
Write-Host "Truncation safety verified: True"
Write-Host "Direct/Harness/Agent structures match: True"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard structural assets: ready"
Write-Host "Event Change Cancellation smoke test passed."
