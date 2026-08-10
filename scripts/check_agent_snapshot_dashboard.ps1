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

function Invoke-ExpectedGetFailure {
    param(
        [string]$Path,
        [int]$ExpectedStatus
    )

    $Client = New-Object System.Net.WebClient
    try {
        $null = $Client.DownloadData("$BaseUrl$Path")
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
    finally {
        $Client.Dispose()
    }
    throw "Expected HTTP $ExpectedStatus but the request succeeded"
}

function Download-AgentSnapshot {
    param([string]$Path)

    $Client = New-Object System.Net.WebClient
    try {
        $Bytes = $Client.DownloadData("$BaseUrl$Path")
        return [PSCustomObject]@{
            Bytes = $Bytes
            ContentType = $Client.ResponseHeaders["Content-Type"]
            Sha256 = (
                $Client.ResponseHeaders[
                    "X-EdgeSentinel-Snapshot-SHA256"
                ]
            )
            ContentDisposition = (
                $Client.ResponseHeaders["Content-Disposition"]
            )
        }
    }
    finally {
        $Client.Dispose()
    }
}

function Get-Sha256 {
    param([byte[]]$Bytes)

    $Algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $Digest = $Algorithm.ComputeHash($Bytes)
        return (
            ($Digest | ForEach-Object {
                $_.ToString("x2")
            }) -join ""
        )
    }
    finally {
        $Algorithm.Dispose()
    }
}

Write-Host (
    "Checking Agent snapshot evidence at " +
    "$BaseUrl/dashboard"
)

$Health = Invoke-Utf8JsonGet -Path "/health"
if ($Health.status -ne "ok") {
    throw "EdgeSentinel API is not healthy"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
$Styles = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.css"
if (
    -not ($Dashboard.Contains('id="agent-snapshot"')) -or
    -not ($Dashboard.Contains('id="agent-snapshot-image"')) -or
    -not ($Dashboard.Contains('id="agent-snapshot-link"')) -or
    -not ($Javascript.Contains("renderAgentSnapshot")) -or
    -not ($Javascript.Contains("task.snapshot_url")) -or
    -not ($Styles.Contains(".agent-snapshot"))
) {
    throw "Dashboard snapshot assets are incomplete"
}

$CancelledPending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "capture snapshot" }
$Cancelled = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/agent/tasks/" +
        "$($CancelledPending.task_id)/cancel"
    ) `
    -Payload @{ cancel = $true }
if (
    $Cancelled.status -ne "CANCELLED" -or
    $null -ne $Cancelled.snapshot_url
) {
    throw "A cancelled task unexpectedly exposed a snapshot"
}
$CancelledStatus = Invoke-ExpectedGetFailure `
    -Path (
        "/api/v1/agent/tasks/" +
        "$($Cancelled.task_id)/snapshot"
    ) `
    -ExpectedStatus 404

$Pending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "capture snapshot" }
$Confirmed = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/agent/tasks/" +
        "$($Pending.task_id)/confirm"
    ) `
    -Payload @{ confirmation = "CONFIRM_TOOL_EXECUTION" }
$Tools = @($Confirmed.tool_results)
if (
    $Confirmed.status -ne "COMPLETED" -or
    $Tools.Count -ne 1 -or
    $Tools[0].tool_name -ne "camera.capture_snapshot" -or
    $Tools[0].status -ne "SUCCEEDED" -or
    [string]::IsNullOrWhiteSpace(
        [string]$Confirmed.snapshot_url
    )
) {
    $Confirmed | ConvertTo-Json -Depth 12
    throw "The confirmed task did not expose a snapshot URL"
}

$Download = Download-AgentSnapshot `
    -Path $Confirmed.snapshot_url
$Bytes = [byte[]]$Download.Bytes
$ActualSha256 = Get-Sha256 -Bytes $Bytes
$Recorded = $Tools[0].result
if (
    $Download.ContentType -notlike "image/jpeg*" -or
    $Bytes.Length -ne [int]$Recorded.bytes -or
    $Bytes.Length -le 4 -or
    $Bytes[0] -ne 0xFF -or
    $Bytes[1] -ne 0xD8 -or
    $Bytes[$Bytes.Length - 2] -ne 0xFF -or
    $Bytes[$Bytes.Length - 1] -ne 0xD9 -or
    $ActualSha256 -ne [string]$Recorded.sha256 -or
    $Download.Sha256 -ne [string]$Recorded.sha256 -or
    $Download.ContentDisposition -notlike "inline; filename=*"
) {
    throw "Downloaded snapshot does not match its audited result"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Confirmed.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.snapshot_url -ne $Confirmed.snapshot_url
) {
    throw "Checkpoint snapshot URL is inconsistent"
}

$MissingStatus = Invoke-ExpectedGetFailure `
    -Path (
        "/api/v1/agent/tasks/" +
        "task_00000000000000000000000000000000/snapshot"
    ) `
    -ExpectedStatus 404

Write-Host ""
Write-Host "Agent Snapshot Dashboard acceptance summary:"
Write-Host "Cancelled task snapshot: HTTP $CancelledStatus"
Write-Host "Confirmed task: $($Confirmed.status)"
Write-Host "Snapshot URL: $($Confirmed.snapshot_url)"
Write-Host "Content type: $($Download.ContentType)"
Write-Host "JPEG bytes: $($Bytes.Length)"
Write-Host "SHA-256 match: $($ActualSha256 -eq [string]$Recorded.sha256)"
Write-Host "Integrity header match: $($Download.Sha256 -eq [string]$Recorded.sha256)"
Write-Host "Checkpoint URL match: $($Checkpoint.snapshot_url -eq $Confirmed.snapshot_url)"
Write-Host "Unknown task snapshot: HTTP $MissingStatus"
Write-Host "Dashboard snapshot preview assets: ready"
Write-Host "Agent Snapshot Dashboard smoke test passed."
