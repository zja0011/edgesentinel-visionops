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
    "Checking confirmation-gated retention cleanup at " +
    "$BaseUrl/dashboard"
)

$Before = Invoke-Utf8JsonGet `
    -Path "/api/v1/system/retention-preview"
$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$Tool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "system.cleanup_retained_data"
    }
)
if (
    $Before.status -ne "COMPLETE" -or
    $Before.mode -ne "PREVIEW_ONLY" -or
    $Before.delete_performed -ne $false -or
    $Tool.Count -ne 1 -or
    $Tool[0].annotations.readOnlyHint -ne $false -or
    $Tool[0].annotations.riskLevel -ne "L2" -or
    $Tool[0].annotations.autoExecute -ne $false -or
    $Tool[0].annotations.requiresConfirmation -ne $true
) {
    throw "Retention cleanup prerequisites are invalid"
}

$Pending = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{ message = "Clean the previewed old logs" }

if ([int]$Before.candidates.file_count -eq 0) {
    if (
        $Pending.status -ne "COMPLETED" -or
        @($Pending.tool_results).Count -ne 1 -or
        $Pending.tool_results[0].tool_name -ne (
            "system.preview_data_retention"
        )
    ) {
        throw "Zero-candidate cleanup did not finish safely"
    }
    Write-Host ""
    Write-Host "Retention Cleanup Dashboard acceptance summary:"
    Write-Host "Candidate files: 0"
    Write-Host "Cleanup tool calls: 0"
    Write-Host "Delete performed: False"
    Write-Host "No eligible old logs were present."
    Write-Host "Retention Cleanup Dashboard smoke test passed."
    exit 0
}

$Results = @($Pending.tool_results)
$Arguments = $Pending.pending_confirmation.arguments
$Paths = @($Arguments.candidate_paths)
if (
    $Pending.status -ne "AWAITING_CONFIRMATION" -or
    $Pending.steps -ne 2 -or
    $Pending.pending_confirmation.tool_name -ne (
        "system.cleanup_retained_data"
    ) -or
    $Pending.pending_confirmation.risk -ne "L2" -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne (
        "system.preview_data_retention"
    ) -or
    $Results[0].status -ne "SUCCEEDED" -or
    [string]$Arguments.plan_id -notmatch (
        '^ret_[0-9a-f]{32}$'
    ) -or
    $Paths.Count -lt 1 -or
    $Paths.Count -gt 100
) {
    $Pending | ConvertTo-Json -Depth 12
    throw "Cleanup task did not pause with a bounded L2 plan"
}

foreach ($PathValue in $Paths) {
    $PathText = [string]$PathValue
    $Allowed = (
        $PathText.StartsWith("data/logs/") -or
        $PathText.StartsWith("data/harness/") -or
        $PathText -match (
            '^data/runtime/edgesentinel-[^/]+\.log$'
        )
    )
    if (
        -not $Allowed -or
        $PathText.StartsWith("/") -or
        $PathText.Contains("..")
    ) {
        throw "Unsafe pending cleanup path: $PathText"
    }
}

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
if (
    $StillPending.status -ne "AWAITING_CONFIRMATION" -or
    @($StillPending.tool_results).Count -ne 1
) {
    throw "Invalid confirmation changed the cleanup task"
}

$Cancelled = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/agent/tasks/$($Pending.task_id)/cancel"
    ) `
    -Payload @{ cancel = $true }
$After = Invoke-Utf8JsonGet `
    -Path "/api/v1/system/retention-preview"
$CleanupResults = @(
    $Cancelled.tool_results | Where-Object {
        $_.tool_name -eq "system.cleanup_retained_data"
    }
)
if (
    $Cancelled.status -ne "CANCELLED" -or
    $CleanupResults.Count -ne 0 -or
    [int]$After.candidates.file_count -ne (
        [int]$Before.candidates.file_count
    ) -or
    [int64]$After.candidates.bytes -ne (
        [int64]$Before.candidates.bytes
    ) -or
    $After.delete_performed -ne $false
) {
    throw "Cancelling cleanup changed the retention candidates"
}

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Pending.task_id)"
)
if (
    $Checkpoint.status -ne "CANCELLED" -or
    $null -ne $Checkpoint.pending_confirmation
) {
    throw "Cancelled cleanup checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="retention-cleanup-prompt"' -or
    $Javascript -notmatch (
        'pending.tool_name === "system.cleanup_retained_data"'
    ) -or
    $Javascript -notmatch (
        'activeAgentToolName === "system.cleanup_retained_data"'
    )
) {
    throw "Dashboard retention cleanup assets are incomplete"
}

$McpTools = @(
    $Tools.tools | Where-Object {
        $_.annotations.readOnlyHint -eq $true -and
        $_.annotations.riskLevel -eq "L0" -and
        $_.annotations.autoExecute -eq $true -and
        $_.annotations.requiresConfirmation -eq $false
    }
)
if ($McpTools.Count -ne 25) {
    throw "MCP read-only tool count is not 25"
}

Write-Host ""
Write-Host "Retention Cleanup Dashboard acceptance summary:"
Write-Host "Pending tool: $($Pending.pending_confirmation.tool_name)"
Write-Host "Risk: $($Pending.pending_confirmation.risk)"
Write-Host "Preview tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Plan ID: $($Arguments.plan_id)"
Write-Host "Approved candidate paths: $($Paths.Count)"
Write-Host "Candidate files before: $($Before.candidates.file_count)"
Write-Host "Candidate bytes before: $($Before.candidates.bytes)"
Write-Host "Invalid confirmation phrase: HTTP $InvalidStatus"
Write-Host "Cancelled task: $($Cancelled.status)"
Write-Host "Cleanup tool calls: $($CleanupResults.Count)"
Write-Host "Candidate files after: $($After.candidates.file_count)"
Write-Host "Candidate bytes after: $($After.candidates.bytes)"
Write-Host "Delete performed: $($After.delete_performed)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard L2 cleanup confirmation assets: ready"
Write-Host "Retention Cleanup Dashboard smoke test passed."
