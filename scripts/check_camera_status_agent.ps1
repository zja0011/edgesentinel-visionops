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

Write-Host "Checking read-only camera status Agent at $BaseUrl"

$Health = Invoke-Utf8Get -Path "/health"
$DirectBefore = Invoke-Utf8Get -Path "/api/v1/camera/status"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"

if (
    $Health.status -ne "ok" -or
    $DirectBefore.status -ne "RUNNING" -or
    $DirectBefore.device_available -ne $true -or
    $DirectBefore.worker_running -ne $true -or
    $DirectBefore.state_stale -ne $false -or
    $DirectBefore.vision.available -ne $true
) {
    $DirectBefore | ConvertTo-Json -Depth 10
    throw "Camera supervisor is not currently healthy"
}

$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "camera.get_status"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "camera.get_status policy metadata is invalid"
}

$Task = Invoke-Utf8AgentTask `
    -Message "Is the camera status healthy now?"
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "camera.get_status" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Camera status Agent task failed"
}

$Result = $Results[0].result
if (
    $Result.status -ne "RUNNING" -or
    $Result.healthy -ne $true -or
    $Result.read_only -ne $true -or
    $Result.device_available -ne $true -or
    $Result.worker_running -ne $true -or
    $Result.state_stale -ne $false -or
    $Result.vision.available -ne $true -or
    [int]$Result.generation -lt 1 -or
    [int]$Result.vision.frame_id -lt 1
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Camera status result contract is invalid"
}

$ForbiddenFields = @("worker_pid", "command", "environment")
foreach ($Field in $ForbiddenFields) {
    if ($Result.PSObject.Properties.Name -contains $Field) {
        throw "Camera status leaked forbidden field: $Field"
    }
}

$DirectAfter = Invoke-Utf8Get -Path "/api/v1/camera/status"
if (
    $DirectAfter.status -ne $Result.status -or
    $DirectAfter.device_available -ne $Result.device_available -or
    $DirectAfter.worker_running -ne $Result.worker_running -or
    [int]$DirectAfter.generation -ne [int]$Result.generation -or
    [int]$DirectAfter.restart_count -ne (
        [int]$Result.restart_count
    )
) {
    throw "Agent camera status does not match the direct API"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "camera.get_status"
    ) -or
    $Checkpoint.tool_results[0].result.healthy -ne $true
) {
    throw "Camera status checkpoint does not match"
}
if ($Dashboard -notmatch (
    'id="camera-status-prompt"[\s\S]{0,160}data-prompt="'
)) {
    throw "Dashboard camera status prompt is missing"
}

Write-Host ""
Write-Host "Camera Status Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Status: $($Result.status)"
Write-Host "Healthy: $($Result.healthy)"
Write-Host "Device available: $($Result.device_available)"
Write-Host "Worker running: $($Result.worker_running)"
Write-Host "Generation: $($Result.generation)"
Write-Host "Restart count: $($Result.restart_count)"
Write-Host "Vision frame: $($Result.vision.frame_id)"
Write-Host "State stale: $($Result.state_stale)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Forbidden fields absent: True"
Write-Host "Dashboard camera prompt: ready"
Write-Host "Camera Status Agent smoke test passed."
