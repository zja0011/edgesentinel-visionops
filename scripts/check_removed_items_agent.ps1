param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [int]$WaitSeconds = 45
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

function Wait-BottleInventory {
    param(
        [int]$StableCount,
        [bool]$RequireVisible
    )
    $Deadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        try {
            $Candidate = Invoke-Utf8Get -Path (
                "/api/v1/vision/inventory?object_class=bottle"
            )
            $Item = @($Candidate.items)[0]
            $VisibleReady = (
                (-not $RequireVisible) -or
                [int]$Item.visible_count -ge 1
            )
            if (
                $Candidate.status -eq "available" -and
                $Candidate.stale -eq $false -and
                [int]$Item.current_count -eq $StableCount -and
                $VisibleReady
            ) {
                return $Candidate
            }
        }
        catch {
            $Candidate = $null
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    throw "Bottle inventory did not reach stable count $StableCount"
}

Write-Host "Checking recent removed-items Agent at $BaseUrl"

$Health = Invoke-Utf8Get -Path "/health"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
if ($Health.status -ne "ok") {
    throw "EdgeSentinel API is not healthy"
}
$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "inventory.get_removed_items"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "inventory.get_removed_items policy metadata is invalid"
}

Write-Host ""
Write-Host "PREPARE:"
Write-Host "1. Remove every bottle from the camera view."
Write-Host "2. Keep the empty scene unchanged."
Read-Host "Press Enter when no bottle is visible"

$EmptyState = Wait-BottleInventory `
    -StableCount 0 `
    -RequireVisible $false
$Baseline = Invoke-Utf8Get -Path (
    "/api/v1/inventory/removed" +
    "?minutes=10&object_class=bottle&limit=50"
)
$BaselineIds = @(
    $Baseline.removals | ForEach-Object { $_.event_id }
)

Write-Host ""
Write-Host "ACTION 1:"
Write-Host "1. Put exactly one bottle fully inside the camera view."
Write-Host "2. Keep it visible and nearly still."
Read-Host "Press Enter after the bottle is in position"

$PresentState = Wait-BottleInventory `
    -StableCount 1 `
    -RequireVisible $true
$PresentItem = @($PresentState.items)[0]
if (@($PresentItem.active_track_ids).Count -lt 1) {
    throw "The stable bottle has no track ID"
}
$StableTrackIds = @($PresentItem.active_track_ids)

Write-Host ""
Write-Host "ACTION 2:"
Write-Host "1. Remove that bottle completely from the camera view."
Write-Host "2. Keep the scene bottle-free until this test finishes."
Read-Host "Press Enter after the bottle has been removed"

$Deadline = (Get-Date).AddSeconds($WaitSeconds)
$Removal = $null
$RemovedHistory = $null
do {
    try {
        $CurrentState = Invoke-Utf8Get -Path (
            "/api/v1/vision/inventory?object_class=bottle"
        )
        $RemovedHistory = Invoke-Utf8Get -Path (
            "/api/v1/inventory/removed" +
            "?minutes=10&object_class=bottle&limit=50"
        )
        $NewRemovals = @(
            $RemovedHistory.removals | Where-Object {
                $_.event_id -notin $BaselineIds
            }
        )
        if (
            $CurrentState.stale -eq $false -and
            [int]$CurrentState.total_current -eq 0 -and
            $NewRemovals.Count -ge 1
        ) {
            $Removal = $NewRemovals[0]
            break
        }
    }
    catch {
        $Removal = $null
    }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $Deadline)

if ($null -eq $Removal) {
    throw "No new confirmed bottle removal event was observed"
}
if (
    $Removal.object_class -ne "bottle" -or
    [int]$Removal.previous_count -ne 1 -or
    [int]$Removal.current_count -ne 0 -or
    [int]$Removal.removed_units -ne 1 -or
    @($Removal.previous_track_ids).Count -lt 1 -or
    -not $Removal.evidence_urls.primary -or
    -not $Removal.evidence_urls.before -or
    -not $Removal.evidence_urls.after
) {
    $Removal | ConvertTo-Json -Depth 10
    throw "The new bottle removal contract is invalid"
}

$Task = Invoke-Utf8AgentTask -Message (
    "Which bottle items were removed in the last 10 minutes?"
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "inventory.get_removed_items" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Removed-items Agent task failed"
}

$Result = $Results[0].result
$MatchingRemoval = @(
    $Result.removals | Where-Object {
        $_.event_id -eq $Removal.event_id
    }
)
if (
    $Result.read_only -ne $true -or
    [int]$Result.window_minutes -ne 10 -or
    $Result.selected_object_class -ne "bottle" -or
    [int]$Result.count -lt 1 -or
    [int]$Result.total_removed_units -lt 1 -or
    $MatchingRemoval.Count -ne 1
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Removed-items Agent result is invalid"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
$CheckpointMatch = @(
    $Checkpoint.tool_results[0].result.removals |
        Where-Object { $_.event_id -eq $Removal.event_id }
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "inventory.get_removed_items"
    ) -or
    $CheckpointMatch.Count -ne 1
) {
    throw "Removed-items checkpoint does not match"
}
if ($Dashboard -notmatch (
    'id="removed-items-prompt"[\s\S]{0,180}data-prompt="'
)) {
    throw "Dashboard removed-items prompt is missing"
}

Write-Host ""
Write-Host "Removed Items Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Window minutes: $($Result.window_minutes)"
Write-Host "New event ID: $($Removal.event_id)"
Write-Host "Object class: $($Removal.object_class)"
Write-Host "Count change: $($Removal.previous_count) -> $($Removal.current_count)"
Write-Host "Removed units: $($Removal.removed_units)"
Write-Host "Previous track IDs: $(@($Removal.previous_track_ids) -join ', ')"
Write-Host "Agent event count: $($Result.count)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard removed-items prompt: ready"
Write-Host "Removed Items Agent smoke test passed."
