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

function Assert-SafeHistory {
    param(
        [object]$History,
        [string]$Source
    )
    if (
        $History.status -notin @("COMPLETE", "PARTIAL") -or
        [int]$History.record_count -lt 0 -or
        [int]$History.returned_count -lt 0 -or
        [int]$History.returned_count -gt 20 -or
        $History.paths_included -ne $false -or
        $History.absolute_paths_included -ne $false -or
        $History.read_only -ne $true
    ) {
        throw "$Source cleanup history is invalid"
    }
    foreach ($Record in @($History.records)) {
        $Names = @($Record.PSObject.Properties.Name)
        if (
            $Names -contains "candidate_paths" -or
            $Names -contains "deleted_paths" -or
            $Names -contains "failed_paths" -or
            [string]$Record.cleanup_id -notmatch (
                '^clean_[0-9a-f]{32}$'
            ) -or
            $Record.status -notin @("COMPLETED", "PARTIAL")
        ) {
            throw "$Source exposed an unsafe cleanup record"
        }
    }
}

Write-Host (
    "Checking read-only retention cleanup history at " +
    "$BaseUrl"
)

$PreviewBefore = Invoke-Utf8JsonGet `
    -Path "/api/v1/system/retention-preview"
$Direct = Invoke-Utf8JsonGet `
    -Path "/api/v1/system/retention-cleanup-history?limit=10"
Assert-SafeHistory -History $Direct -Source "Direct API"

$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$Tool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "system.get_retention_cleanup_history"
    }
)
if (
    $Tool.Count -ne 1 -or
    $Tool[0].annotations.readOnlyHint -ne $true -or
    $Tool[0].annotations.riskLevel -ne "L0" -or
    $Tool[0].annotations.autoExecute -ne $true -or
    $Tool[0].annotations.requiresConfirmation -ne $false -or
    [int]$Tool[0].inputSchema.properties.limit.maximum -ne 20
) {
    throw "Cleanup history tool policy is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/harness/tools/" +
        "system.get_retention_cleanup_history/invoke"
    ) `
    -Payload @{ limit = 10 }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne (
        "system.get_retention_cleanup_history"
    )
) {
    throw "Harness cleanup history query failed"
}
Assert-SafeHistory `
    -History $Harness.result `
    -Source "Harness"

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = "Show the retention cleanup audit history"
    }
$Results = @($Task.tool_results)
$CleanupCalls = @(
    $Results | Where-Object {
        $_.tool_name -eq "system.cleanup_retained_data"
    }
)
if (
    $Task.status -ne "COMPLETED" -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne (
        "system.get_retention_cleanup_history"
    ) -or
    $Results[0].status -ne "SUCCEEDED" -or
    $CleanupCalls.Count -ne 0 -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent cleanup history query failed"
}
Assert-SafeHistory `
    -History $Results[0].result `
    -Source "Agent"

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $null -ne $Checkpoint.pending_confirmation
) {
    throw "Cleanup history checkpoint is inconsistent"
}

$PreviewAfter = Invoke-Utf8JsonGet `
    -Path "/api/v1/system/retention-preview"
if (
    [int]$PreviewAfter.candidates.file_count -ne (
        [int]$PreviewBefore.candidates.file_count
    ) -or
    [int64]$PreviewAfter.candidates.bytes -ne (
        [int64]$PreviewBefore.candidates.bytes
    ) -or
    $PreviewAfter.delete_performed -ne $false
) {
    throw "Read-only history query changed cleanup candidates"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch (
        'id="retention-cleanup-history-status"'
    ) -or
    $Dashboard -notmatch (
        'id="retention-cleanup-history-prompt"'
    ) -or
    $Javascript -notmatch (
        '/api/v1/system/retention-cleanup-history'
    ) -or
    $Javascript -notmatch (
        'renderRetentionCleanupHistory'
    )
) {
    throw "Dashboard cleanup history assets are incomplete"
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
Write-Host "Retention Cleanup History acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($Tool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $Tool[0].annotations.requiresConfirmation
)
Write-Host "Audit exists: $($Direct.audit_exists)"
Write-Host "Cleanup records: $($Direct.record_count)"
Write-Host "Returned records: $($Direct.returned_count)"
Write-Host (
    "Deleted files total: " +
    $Direct.totals.deleted_file_count
)
Write-Host "Deleted bytes total: $($Direct.totals.deleted_bytes)"
Write-Host (
    "Failed files total: " +
    $Direct.totals.failed_file_count
)
Write-Host "Paths exposed: $($Direct.paths_included)"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Cleanup tool calls: $($CleanupCalls.Count)"
Write-Host "Candidate files unchanged: $($PreviewAfter.candidates.file_count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard cleanup history status and prompt: ready"
Write-Host "Retention Cleanup History smoke test passed."
