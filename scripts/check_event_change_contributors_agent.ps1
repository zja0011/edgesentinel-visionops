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

function Assert-Contributors {
    param(
        [object]$Payload,
        [string]$Source
    )
    $Comparison = $Payload.comparison
    if ($null -eq $Comparison -or $null -eq $Comparison.contributors) {
        throw "$Source contributors are missing"
    }
    $Dimensions = @(
        "by_event_type",
        "by_severity",
        "by_object_class",
        "by_zone"
    )
    foreach ($Dimension in $Dimensions) {
        $Property = $Comparison.contributors.PSObject.Properties[
            $Dimension
        ]
        if ($null -eq $Property) {
            throw "$Source contributor dimension $Dimension is missing"
        }
        $Rows = @($Property.Value)
        if ($Rows.Count -gt 20) {
            throw "$Source contributor dimension is not bounded"
        }
        $PreviousMagnitude = [int]::MaxValue
        foreach ($Row in $Rows) {
            $Current = [int]$Row.current_count
            $Previous = [int]$Row.previous_count
            $Change = [int]$Row.absolute_change
            $Expected = $Current - $Previous
            $Direction = if ($Expected -gt 0) {
                "INCREASE"
            }
            elseif ($Expected -lt 0) {
                "DECREASE"
            }
            else {
                "UNCHANGED"
            }
            $Magnitude = [Math]::Abs($Change)
            if (
                [string]::IsNullOrWhiteSpace(
                    [string]$Row.name
                ) -or
                $Change -ne $Expected -or
                [string]$Row.direction -ne $Direction -or
                $Magnitude -gt $PreviousMagnitude
            ) {
                throw "$Source contributor row is invalid"
            }
            $PreviousMagnitude = $Magnitude
        }
    }
    $EventTypes = @(
        $Comparison.contributors.by_event_type
    )
    $Largest = $Comparison.largest_event_type_change
    if ($EventTypes.Count -eq 0) {
        if ($null -ne $Largest) {
            throw "$Source largest change must be null"
        }
        return $null
    }
    if (
        $null -eq $Largest -or
        [string]$Largest.name -ne [string]$EventTypes[0].name -or
        [int]$Largest.current_count -ne
            [int]$EventTypes[0].current_count -or
        [int]$Largest.previous_count -ne
            [int]$EventTypes[0].previous_count -or
        [int]$Largest.absolute_change -ne
            [int]$EventTypes[0].absolute_change -or
        [string]$Largest.direction -ne
            [string]$EventTypes[0].direction
    ) {
        throw "$Source largest event-type change is invalid"
    }
    $Serialized = $Comparison | ConvertTo-Json -Depth 10
    if (
        $Serialized -match "evidence_path" -or
        $Serialized -match "details" -or
        $Serialized -match "/workspace/"
    ) {
        throw "$Source contributors expose forbidden data"
    }
    return $Largest
}

Write-Host (
    "Checking bounded event change contributors at " +
    "$BaseUrl"
)

$SummaryPath = (
    "/api/v1/events/summary/recent?" +
    "minutes=1440&recent_limit=5&compare_previous=true" +
    "&status=OPEN&severity=INFO"
)
$Direct = Invoke-Utf8JsonGet -Path $SummaryPath
$DirectLargest = Assert-Contributors `
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
    throw "Contributor tool schema or policy is invalid"
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
    throw "Harness contributor analysis failed"
}
$HarnessLargest = Assert-Contributors `
    -Payload $Harness.result `
    -Source "Harness"

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
    $WriteCalls.Count -ne 0
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent contributor analysis failed"
}
$AgentLargest = Assert-Contributors `
    -Payload $Results[0].result `
    -Source "Agent"

foreach ($Candidate in @($HarnessLargest, $AgentLargest)) {
    if (
        [string]$Candidate.name -ne
            [string]$DirectLargest.name -or
        [int]$Candidate.current_count -ne
            [int]$DirectLargest.current_count -or
        [int]$Candidate.previous_count -ne
            [int]$DirectLargest.previous_count -or
        [int]$Candidate.absolute_change -ne
            [int]$DirectLargest.absolute_change
    ) {
        throw "Direct, Harness, and Agent contributors differ"
    }
}
if (
    [string]$Task.answer -notmatch
        [Regex]::Escape([string]$DirectLargest.name)
) {
    throw "Agent answer does not explain the largest change"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
$CheckpointLargest = (
    $Checkpoint.tool_results[0].result.comparison.
        largest_event_type_change
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [string]$CheckpointLargest.name -ne
        [string]$DirectLargest.name -or
    [int]$CheckpointLargest.absolute_change -ne
        [int]$DirectLargest.absolute_change
) {
    throw "Contributor checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
$HasEventSummary = (
    $Dashboard -match 'id="event-summary"'
)
$HasLargestChange = (
    $Javascript -match 'largest_event_type_change'
)
$HasContributorRenderer = (
    $Javascript -match 'const contributorText = largestChange'
)
if (
    -not $HasEventSummary -or
    -not $HasLargestChange -or
    -not $HasContributorRenderer
) {
    throw (
        "Dashboard contributor assets are incomplete: " +
        "summary=$HasEventSummary " +
        "largest=$HasLargestChange " +
        "renderer=$HasContributorRenderer"
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

$ContributorCounts = @(
    $Direct.comparison.contributors.by_event_type
).Count
Write-Host ""
Write-Host "Event Change Contributors acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($SummaryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $SummaryTool[0].annotations.requiresConfirmation
)
Write-Host "Current events: $($Direct.comparison.current_total)"
Write-Host "Previous events: $($Direct.comparison.previous_total)"
Write-Host "Largest event type: $($DirectLargest.name)"
Write-Host "Largest current count: $($DirectLargest.current_count)"
Write-Host "Largest previous count: $($DirectLargest.previous_count)"
Write-Host "Largest change: $($DirectLargest.absolute_change)"
Write-Host "Largest direction: $($DirectLargest.direction)"
Write-Host "Event type contributors: $ContributorCounts"
Write-Host "Contributor groups bounded: True"
Write-Host "Direct/Harness/Agent contributors match: True"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard contributor assets: ready"
Write-Host "Event Change Contributors smoke test passed."
