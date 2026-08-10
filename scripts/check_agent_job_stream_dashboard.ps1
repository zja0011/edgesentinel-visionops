param(
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-Utf8JsonPost {
    param(
        [string]$Uri,
        [hashtable]$Body,
        [string]$IdempotencyKey = ""
    )
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    $Client.Headers["Content-Type"] =
        "application/json; charset=utf-8"
    if (-not [string]::IsNullOrWhiteSpace($IdempotencyKey)) {
        $Client.Headers["Idempotency-Key"] = $IdempotencyKey
    }
    $Json = $Body | ConvertTo-Json -Depth 12 -Compress
    return (
        $Utf8.GetString(
            $Client.UploadData(
                $Uri,
                "POST",
                $Utf8.GetBytes($Json)
            )
        ) |
            ConvertFrom-Json
    )
}

function Get-Utf8Json {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    return (
        $Utf8.GetString($Client.DownloadData($Uri)) |
            ConvertFrom-Json
    )
}

function Get-Utf8Text {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "*/*"
    return $Utf8.GetString($Client.DownloadData($Uri))
}

function Get-HttpStatusCode {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)
    $Exception = $ErrorRecord.Exception
    while ($null -ne $Exception) {
        if ($null -ne $Exception.Response) {
            return [int]$Exception.Response.StatusCode
        }
        $Exception = $Exception.InnerException
    }
    return $null
}

Write-Host "Checking bounded Agent jobs and SSE at $BaseUrl/dashboard"

$Key = "job-stream-$([Guid]::NewGuid().ToString('N'))"
$Body = @{
    message = "How many people are currently in the camera view?"
}
$Job = Invoke-Utf8JsonPost `
    -Uri "$BaseUrl/api/v1/agent/jobs" `
    -Body $Body `
    -IdempotencyKey $Key
if (
    $Job.status -ne "QUEUED" -or
    $Job.job_id -notmatch '^job_[0-9a-f]{32}$' -or
    $Job.idempotent_replay -or
    $Job.request_body_persisted -or
    -not $Job.safe_cancel -or
    $Job.queue.max_pending -ne 16 -or
    $Job.queue.workers -ne 1
) {
    throw "The submitted Agent job is invalid"
}

$Replay = Invoke-Utf8JsonPost `
    -Uri "$BaseUrl/api/v1/agent/jobs" `
    -Body $Body `
    -IdempotencyKey $Key
if (
    $Replay.job_id -ne $Job.job_id -or
    -not $Replay.idempotent_replay
) {
    throw "The idempotent Agent job was not replayed"
}

$ConflictRejected = $false
try {
    Invoke-Utf8JsonPost `
        -Uri "$BaseUrl/api/v1/agent/jobs" `
        -Body @{ message = "A different request" } `
        -IdempotencyKey $Key | Out-Null
} catch {
    if ((Get-HttpStatusCode $_) -eq 409) {
        $ConflictRejected = $true
    } else {
        throw
    }
}
if (-not $ConflictRejected) {
    throw "Changed request reused an idempotency key"
}

$CancelKey = "job-cancel-$([Guid]::NewGuid().ToString('N'))"
$CancelJob = Invoke-Utf8JsonPost `
    -Uri "$BaseUrl/api/v1/agent/jobs" `
    -Body @{ message = "Reply with cancel-target only." } `
    -IdempotencyKey $CancelKey
if ($CancelJob.status -ne "QUEUED") {
    throw "The cancellation target did not remain queued"
}
$Cancelled = Invoke-Utf8JsonPost `
    -Uri (
        "$BaseUrl/api/v1/agent/jobs/" +
        "$($CancelJob.job_id)/cancel"
    ) `
    -Body @{ cancel = $true }
if (
    $Cancelled.status -ne "CANCELLED" -or
    $null -ne $Cancelled.task_id -or
    $Cancelled.safe_cancel
) {
    throw "The queued Agent job was not cancelled safely"
}

$Sse = Get-Utf8Text (
    "$BaseUrl/api/v1/agent/jobs/$($Job.job_id)/events?after=-1"
)
if (
    $Sse -notmatch 'event: status' -or
    $Sse -notmatch 'data: \{' -or
    $Sse -notmatch '"status":"COMPLETED"'
) {
    throw "The Agent SSE stream is incomplete"
}

$Completed = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/jobs/$($Job.job_id)"
)
if (
    $Completed.status -ne "COMPLETED" -or
    $Completed.task_id -notmatch '^task_[0-9a-f]{32}$' -or
    $Completed.task_status -ne "COMPLETED" -or
    $Completed.sequence -lt 2 -or
    $Completed.safe_cancel
) {
    throw "The completed Agent job metadata is invalid"
}
$Task = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/$($Completed.task_id)"
)
if (
    $Task.status -ne "COMPLETED" -or
    @($Task.tool_results).Count -lt 1 -or
    @($Task.tool_results)[-1].tool_name -ne
        "vision.get_people_count"
) {
    throw "The streamed Agent job did not produce the expected task"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
$Stylesheet = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.css"
)
if (
    $Html -notmatch 'id="agent-job-cancel"' -or
    $Javascript -notmatch 'new EventSource' -or
    $Javascript -notmatch 'waitForAgentJob' -or
    $Javascript -notmatch 'Idempotency-Key' -or
    $Javascript -notmatch 'cancelQueuedAgentJob' -or
    $Stylesheet -notmatch '\.agent-job-cancel'
) {
    throw "Dashboard Agent job streaming assets are incomplete"
}

$UnknownRejected = $false
try {
    Get-Utf8Json (
        "$BaseUrl/api/v1/agent/jobs/" +
        "job_00000000000000000000000000000000"
    ) | Out-Null
} catch {
    if ((Get-HttpStatusCode $_) -eq 404) {
        $UnknownRejected = $true
    } else {
        throw
    }
}
if (-not $UnknownRejected) {
    throw "An unknown Agent job was not rejected"
}

Write-Host
Write-Host "Agent Job Stream acceptance summary:"
Write-Host "Submitted job: QUEUED"
Write-Host "Worker count: $($Job.queue.workers)"
Write-Host "Queue capacity: $($Job.queue.max_pending)"
Write-Host "Request body persisted: $($Job.request_body_persisted)"
Write-Host "Idempotent replay: True"
Write-Host "Changed request conflict: HTTP 409"
Write-Host "Queued cancellation: CANCELLED"
Write-Host "Cancelled task ID: absent"
Write-Host "SSE terminal status: COMPLETED"
Write-Host "SSE sequence: $($Completed.sequence)"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: vision.get_people_count SUCCEEDED"
Write-Host "Unknown job: HTTP 404"
Write-Host "Dashboard streaming assets: ready"
Write-Host "Agent Job Stream smoke test passed."
