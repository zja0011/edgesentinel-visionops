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

function Get-HttpStatus {
    param([string]$Path)

    $Client = New-Object System.Net.WebClient
    try {
        $null = $Client.DownloadData("$BaseUrl$Path")
        return 200
    }
    catch [System.Net.WebException] {
        if ($null -eq $_.Exception.Response) {
            throw
        }
        return [int]$_.Exception.Response.StatusCode
    }
    finally {
        $Client.Dispose()
    }
}

function Get-PostStatus {
    param(
        [string]$Path,
        [hashtable]$Payload
    )

    try {
        $null = Invoke-Utf8JsonPost `
            -Path $Path `
            -Payload $Payload
        return 200
    }
    catch [System.Net.WebException] {
        if ($null -eq $_.Exception.Response) {
            throw
        }
        return [int]$_.Exception.Response.StatusCode
    }
}

Write-Host (
    "Checking confirmation-gated reports at " +
    "$BaseUrl/dashboard"
)

$Health = Invoke-Utf8JsonGet -Path "/health"
if ($Health.status -ne "ok") {
    throw "API health check failed"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    -not ($Dashboard.Contains('id="agent-report"')) -or
    -not ($Dashboard.Contains('id="agent-report-link"')) -or
    -not ($Javascript.Contains("renderAgentReport")) -or
    -not ($Javascript.Contains("task.report_url")) -or
    -not ($Javascript.Contains('report.generate'))
) {
    throw "Dashboard report assets are incomplete"
}

$Message = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String(
        "55Sf5oiQ5LuK5pel5LqL5Lu25oql5ZGK"
    )
)

$CancelledPending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = $Message }
if (
    $CancelledPending.status -ne "AWAITING_CONFIRMATION" -or
    $CancelledPending.pending_confirmation.tool_name -ne (
        "report.generate"
    ) -or
    $CancelledPending.pending_confirmation.risk -ne "L1" -or
    $CancelledPending.tool_results.Count -ne 0
) {
    $CancelledPending | ConvertTo-Json -Depth 12
    throw "Report task did not pause for confirmation"
}
$Cancelled = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/agent/tasks/" +
        "$($CancelledPending.task_id)/cancel"
    ) `
    -Payload @{ cancel = $true }
$CancelledReportStatus = Get-HttpStatus `
    -Path (
        "/api/v1/agent/tasks/" +
        "$($CancelledPending.task_id)/report"
    )
if (
    $Cancelled.status -ne "CANCELLED" -or
    $Cancelled.tool_results.Count -ne 0 -or
    $CancelledReportStatus -ne 404
) {
    throw "Cancelled report task created an artifact"
}

$Pending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = $Message }
if (
    $Pending.status -ne "AWAITING_CONFIRMATION" -or
    $Pending.pending_confirmation.tool_name -ne "report.generate"
) {
    throw "Confirmed report task did not pause"
}

$Completed = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/agent/tasks/$($Pending.task_id)/confirm"
    ) `
    -Payload @{
        confirmation = "CONFIRM_TOOL_EXECUTION"
    }
$Tools = @($Completed.tool_results)
if (
    $Completed.status -ne "COMPLETED" -or
    $Completed.task_id -ne $Pending.task_id -or
    $Tools.Count -ne 1 -or
    $Tools[0].tool_name -ne "report.generate" -or
    $Tools[0].status -ne "SUCCEEDED" -or
    -not $Completed.report_url
) {
    $Completed | ConvertTo-Json -Depth 12
    throw "Confirmed report generation failed"
}
$ReportResult = $Tools[0].result
if (
    $null -eq $ReportResult.event_count -or
    [int]$ReportResult.event_count -lt 0 -or
    [string]::IsNullOrWhiteSpace(
        [string]$ReportResult.report_path
    ) -or
    -not ([string]$ReportResult.report_path).StartsWith(
        "data/reports/"
    ) -or
    [int]$ReportResult.bytes -le 0
) {
    throw "Generated report metadata is invalid"
}

$Checkpoint = Invoke-Utf8JsonGet `
    -Path "/api/v1/agent/tasks/$($Pending.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.report_url -ne $Completed.report_url
) {
    throw "Checkpoint report URL does not match"
}

$ReportClient = New-Object System.Net.WebClient
try {
    $ReportBytes = $ReportClient.DownloadData(
        "$BaseUrl$($Completed.report_url)"
    )
    $ContentType = $ReportClient.ResponseHeaders[
        "Content-Type"
    ]
    $IntegrityHeader = $ReportClient.ResponseHeaders[
        "X-EdgeSentinel-Report-SHA256"
    ]
}
finally {
    $ReportClient.Dispose()
}
$Hasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $ActualHashBytes = $Hasher.ComputeHash($ReportBytes)
}
finally {
    $Hasher.Dispose()
}
$ActualHash = (
    [System.BitConverter]::ToString($ActualHashBytes)
).Replace("-", "").ToLowerInvariant()
$ReportText = [System.Text.Encoding]::UTF8.GetString(
    $ReportBytes
)
if (
    -not $ContentType.StartsWith("text/markdown") -or
    $ReportBytes.Length -ne [int]$ReportResult.bytes -or
    $ActualHash -ne $ReportResult.sha256 -or
    $IntegrityHeader -ne $ActualHash -or
    -not $ReportText.StartsWith("# EdgeSentinel VisionOps") -or
    -not $ReportText.Contains($ReportResult.report_id)
) {
    throw "Downloaded report integrity validation failed"
}

$DuplicateStatus = Get-PostStatus `
    -Path (
        "/api/v1/agent/tasks/$($Pending.task_id)/confirm"
    ) `
    -Payload @{
        confirmation = "CONFIRM_TOOL_EXECUTION"
    }
if ($DuplicateStatus -ne 409) {
    throw "Duplicate report confirmation was not rejected"
}

Write-Host ""
Write-Host "Agent Report Dashboard acceptance summary:"
Write-Host "Cancelled task: $($Cancelled.status)"
Write-Host "Cancelled report: HTTP $CancelledReportStatus"
Write-Host "Pending tool: $($Pending.pending_confirmation.tool_name)"
Write-Host "Pending risk: $($Pending.pending_confirmation.risk)"
Write-Host "Confirmed task: $($Completed.status)"
Write-Host "Same task ID: $($Completed.task_id -eq $Pending.task_id)"
Write-Host "Report ID: $($ReportResult.report_id)"
Write-Host "Report date: $($ReportResult.date)"
Write-Host "Report event count: $($ReportResult.event_count)"
Write-Host "Report bytes: $($ReportBytes.Length)"
Write-Host "Content type: $ContentType"
Write-Host "SHA-256 match: $($ActualHash -eq $ReportResult.sha256)"
Write-Host "Integrity header match: $($IntegrityHeader -eq $ActualHash)"
Write-Host "Checkpoint URL match: $($Checkpoint.report_url -eq $Completed.report_url)"
Write-Host "Duplicate confirmation: HTTP $DuplicateStatus"
Write-Host "Dashboard report assets: ready"
Write-Host "Agent Report Dashboard smoke test passed."
