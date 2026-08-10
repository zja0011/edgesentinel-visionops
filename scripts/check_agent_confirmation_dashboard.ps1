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
        $Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
        return $Text | ConvertFrom-Json
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
        $Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
        return $Text | ConvertFrom-Json
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
    "Checking protected Agent confirmation at " +
    "$BaseUrl/dashboard"
)

$Health = Invoke-Utf8JsonGet -Path "/health"
if (
    $Health.status -ne "ok" -or
    $Health.agent_model.mode -ne "offline"
) {
    throw "The systemd service must be healthy in offline model mode"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
$Styles = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.css"
if (
    -not ($Dashboard.Contains('id="agent-confirmation"')) -or
    -not ($Dashboard.Contains('id="agent-confirm"')) -or
    -not ($Dashboard.Contains('id="agent-cancel"')) -or
    -not ($Javascript.Contains("resolveAgentConfirmation")) -or
    -not ($Javascript.Contains("CONFIRM_TOOL_EXECUTION")) -or
    -not ($Styles.Contains(".agent-confirmation"))
) {
    throw "Dashboard confirmation assets are incomplete"
}

$CancelPending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "capture snapshot" }
if (
    $CancelPending.status -ne "AWAITING_CONFIRMATION" -or
    $CancelPending.pending_confirmation.tool_name -ne (
        "camera.capture_snapshot"
    ) -or
    $CancelPending.pending_confirmation.risk -ne "L1" -or
    @($CancelPending.tool_results).Count -ne 0
) {
    $CancelPending | ConvertTo-Json -Depth 12
    throw "The cancellation test did not pause for confirmation"
}

$Cancelled = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/agent/tasks/" +
        "$($CancelPending.task_id)/cancel"
    ) `
    -Payload @{ cancel = $true }
if (
    $Cancelled.status -ne "CANCELLED" -or
    @($Cancelled.tool_results).Count -ne 0 -or
    [string]::IsNullOrWhiteSpace([string]$Cancelled.answer)
) {
    $Cancelled | ConvertTo-Json -Depth 12
    throw "The pending action was not cancelled safely"
}
$CancelCheckpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Cancelled.task_id)"
)
if (
    $CancelCheckpoint.status -ne "CANCELLED" -or
    $null -ne $CancelCheckpoint.pending_confirmation
) {
    throw "The cancelled checkpoint is inconsistent"
}

$ConfirmPending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "capture snapshot" }
if ($ConfirmPending.status -ne "AWAITING_CONFIRMATION") {
    throw "The confirmation test did not pause"
}
$ConfirmPath = (
    "/api/v1/agent/tasks/" +
    "$($ConfirmPending.task_id)/confirm"
)
$InvalidStatus = Invoke-ExpectedHttpFailure `
    -Path $ConfirmPath `
    -Payload @{ confirmation = "yes" } `
    -ExpectedStatus 422
$StillPending = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($ConfirmPending.task_id)"
)
if ($StillPending.status -ne "AWAITING_CONFIRMATION") {
    throw "An invalid phrase changed the pending task"
}

$Confirmed = Invoke-Utf8JsonPost `
    -Path $ConfirmPath `
    -Payload @{ confirmation = "CONFIRM_TOOL_EXECUTION" }
$Tools = @($Confirmed.tool_results)
if (
    $Confirmed.status -ne "COMPLETED" -or
    $Confirmed.task_id -ne $ConfirmPending.task_id -or
    $Tools.Count -ne 1 -or
    $Tools[0].tool_name -ne "camera.capture_snapshot" -or
    $Tools[0].status -ne "SUCCEEDED" -or
    [string]::IsNullOrWhiteSpace(
        [string]$Tools[0].result.evidence_path
    ) -or
    [int]$Tools[0].result.bytes -le 0
) {
    $Confirmed | ConvertTo-Json -Depth 12
    throw "The explicitly confirmed snapshot failed"
}

$DuplicateStatus = Invoke-ExpectedHttpFailure `
    -Path $ConfirmPath `
    -Payload @{ confirmation = "CONFIRM_TOOL_EXECUTION" } `
    -ExpectedStatus 409
$FinalCheckpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Confirmed.task_id)"
)
if (
    $FinalCheckpoint.status -ne "COMPLETED" -or
    @($FinalCheckpoint.tool_results).Count -ne 1 -or
    $null -ne $FinalCheckpoint.pending_confirmation
) {
    throw "The completed checkpoint is inconsistent"
}

Write-Host ""
Write-Host "Agent Confirmation Dashboard acceptance summary:"
Write-Host "Cancelled task: $($Cancelled.status)"
Write-Host "Cancelled tool calls: $(@($Cancelled.tool_results).Count)"
Write-Host "Invalid confirmation phrase: HTTP $InvalidStatus"
Write-Host "Confirmed task: $($Confirmed.status)"
Write-Host "Same task ID: $($Confirmed.task_id -eq $ConfirmPending.task_id)"
Write-Host "Tool: $($Tools[0].tool_name) $($Tools[0].status)"
Write-Host "JPEG bytes: $($Tools[0].result.bytes)"
Write-Host "Snapshot: $($Tools[0].result.evidence_path)"
Write-Host "Duplicate confirmation: HTTP $DuplicateStatus"
Write-Host "Final checkpoint: $($FinalCheckpoint.status)"
Write-Host "Dashboard confirmation assets: ready"
Write-Host "Agent Confirmation Dashboard smoke test passed."
