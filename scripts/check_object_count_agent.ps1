param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [int]$WaitSeconds = 45
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"
$CountPath = (
    "/api/v1/vision/count" +
    "?object_class=bottle&minimum_confidence=0.5"
)

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

function Wait-LatestBottleCount {
    param([int]$ExpectedCount)
    $Deadline = (Get-Date).AddSeconds($WaitSeconds)
    $ConsecutiveMatches = 0
    do {
        try {
            $Candidate = Invoke-Utf8Get -Path $CountPath
            $Counts = @($Candidate.counts)
            $Ready = (
                $Candidate.status -eq "available" -and
                $Candidate.stale -eq $false -and
                $Candidate.read_only -eq $true -and
                $Counts.Count -eq 1 -and
                $Counts[0].class_name -eq "bottle" -and
                [int]$Candidate.total_count -eq $ExpectedCount -and
                [int]$Counts[0].count -eq $ExpectedCount
            )
            if ($Ready) {
                $ConsecutiveMatches += 1
                if ($ConsecutiveMatches -ge 2) {
                    return $Candidate
                }
            }
            else {
                $ConsecutiveMatches = 0
            }
        }
        catch {
            $Candidate = $null
            $ConsecutiveMatches = 0
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    throw "Latest-frame bottle count did not reach $ExpectedCount"
}

Write-Host "Checking latest-frame object count Agent at $BaseUrl"

$Health = Invoke-Utf8Get -Path "/health"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
if ($Health.status -ne "ok") {
    throw "EdgeSentinel API is not healthy"
}
$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "vision.count_objects"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "vision.count_objects policy metadata is invalid"
}

Write-Host ""
Write-Host "PREPARE:"
Write-Host "1. Remove every bottle from the camera view."
Write-Host "2. Keep the empty scene unchanged."
Read-Host "Press Enter when no bottle is visible"
Wait-LatestBottleCount -ExpectedCount 0 | Out-Null

Write-Host ""
Write-Host "ACTION REQUIRED:"
Write-Host "1. Put exactly one bottle fully inside the camera view."
Write-Host "2. Keep the bottle visible and nearly still."
Write-Host "3. Do not remove it until this test finishes."
Read-Host "Press Enter after the bottle is in position"

$Direct = Wait-LatestBottleCount -ExpectedCount 1
if (
    $Direct.status -ne "available" -or
    $Direct.stale -ne $false -or
    $Direct.read_only -ne $true -or
    [double]$Direct.minimum_confidence -ne 0.5 -or
    $null -ne $Direct.selected_zone_id -or
    @($Direct.requested_classes).Count -ne 1 -or
    @($Direct.requested_classes)[0] -ne "bottle" -or
    [int]$Direct.class_count -ne 1 -or
    [int]$Direct.detected_class_count -ne 1 -or
    [int]$Direct.total_count -ne 1
) {
    $Direct | ConvertTo-Json -Depth 12
    throw "Direct latest-frame object count contract is invalid"
}

$Task = Invoke-Utf8AgentTask -Message (
    "Count current bottles with minimum confidence 0.5."
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "vision.count_objects" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Latest-frame object count Agent task failed"
}

$Result = $Results[0].result
$Counts = @($Result.counts)
if (
    $Result.stale -ne $false -or
    $Result.read_only -ne $true -or
    [double]$Result.minimum_confidence -ne 0.5 -or
    $null -ne $Result.selected_zone_id -or
    @($Result.requested_classes).Count -ne 1 -or
    @($Result.requested_classes)[0] -ne "bottle" -or
    [int]$Result.class_count -ne 1 -or
    [int]$Result.detected_class_count -ne 1 -or
    [int]$Result.total_count -ne 1 -or
    $Counts.Count -ne 1 -or
    $Counts[0].class_name -ne "bottle" -or
    [int]$Counts[0].count -ne 1
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Latest-frame object count Agent result is invalid"
}
if (
    $null -ne $Result.detections -or
    $null -ne $Counts[0].bbox
) {
    throw "Object count exposed forbidden detection details"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "vision.count_objects"
    ) -or
    [int]$Checkpoint.tool_results[0].result.total_count -ne 1
) {
    throw "Latest-frame object count checkpoint does not match"
}
if ($Dashboard -notmatch (
    'id="object-count-prompt"[\s\S]{0,180}data-prompt="'
)) {
    throw "Dashboard object count prompt is missing"
}

Write-Host ""
Write-Host "Object Count Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Object class: $($Counts[0].class_name)"
Write-Host "Minimum confidence: $($Result.minimum_confidence)"
Write-Host "Current frame count: $($Counts[0].count)"
Write-Host "Total count: $($Result.total_count)"
Write-Host "Zone: global"
Write-Host "Vision stale: $($Result.stale)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard count prompt: ready"
Write-Host "You may now remove the bottle."
Write-Host "Object Count Agent smoke test passed."
