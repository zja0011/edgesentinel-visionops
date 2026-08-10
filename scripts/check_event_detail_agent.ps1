param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"

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

function Invoke-Utf8Get {
    param([string]$Path)
    return (Get-Utf8Text -Path $Path) | ConvertFrom-Json
}

function Invoke-Utf8AgentTask {
    param([string]$Message)
    $Json = @{ message = $Message } |
        ConvertTo-Json -Compress
    $Body = [System.Text.Encoding]::UTF8.GetBytes($Json)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Content-Type"] = (
            "application/json; charset=utf-8"
        )
        $Bytes = $Client.UploadData(
            "$BaseUrl/api/v1/agent/tasks",
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

Write-Host "Checking exact event detail Agent at $BaseUrl"

$HealthBefore = Invoke-Utf8Get -Path "/health"
$Latest = Invoke-Utf8Get -Path "/api/v1/events?limit=1"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
if (
    $HealthBefore.status -ne "ok" -or
    $Latest.count -ne 1
) {
    throw "A healthy API with at least one event is required"
}

$EventId = [string]$Latest.events[0].event_id
if ($EventId -notmatch "^evt_[0-9a-f]{32}$") {
    throw "Latest event ID is invalid"
}
$DirectBefore = Invoke-Utf8Get `
    -Path "/api/v1/events/$EventId"

$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "event.get_detail"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "event.get_detail policy metadata is invalid"
}

$Task = Invoke-Utf8AgentTask `
    -Message "Show event detail $EventId"
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "event.get_detail" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 14
    throw "Event detail Agent task failed"
}

$Result = $Results[0].result
if (
    $Result.read_only -ne $true -or
    $Result.event_id -ne $EventId -or
    $Result.event_type -ne $DirectBefore.event_type -or
    $Result.severity -ne $DirectBefore.severity -or
    $Result.timestamp -ne $DirectBefore.timestamp -or
    $Result.camera_id -ne $DirectBefore.camera_id -or
    $Result.zone_id -ne $DirectBefore.zone_id -or
    $Result.object_class -ne $DirectBefore.object_class -or
    $Result.status -ne $DirectBefore.status
) {
    $Result | ConvertTo-Json -Depth 14
    throw "Event detail result does not match the direct API"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
$DirectAfter = Invoke-Utf8Get `
    -Path "/api/v1/events/$EventId"
$HealthAfter = Invoke-Utf8Get -Path "/health"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "event.get_detail"
    ) -or
    $Checkpoint.tool_results[0].result.event_id -ne $EventId
) {
    throw "Event detail checkpoint does not match"
}
if (
    $HealthAfter.database.event_count -ne (
        $HealthBefore.database.event_count
    ) -or
    $DirectAfter.status -ne $DirectBefore.status -or
    $DirectAfter.acknowledged_at -ne (
        $DirectBefore.acknowledged_at
    ) -or
    $DirectAfter.acknowledged_by -ne (
        $DirectBefore.acknowledged_by
    )
) {
    throw "Read-only detail query changed the event database"
}

$EvidenceKinds = @(
    $Result.evidence_urls.PSObject.Properties.Name
)
$DetailKeys = @($Result.details.PSObject.Properties.Name)

Write-Host ""
Write-Host "Event Detail Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Event ID: $($Result.event_id)"
Write-Host "Event type: $($Result.event_type)"
Write-Host "Object class: $($Result.object_class)"
Write-Host "Zone: $($Result.zone_id)"
Write-Host "Disposition: $($Result.status)"
Write-Host "Detail keys: $($DetailKeys.Count)"
Write-Host "Evidence kinds: $($EvidenceKinds -join ', ')"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Event count unchanged: True"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Event Detail Agent smoke test passed."
