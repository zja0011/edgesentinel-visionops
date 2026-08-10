param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [switch]$AssetsOnly
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"

function Invoke-Utf8JsonGet {
    param([string]$Path)
    return Invoke-RestMethod `
        -Uri "$BaseUrl$Path" `
        -Method Get `
        -Headers @{ Accept = "application/json" }
}

function Invoke-Utf8JsonPost {
    param(
        [string]$Path,
        [hashtable]$Payload
    )
    $Json = $Payload | ConvertTo-Json -Depth 12 -Compress
    $Bytes = [System.Text.Encoding]::UTF8.GetBytes($Json)
    return Invoke-RestMethod `
        -Uri "$BaseUrl$Path" `
        -Method Post `
        -Headers @{ Accept = "application/json" } `
        -ContentType "application/json; charset=utf-8" `
        -Body $Bytes
}

function Get-PostStatus {
    param(
        [string]$Path,
        [hashtable]$Payload
    )
    try {
        Invoke-Utf8JsonPost -Path $Path -Payload $Payload | Out-Null
        return 200
    }
    catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function Test-DashboardAcknowledgementAssets {
    $WebClient = New-Object System.Net.WebClient
    $WebClient.Encoding = [System.Text.Encoding]::UTF8
    try {
        $Html = $WebClient.DownloadString("$BaseUrl/dashboard")
        $Javascript = $WebClient.DownloadString(
            "$BaseUrl/dashboard/assets/dashboard.js"
        )
        $Css = $WebClient.DownloadString(
            "$BaseUrl/dashboard/assets/dashboard.css"
        )
    }
    finally {
        $WebClient.Dispose()
    }
    if (
        -not $Html.Contains('id="event-acknowledge"') -or
        -not $Html.Contains('id="event-disposition-status"') -or
        -not $Javascript.Contains("requestEventAcknowledgement") -or
        -not $Javascript.Contains('event.acknowledge') -or
        -not $Css.Contains(".event-disposition-badge")
    ) {
        throw "Dashboard acknowledgement assets are incomplete"
    }
}

Write-Host "Checking confirmation-gated event acknowledgement at $BaseUrl/dashboard"

$Health = Invoke-Utf8JsonGet -Path "/health"
if ($Health.status -ne "ok") {
    throw "API health check failed"
}

$ToolPayload = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$AcknowledgeTool = @(
    $ToolPayload.tools | Where-Object {
        $_.name -eq "event.acknowledge"
    }
)
if (
    $AcknowledgeTool.Count -ne 1 -or
    $AcknowledgeTool[0].annotations.riskLevel -ne "L1" -or
    $AcknowledgeTool[0].annotations.autoExecute -ne $false -or
    $AcknowledgeTool[0].annotations.requiresConfirmation -ne $true
) {
    throw "event.acknowledge policy metadata is invalid"
}

Test-DashboardAcknowledgementAssets

$EventPayload = Invoke-Utf8JsonGet -Path "/api/v1/events?limit=100"
if ($AssetsOnly) {
    $Acknowledged = @(
        $EventPayload.events | Where-Object {
            $_.status -eq "ACKNOWLEDGED" -and
            $_.acknowledged_by -eq "agent_operator"
        } | Select-Object -First 1
    )
    if ($Acknowledged.Count -ne 1) {
        throw "No Agent-acknowledged event is available to verify"
    }
    Write-Host ""
    Write-Host "Event Acknowledgement Dashboard asset recheck summary:"
    Write-Host "Persisted event: $($Acknowledged[0].event_id)"
    Write-Host "Persisted status: $($Acknowledged[0].status)"
    Write-Host "Acknowledged at: $($Acknowledged[0].acknowledged_at)"
    Write-Host "Acknowledged by: $($Acknowledged[0].acknowledged_by)"
    Write-Host "Dashboard acknowledgement assets: ready"
    Write-Host "Event Acknowledgement Dashboard smoke test passed."
    exit 0
}

$Target = @(
    $EventPayload.events | Where-Object {
        $_.status -eq "OPEN"
    } | Select-Object -First 1
)
if ($Target.Count -ne 1) {
    throw "No OPEN event is available; create one new vision event first"
}
$EventId = [string]$Target[0].event_id
if ($EventId -notmatch "^evt_[0-9a-f]{32}$") {
    throw "Selected event ID is invalid"
}
$InitialEvidence = [string]$Target[0].evidence_urls.primary
$Message = "acknowledge event $EventId"

$CancelledPending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = $Message }
if (
    $CancelledPending.status -ne "AWAITING_CONFIRMATION" -or
    $CancelledPending.pending_confirmation.tool_name -ne (
        "event.acknowledge"
    ) -or
    $CancelledPending.pending_confirmation.arguments.event_id -ne (
        $EventId
    ) -or
    $CancelledPending.pending_confirmation.risk -ne "L1" -or
    @($CancelledPending.tool_results).Count -ne 0
) {
    $CancelledPending | ConvertTo-Json -Depth 12
    throw "Acknowledgement task did not pause"
}
$Cancelled = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/agent/tasks/$($CancelledPending.task_id)/cancel"
    ) `
    -Payload @{ cancel = $true }
$AfterCancel = Invoke-Utf8JsonGet `
    -Path "/api/v1/events/$EventId"
if (
    $Cancelled.status -ne "CANCELLED" -or
    @($Cancelled.tool_results).Count -ne 0 -or
    $AfterCancel.status -ne "OPEN" -or
    $null -ne $AfterCancel.acknowledged_at
) {
    throw "Cancelled task changed the event"
}

$Pending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = $Message }
if (
    $Pending.status -ne "AWAITING_CONFIRMATION" -or
    $Pending.pending_confirmation.tool_name -ne "event.acknowledge"
) {
    throw "Confirmed acknowledgement task did not pause"
}
$Completed = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks/$($Pending.task_id)/confirm" `
    -Payload @{ confirmation = "CONFIRM_TOOL_EXECUTION" }
$Results = @($Completed.tool_results)
if (
    $Completed.status -ne "COMPLETED" -or
    $Completed.task_id -ne $Pending.task_id -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "event.acknowledge" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Completed | ConvertTo-Json -Depth 12
    throw "Confirmed acknowledgement failed"
}
$Result = $Results[0].result
if (
    $Result.event_id -ne $EventId -or
    $Result.status -ne "ACKNOWLEDGED" -or
    $Result.already_acknowledged -ne $false -or
    $Result.acknowledged_by -ne "agent_operator" -or
    -not ([string]$Result.acknowledged_at).EndsWith("+08:00")
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Acknowledgement result metadata is invalid"
}

$Updated = Invoke-Utf8JsonGet -Path "/api/v1/events/$EventId"
if (
    $Updated.status -ne "ACKNOWLEDGED" -or
    $Updated.acknowledged_at -ne $Result.acknowledged_at -or
    $Updated.acknowledged_by -ne "agent_operator" -or
    [string]$Updated.evidence_urls.primary -ne $InitialEvidence
) {
    $Updated | ConvertTo-Json -Depth 12
    throw "Persisted event acknowledgement is invalid"
}
$Checkpoint = Invoke-Utf8JsonGet `
    -Path "/api/v1/agent/tasks/$($Pending.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.tool_results[0].result.event_id -ne $EventId -or
    $Checkpoint.tool_results[0].result.status -ne "ACKNOWLEDGED"
) {
    throw "Acknowledgement checkpoint does not match"
}
$DuplicateStatus = Get-PostStatus `
    -Path "/api/v1/agent/tasks/$($Pending.task_id)/confirm" `
    -Payload @{ confirmation = "CONFIRM_TOOL_EXECUTION" }
if ($DuplicateStatus -ne 409) {
    throw "Duplicate confirmation was not rejected"
}

Write-Host ""
Write-Host "Event Acknowledgement Dashboard acceptance summary:"
Write-Host "Target event: $EventId"
Write-Host "Initial status: OPEN"
Write-Host "Cancelled task: $($Cancelled.status)"
Write-Host "Cancelled tool calls: $(@($Cancelled.tool_results).Count)"
Write-Host "Status after cancellation: $($AfterCancel.status)"
Write-Host "Pending tool: $($Pending.pending_confirmation.tool_name)"
Write-Host "Pending risk: $($Pending.pending_confirmation.risk)"
Write-Host "Confirmed task: $($Completed.status)"
Write-Host "Same task ID: $($Completed.task_id -eq $Pending.task_id)"
Write-Host "Persisted status: $($Updated.status)"
Write-Host "Acknowledged at: $($Updated.acknowledged_at)"
Write-Host "Acknowledged by: $($Updated.acknowledged_by)"
Write-Host "Evidence retained: $([string]$Updated.evidence_urls.primary -eq $InitialEvidence)"
Write-Host "Duplicate confirmation: HTTP $DuplicateStatus"
Write-Host "Checkpoint status: $($Checkpoint.status)"
Write-Host "Dashboard acknowledgement assets: ready"
Write-Host "Event Acknowledgement Dashboard smoke test passed."
