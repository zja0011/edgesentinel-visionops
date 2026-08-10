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

function Wait-BottleCount {
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

Write-Host "Checking inventory comparison Agent at $BaseUrl"

$Health = Invoke-Utf8Get -Path "/health"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
if ($Health.status -ne "ok") {
    throw "EdgeSentinel API is not healthy"
}
$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "inventory.compare_state"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "inventory.compare_state policy metadata is invalid"
}

Write-Host ""
Write-Host "PREPARE:"
Write-Host "1. Remove every bottle from the camera view."
Write-Host "2. Keep the empty scene unchanged."
Read-Host "Press Enter when no bottle is visible"
Wait-BottleCount -StableCount 0 -RequireVisible $false |
    Out-Null

Write-Host ""
Write-Host "ACTION REQUIRED:"
Write-Host "1. Put exactly one bottle fully inside the camera view."
Write-Host "2. Keep the bottle visible and nearly still."
Write-Host "3. Do not remove it until this test finishes."
Read-Host "Press Enter after the bottle is in position"

$Inventory = Wait-BottleCount `
    -StableCount 1 `
    -RequireVisible $true
$InventoryItem = @($Inventory.items)[0]
if (@($InventoryItem.active_track_ids).Count -lt 1) {
    throw "The stable bottle has no track ID"
}

$Direct = Invoke-Utf8Get -Path (
    "/api/v1/inventory/compare" +
    "?object_class=bottle&expected_count=2"
)
$DirectComparisons = @($Direct.comparisons)
if (
    $Direct.status -ne "available" -or
    $Direct.stale -ne $false -or
    $Direct.read_only -ne $true -or
    $Direct.matches -ne $false -or
    [int]$Direct.compared_class_count -ne 1 -or
    [int]$Direct.total_expected -ne 2 -or
    [int]$Direct.total_current -ne 1 -or
    [int]$Direct.total_missing -ne 1 -or
    [int]$Direct.total_extra -ne 0 -or
    $DirectComparisons.Count -ne 1 -or
    $DirectComparisons[0].class_name -ne "bottle" -or
    [int]$DirectComparisons[0].visible_count -lt 1 -or
    @($DirectComparisons[0].active_track_ids).Count -lt 1
) {
    $Direct | ConvertTo-Json -Depth 12
    throw "Direct inventory comparison contract is invalid"
}

$Task = Invoke-Utf8AgentTask -Message (
    "Compare current bottle inventory with expected count 2."
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "inventory.compare_state" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Inventory comparison Agent task failed"
}

$Result = $Results[0].result
$Comparisons = @($Result.comparisons)
if (
    $Result.stale -ne $false -or
    $Result.read_only -ne $true -or
    $Result.matches -ne $false -or
    [int]$Result.total_expected -ne 2 -or
    [int]$Result.total_current -ne 1 -or
    [int]$Result.total_missing -ne 1 -or
    [int]$Result.total_extra -ne 0 -or
    $Comparisons.Count -ne 1 -or
    $Comparisons[0].class_name -ne "bottle" -or
    [int]$Comparisons[0].expected_count -ne 2 -or
    [int]$Comparisons[0].current_count -ne 1 -or
    [int]$Comparisons[0].missing_count -ne 1 -or
    @($Comparisons[0].active_track_ids).Count -lt 1
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Inventory comparison Agent result is invalid"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "inventory.compare_state"
    ) -or
    $Checkpoint.tool_results[0].result.matches -ne $false -or
    [int]$Checkpoint.tool_results[0].result.total_missing -ne 1
) {
    throw "Inventory comparison checkpoint does not match"
}
if ($Dashboard -notmatch (
    'id="inventory-compare-prompt"[\s\S]{0,180}data-prompt="'
)) {
    throw "Dashboard inventory comparison prompt is missing"
}

Write-Host ""
Write-Host "Inventory Comparison Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Object class: $($Comparisons[0].class_name)"
Write-Host "Expected count: $($Comparisons[0].expected_count)"
Write-Host "Current stable count: $($Comparisons[0].current_count)"
Write-Host "Current visible count: $($Comparisons[0].visible_count)"
Write-Host "Missing count: $($Comparisons[0].missing_count)"
Write-Host "Extra count: $($Comparisons[0].extra_count)"
Write-Host "Track IDs: $(@($Comparisons[0].active_track_ids) -join ', ')"
Write-Host "Matches: $($Result.matches)"
Write-Host "Vision stale: $($Result.stale)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard comparison prompt: ready"
Write-Host "You may now remove the bottle."
Write-Host "Inventory Comparison Agent smoke test passed."
