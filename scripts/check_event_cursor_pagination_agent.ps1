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

function Assert-Page {
    param(
        [object]$Payload,
        [string]$Source,
        [int]$Maximum
    )
    $Events = @($Payload.events)
    if (
        [int]$Payload.count -ne $Events.Count -or
        $Events.Count -gt $Maximum -or
        [string]$Payload.filters.status -ne "OPEN" -or
        [string]$Payload.filters.severity -ne "INFO" -or
        $Payload.read_only -ne $true -or
        [string]$Payload.pagination.order -ne (
            "timestamp_desc,frame_id_desc,event_id_desc"
        )
    ) {
        throw "$Source page contract is invalid"
    }
    foreach ($Event in $Events) {
        $Disposition = [string]$Event.status
        if ([string]::IsNullOrWhiteSpace($Disposition)) {
            $Disposition = [string]$Event.disposition_status
        }
        if (
            $Disposition -ne "OPEN" -or
            [string]$Event.severity -ne "INFO"
        ) {
            throw "$Source page contains an event outside filters"
        }
    }
}

function Assert-NoOverlap {
    param(
        [object[]]$First,
        [object[]]$Second,
        [string]$Source
    )
    $FirstIds = @($First | ForEach-Object {
        [string]$_.event_id
    })
    foreach ($Event in $Second) {
        if ($FirstIds -contains [string]$Event.event_id) {
            throw "$Source pages contain a duplicate event"
        }
    }
}

Write-Host (
    "Checking stable event cursor pagination at " +
    "$BaseUrl"
)

$QueryPath = (
    "/api/v1/events?limit=3&minutes=1440" +
    "&status=OPEN&severity=INFO"
)
$First = Invoke-Utf8JsonGet -Path $QueryPath
Assert-Page -Payload $First -Source "Direct first" -Maximum 3
if (
    $First.pagination.has_more -ne $true -or
    [string]::IsNullOrWhiteSpace(
        [string]$First.pagination.next_cursor
    )
) {
    throw "Direct first page does not expose a next cursor"
}

$DirectCursor = [string]$First.pagination.next_cursor
$EncodedCursor = [System.Uri]::EscapeDataString($DirectCursor)
$Second = Invoke-Utf8JsonGet -Path (
    "$QueryPath&cursor=$EncodedCursor"
)
Assert-Page -Payload $Second -Source "Direct second" -Maximum 3
Assert-NoOverlap `
    -First @($First.events) `
    -Second @($Second.events) `
    -Source "Direct"
if (
    [string]$Second.window.since_timestamp -ne
        [string]$First.window.since_timestamp -or
    [string]$Second.window.queried_at -ne
        [string]$First.window.queried_at
) {
    throw "Second page did not retain the original time window"
}

$Replacement = if ($DirectCursor[-1] -eq "0") {
    "1"
}
else {
    "0"
}
$TamperedCursor = (
    $DirectCursor.Substring(0, $DirectCursor.Length - 1) +
    $Replacement
)
Assert-HttpStatus `
    -Path (
        "$QueryPath&cursor=" +
        [System.Uri]::EscapeDataString($TamperedCursor)
    ) `
    -ExpectedStatus 422
Assert-HttpStatus `
    -Path (
        "/api/v1/events?limit=3&minutes=1440" +
        "&status=OPEN&severity=MEDIUM&cursor=" +
        $EncodedCursor
    ) `
    -ExpectedStatus 422

$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$QueryTool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "event.query"
    }
)
if (
    $QueryTool.Count -ne 1 -or
    $QueryTool[0].annotations.riskLevel -ne "L0" -or
    $QueryTool[0].annotations.readOnlyHint -ne $true -or
    $QueryTool[0].annotations.requiresConfirmation -ne $false -or
    [int]$QueryTool[0].inputSchema.properties.cursor.maxLength -ne
        2048
) {
    throw "Harness cursor schema or policy is invalid"
}

$HarnessFirst = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.query/invoke" `
    -Payload @{
        limit = 2
        minutes = 1440
        status = "OPEN"
        severity = "INFO"
    }
if (
    $HarnessFirst.status -ne "SUCCEEDED" -or
    $HarnessFirst.tool_name -ne "event.query"
) {
    throw "Harness first cursor page failed"
}
Assert-Page `
    -Payload $HarnessFirst.result `
    -Source "Harness first" `
    -Maximum 2
$HarnessCursor = [string](
    $HarnessFirst.result.pagination.next_cursor
)
if ([string]::IsNullOrWhiteSpace($HarnessCursor)) {
    throw "Harness first page has no next cursor"
}
$HarnessSecond = Invoke-Utf8JsonPost `
    -Path "/api/v1/harness/tools/event.query/invoke" `
    -Payload @{
        limit = 2
        minutes = 1440
        status = "OPEN"
        severity = "INFO"
        cursor = $HarnessCursor
    }
if ($HarnessSecond.status -ne "SUCCEEDED") {
    throw "Harness second cursor page failed"
}
Assert-Page `
    -Payload $HarnessSecond.result `
    -Source "Harness second" `
    -Maximum 2
Assert-NoOverlap `
    -First @($HarnessFirst.result.events) `
    -Second @($HarnessSecond.result.events) `
    -Source "Harness"

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "Show open INFO events" }
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
    $Results[0].tool_name -ne "event.query" -or
    $Results[0].status -ne "SUCCEEDED" -or
    $Results[0].result.pagination.has_more -ne $true -or
    [string]::IsNullOrWhiteSpace(
        [string]$Results[0].result.pagination.next_cursor
    ) -or
    $WriteCalls.Count -ne 0
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent cursor-aware query failed"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    [string]$Checkpoint.tool_results[0].result.pagination.next_cursor -ne
        [string]$Results[0].result.pagination.next_cursor
) {
    throw "Agent checkpoint did not preserve the signed cursor"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-load-more"' -or
    $Javascript -notmatch 'eventNextCursor' -or
    $Javascript -notmatch 'loadMoreEvents' -or
    $Javascript -notmatch 'parameters.set\("cursor", cursor\)' -or
    $Javascript -notmatch 'renderEvents\(payload, true\)'
) {
    throw "Dashboard cursor pagination assets are incomplete"
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
Write-Host "Event Cursor Pagination acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($QueryTool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $QueryTool[0].annotations.requiresConfirmation
)
Write-Host "Direct first page: $($First.count)"
Write-Host "Direct second page: $($Second.count)"
Write-Host "Direct overlap: 0"
Write-Host "Original window retained: True"
Write-Host "Tampered cursor rejected: HTTP 422"
Write-Host "Changed filters rejected: HTTP 422"
Write-Host "Harness first page: $($HarnessFirst.result.count)"
Write-Host "Harness second page: $($HarnessSecond.result.count)"
Write-Host "Harness overlap: 0"
Write-Host "Agent has more: $($Results[0].result.pagination.has_more)"
Write-Host "Read only: $($First.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard load-more assets: ready"
Write-Host "Event Cursor Pagination smoke test passed."
