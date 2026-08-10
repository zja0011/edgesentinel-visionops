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

Write-Host "Checking stable inventory Agent at $BaseUrl"

$Health = Invoke-Utf8Get -Path "/health"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"

if ($Health.status -ne "ok") {
    throw "EdgeSentinel API is not healthy"
}
$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "inventory.get_current_state"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "inventory.get_current_state policy metadata is invalid"
}

Write-Host ""
Write-Host "ACTION REQUIRED:"
Write-Host "1. Put exactly one bottle fully inside the camera view."
Write-Host "2. Keep the bottle visible and nearly still."
Write-Host "3. Do not remove it until this test finishes."
Read-Host "Press Enter after the bottle is in position"

$Deadline = (Get-Date).AddSeconds($WaitSeconds)
$Direct = $null
do {
    try {
        $Candidate = Invoke-Utf8Get -Path (
            "/api/v1/vision/inventory?object_class=bottle"
        )
        $Items = @($Candidate.items)
        if (
            $Candidate.status -eq "available" -and
            $Candidate.stale -eq $false -and
            $Candidate.selected_object_class -eq "bottle" -and
            $Items.Count -eq 1 -and
            [int]$Items[0].current_count -eq 1 -and
            [int]$Items[0].visible_count -ge 1 -and
            @($Items[0].active_track_ids).Count -ge 1
        ) {
            $Direct = $Candidate
            break
        }
    }
    catch {
        $Candidate = $null
    }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $Deadline)

if ($null -eq $Direct) {
    throw (
        "A stable single-bottle inventory was not observed within " +
        "$WaitSeconds seconds"
    )
}

$Task = Invoke-Utf8AgentTask `
    -Message "What is current bottle inventory?"
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "inventory.get_current_state" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Inventory Agent task failed"
}

$Result = $Results[0].result
$ResultItems = @($Result.items)
if (
    $Result.stale -ne $false -or
    $Result.read_only -ne $true -or
    $Result.selected_object_class -ne "bottle" -or
    [int]$Result.target_class_count -ne 1 -or
    [int]$Result.total_current -ne 1 -or
    [int]$Result.total_visible -lt 1 -or
    $ResultItems.Count -ne 1 -or
    $ResultItems[0].class_name -ne "bottle" -or
    [int]$ResultItems[0].current_count -ne 1 -or
    [int]$ResultItems[0].visible_count -lt 1 -or
    @($ResultItems[0].active_track_ids).Count -lt 1
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Inventory result contract is invalid"
}

$DirectAfter = Invoke-Utf8Get -Path (
    "/api/v1/vision/inventory?object_class=bottle"
)
if (
    $DirectAfter.stale -ne $false -or
    [int]$DirectAfter.total_current -ne (
        [int]$Result.total_current
    )
) {
    throw "Agent inventory does not match the live inventory API"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "inventory.get_current_state"
    ) -or
    $Checkpoint.tool_results[0].result.selected_object_class -ne (
        "bottle"
    ) -or
    [int]$Checkpoint.tool_results[0].result.total_current -ne 1
) {
    throw "Inventory checkpoint does not match"
}
if ($Dashboard -notmatch (
    'id="inventory-status-prompt"[\s\S]{0,180}data-prompt="'
)) {
    throw "Dashboard inventory prompt is missing"
}

Write-Host ""
Write-Host "Inventory State Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Selected class: $($Result.selected_object_class)"
Write-Host "Stable count: $($ResultItems[0].current_count)"
Write-Host "Visible count: $($ResultItems[0].visible_count)"
Write-Host "Track IDs: $(@($ResultItems[0].active_track_ids) -join ', ')"
Write-Host "Vision stale: $($Result.stale)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard inventory prompt: ready"
Write-Host "You may now remove the bottle."
Write-Host "Inventory State Agent smoke test passed."
