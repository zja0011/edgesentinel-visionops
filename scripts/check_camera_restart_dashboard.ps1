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

function Invoke-ExpectedHttpFailure {
    param(
        [string]$Path,
        [hashtable]$Payload,
        [int]$ExpectedStatus
    )
    try {
        $null = Invoke-Utf8JsonPost -Path $Path -Payload $Payload
    }
    catch [System.Net.WebException] {
        $Response = $_.Exception.Response
        if ($null -eq $Response) {
            throw
        }
        $Status = [int]$Response.StatusCode
        if ($Status -ne $ExpectedStatus) {
            throw "Expected HTTP $ExpectedStatus but received HTTP $Status"
        }
        return $Status
    }
    throw "Expected HTTP $ExpectedStatus but the request succeeded"
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

Write-Host (
    "Checking confirmation-gated camera restart at " +
    "$BaseUrl/dashboard"
)

$HealthBefore = Invoke-Utf8JsonGet -Path "/health"
$CameraBefore = Invoke-Utf8JsonGet -Path "/api/v1/camera/status"
$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
if (
    $HealthBefore.status -ne "ok" -or
    $CameraBefore.status -ne "RUNNING" -or
    $CameraBefore.device_available -ne $true -or
    $CameraBefore.worker_running -ne $true -or
    $CameraBefore.state_stale -ne $false -or
    $CameraBefore.vision.available -ne $true
) {
    throw "The camera must be healthy before this test"
}
$Tool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "camera.restart"
    }
)
if (
    $Tool.Count -ne 1 -or
    $Tool[0].annotations.readOnlyHint -ne $false -or
    $Tool[0].annotations.riskLevel -ne "L2" -or
    $Tool[0].annotations.autoExecute -ne $false -or
    $Tool[0].annotations.requiresConfirmation -ne $true
) {
    throw "camera.restart policy metadata is invalid"
}

$CancelPending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "Restart camera inference." }
if (
    $CancelPending.status -ne "AWAITING_CONFIRMATION" -or
    $CancelPending.pending_confirmation.tool_name -ne (
        "camera.restart"
    ) -or
    $CancelPending.pending_confirmation.risk -ne "L2" -or
    @($CancelPending.tool_results).Count -ne 0
) {
    $CancelPending | ConvertTo-Json -Depth 12
    throw "The restart task did not pause for L2 confirmation"
}
$Cancelled = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/agent/tasks/" +
        "$($CancelPending.task_id)/cancel"
    ) `
    -Payload @{ cancel = $true }
$CameraAfterCancel = Invoke-Utf8JsonGet `
    -Path "/api/v1/camera/status"
if (
    $Cancelled.status -ne "CANCELLED" -or
    @($Cancelled.tool_results).Count -ne 0 -or
    [int]$CameraAfterCancel.generation -ne (
        [int]$CameraBefore.generation
    ) -or
    [int]$CameraAfterCancel.restart_count -ne (
        [int]$CameraBefore.restart_count
    )
) {
    throw "Cancelling the pending restart changed the runtime"
}

$Pending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "Restart camera inference." }
$ConfirmPath = (
    "/api/v1/agent/tasks/$($Pending.task_id)/confirm"
)
$InvalidStatus = Invoke-ExpectedHttpFailure `
    -Path $ConfirmPath `
    -Payload @{ confirmation = "yes" } `
    -ExpectedStatus 422
$StillPending = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Pending.task_id)"
)
if ($StillPending.status -ne "AWAITING_CONFIRMATION") {
    throw "An invalid phrase changed the pending restart"
}

$Confirmed = Invoke-Utf8JsonPost `
    -Path $ConfirmPath `
    -Payload @{ confirmation = "CONFIRM_TOOL_EXECUTION" }
$Results = @($Confirmed.tool_results)
if (
    $Confirmed.status -ne "COMPLETED" -or
    $Confirmed.task_id -ne $Pending.task_id -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "camera.restart" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Confirmed | ConvertTo-Json -Depth 12
    throw "The confirmed camera restart failed"
}
$Result = $Results[0].result
$CameraAfter = Invoke-Utf8JsonGet -Path "/api/v1/camera/status"
$HealthAfter = Invoke-Utf8JsonGet -Path "/health"
if (
    [int]$Result.after_generation -le (
        [int]$Result.before_generation
    ) -or
    [int]$Result.after_restart_count -le (
        [int]$Result.before_restart_count
    ) -or
    $Result.state_stale -ne $false -or
    [int]$Result.vision_frame_id -lt 1 -or
    $CameraAfter.status -ne "RUNNING" -or
    $CameraAfter.state_stale -ne $false -or
    $CameraAfter.vision.available -ne $true -or
    $CameraAfter.control.last_request_id -ne $Result.request_id -or
    $CameraAfter.control.status -ne "COMPLETED" -or
    $HealthAfter.status -ne "ok"
) {
    $Result | ConvertTo-Json -Depth 12
    throw "The recovered camera state is inconsistent"
}

$DuplicateStatus = Invoke-ExpectedHttpFailure `
    -Path $ConfirmPath `
    -Payload @{ confirmation = "CONFIRM_TOOL_EXECUTION" } `
    -ExpectedStatus 409
$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Confirmed.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    @($Checkpoint.tool_results).Count -ne 1 -or
    $Checkpoint.tool_results[0].result.request_id -ne (
        $Result.request_id
    ) -or
    $null -ne $Checkpoint.pending_confirmation
) {
    throw "The final restart checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="camera-restart-prompt"' -or
    -not (
        $Javascript.Contains(
            'pending.tool_name === "camera.restart"'
        )
    )
) {
    throw "Dashboard camera restart assets are incomplete"
}

Write-Host ""
Write-Host "Camera Restart Dashboard acceptance summary:"
Write-Host "Pending tool: $($Pending.pending_confirmation.tool_name)"
Write-Host "Risk: $($Pending.pending_confirmation.risk)"
Write-Host "Cancelled task: $($Cancelled.status)"
Write-Host "Cancelled tool calls: $(@($Cancelled.tool_results).Count)"
Write-Host "Invalid confirmation phrase: HTTP $InvalidStatus"
Write-Host "Confirmed task: $($Confirmed.status)"
Write-Host "Same task ID: $($Confirmed.task_id -eq $Pending.task_id)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host (
    "Generation: $($Result.before_generation) -> " +
    "$($Result.after_generation)"
)
Write-Host (
    "Restart count: $($Result.before_restart_count) -> " +
    "$($Result.after_restart_count)"
)
Write-Host "Recovery seconds: $($Result.recovery_seconds)"
Write-Host "Recovered frame ID: $($Result.vision_frame_id)"
Write-Host "API stayed online: True"
Write-Host "Duplicate confirmation: HTTP $DuplicateStatus"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Dashboard restart assets: ready"
Write-Host "Camera Restart Dashboard smoke test passed."
