param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [int]$WaitSeconds = 30
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

Write-Host "Checking live zone status Agent at $BaseUrl"

$Health = Invoke-Utf8Get -Path "/health"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$AllZones = Invoke-Utf8Get -Path "/api/v1/vision/zones"
$Dashboard = Get-Utf8Text -Path "/dashboard"

if ($Health.status -ne "ok") {
    throw "EdgeSentinel API is not healthy"
}
$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "vision.get_zone_status"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "vision.get_zone_status policy metadata is invalid"
}
if (
    $AllZones.status -ne "available" -or
    $AllZones.zone_count -lt 2 -or
    @($AllZones.zones | Where-Object {
        $_.zone_id -eq "left_zone"
    }).Count -ne 1
) {
    $AllZones | ConvertTo-Json -Depth 10
    throw "Live zone API does not expose left_zone"
}

Write-Host ""
Write-Host "ACTION REQUIRED:"
Write-Host "1. Stand fully inside the left zone."
Write-Host "2. Keep your feet away from the center neutral band."
Write-Host "3. Remain visible until this test finishes."
Read-Host "Press Enter once you are standing in the left zone"

$Deadline = (Get-Date).AddSeconds($WaitSeconds)
$Direct = $null
do {
    try {
        $Candidate = Invoke-Utf8Get `
            -Path "/api/v1/vision/zones?zone_id=left_zone"
        if (
            $Candidate.status -eq "available" -and
            $Candidate.stale -eq $false -and
            $Candidate.zone_count -eq 1 -and
            $Candidate.zones[0].current_count -ge 1
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
    throw "No confirmed person appeared in left_zone"
}

$Task = Invoke-Utf8AgentTask `
    -Message "How many people are in left zone now?"
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "vision.get_zone_status" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Zone status Agent task failed"
}

$Result = $Results[0].result
if (
    $Result.stale -ne $false -or
    $Result.selected_zone_id -ne "left_zone" -or
    $Result.zone_count -ne 1 -or
    $Result.zones[0].zone_id -ne "left_zone" -or
    $Result.zones[0].current_count -lt 1 -or
    @($Result.zones[0].track_ids).Count -lt 1
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Zone status result contract is invalid"
}

$DirectAfter = Invoke-Utf8Get `
    -Path "/api/v1/vision/zones?zone_id=left_zone"
if (
    $DirectAfter.stale -ne $false -or
    $DirectAfter.zones[0].current_count -ne (
        $Result.zones[0].current_count
    )
) {
    throw "Agent zone count does not match the live zone API"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "vision.get_zone_status"
    ) -or
    $Checkpoint.tool_results[0].result.selected_zone_id -ne (
        "left_zone"
    )
) {
    throw "Zone status checkpoint does not match"
}
if ($Dashboard -notmatch (
    'id="zone-status-prompt"[\s\S]{0,160}data-prompt="'
)) {
    throw "Dashboard zone status prompt is missing"
}

Write-Host ""
Write-Host "Zone Status Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Selected zone: $($Result.selected_zone_id)"
Write-Host "Zone name: $($Result.zones[0].name)"
Write-Host "Current count: $($Result.zones[0].current_count)"
Write-Host "Track IDs: $(@($Result.zones[0].track_ids) -join ', ')"
Write-Host "Vision stale: $($Result.stale)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard zone prompt: ready"
Write-Host "You may now leave the camera frame."
Write-Host "Zone Status Agent smoke test passed."
