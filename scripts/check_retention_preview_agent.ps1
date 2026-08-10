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
    $Json = @{ message = $Message } | ConvertTo-Json -Compress
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

function Assert-RetentionPreview {
    param(
        [object]$Result,
        [string]$Source
    )
    $Policy = @($Result.policy)
    $Categories = @($Result.by_category)
    $Files = @($Result.candidate_files)
    $Protected = @($Result.protected_scopes)
    $Raw = $Result | ConvertTo-Json -Depth 12 -Compress
    $CategoryFiles = (
        $Categories |
        Measure-Object -Property candidate_file_count -Sum
    ).Sum
    $CategoryBytes = (
        $Categories |
        Measure-Object -Property candidate_bytes -Sum
    ).Sum

    if (
        $Result.status -ne "COMPLETE" -or
        $Result.mode -ne "PREVIEW_ONLY" -or
        $Result.root -ne "data" -or
        $Policy.Count -ne 3 -or
        $Categories.Count -ne 3 -or
        [int64]$CategoryFiles -ne (
            [int64]$Result.candidates.file_count
        ) -or
        [int64]$CategoryBytes -ne (
            [int64]$Result.candidates.bytes
        ) -or
        [int]$Result.candidates.returned_count -ne (
            $Files.Count
        ) -or
        $Files.Count -gt 100 -or
        [int]$Result.scan_errors -ne 0 -or
        $Result.truncated -ne $false -or
        [int]$Result.max_files -ne 100000 -or
        [int]$Result.candidate_limit -ne 100 -or
        $Result.delete_performed -ne $false -or
        $Result.absolute_paths_included -ne $false -or
        $Result.read_only -ne $true -or
        $Protected -notcontains "data/evidence" -or
        $Protected -notcontains "data/events" -or
        $Protected -notcontains "data/reports" -or
        $Protected -notcontains "data/benchmarks" -or
        $Protected -notcontains "data/state" -or
        $Protected -notcontains "data/runtime/service.json" -or
        $Raw.Contains("/workspace/") -or
        $Raw.Contains("/home/nvidia/") -or
        $Raw -match '"absolute_path":'
    ) {
        $Result | ConvertTo-Json -Depth 12
        throw "$Source retention preview is invalid"
    }

    $Logs = @(
        $Policy | Where-Object { $_.category -eq "logs" }
    )
    $Harness = @(
        $Policy | Where-Object { $_.category -eq "harness" }
    )
    $Runtime = @(
        $Policy | Where-Object { $_.category -eq "runtime" }
    )
    if (
        $Logs.Count -ne 1 -or
        [int]$Logs[0].retention_days -ne 3 -or
        [int]$Logs[0].min_keep_files -ne 5 -or
        $Harness.Count -ne 1 -or
        [int]$Harness[0].retention_days -ne 7 -or
        [int]$Harness[0].min_keep_files -ne 5 -or
        $Runtime.Count -ne 1 -or
        [int]$Runtime[0].retention_days -ne 3 -or
        [int]$Runtime[0].min_keep_files -ne 5 -or
        $Runtime[0].filename_rule -ne "edgesentinel-*.log"
    ) {
        throw "$Source fixed retention policy is invalid"
    }

    foreach ($File in $Files) {
        $Path = [string]$File.path
        $Allowed = (
            $Path.StartsWith("data/logs/") -or
            $Path.StartsWith("data/harness/") -or
            $Path -match (
                '^data/runtime/edgesentinel-[^/]+\.log$'
            )
        )
        if (
            -not $Allowed -or
            $Path.Contains("..") -or
            $Path.StartsWith("/") -or
            [double]$File.age_days -lt 3.0
        ) {
            throw "Unsafe retention candidate path: $Path"
        }
    }
}

Write-Host "Checking read-only data retention preview at $BaseUrl"

$Direct = Invoke-Utf8Get `
    -Path "/api/v1/system/retention-preview"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text -Path "/dashboard/assets/dashboard.js"

Assert-RetentionPreview -Result $Direct -Source "Direct API"

$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "system.preview_data_retention"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "system.preview_data_retention policy metadata is invalid"
}

$Task = Invoke-Utf8AgentTask -Message (
    "How much old data can be cleaned?"
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne (
        "system.preview_data_retention"
    ) -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Retention preview Agent task failed"
}

$Result = $Results[0].result
Assert-RetentionPreview -Result $Result -Source "Agent"

if (
    -not ([string]$Task.answer).Contains("COMPLETE") -or
    -not ([string]$Task.answer).Contains(
        [string]$Result.candidates.file_count
    ) -or
    -not ([string]$Task.answer).Contains(
        [string]$Result.candidates.bytes
    )
) {
    throw "Agent answer is missing preview values"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "system.preview_data_retention"
    ) -or
    $Checkpoint.tool_results[0].result.mode -ne (
        "PREVIEW_ONLY"
    ) -or
    $Checkpoint.tool_results[0].result.delete_performed -ne (
        $false
    )
) {
    throw "Retention preview checkpoint does not match"
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

if (
    $Dashboard -notmatch 'id="retention-preview-status"' -or
    $Dashboard -notmatch 'id="retention-preview-prompt"' -or
    $Dashboard -notmatch '19[^<]*5[^<]*3' -or
    $Javascript -notmatch (
        'retentionPreview: "/api/v1/system/retention-preview"'
    ) -or
    $Javascript -notmatch 'renderRetentionPreview'
) {
    throw "Dashboard retention preview assets are incomplete"
}

$ByName = @{}
foreach ($Category in @($Result.by_category)) {
    $ByName[$Category.category] = $Category
}

Write-Host ""
Write-Host "Data Retention Preview acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Status: $($Result.status)"
Write-Host "Mode: $($Result.mode)"
Write-Host "Scanned files: $($Result.scanned.file_count)"
Write-Host "Candidate files: $($Result.candidates.file_count)"
Write-Host "Candidate bytes: $($Result.candidates.bytes)"
Write-Host "Returned candidates: $($Result.candidates.returned_count)"
Write-Host "Logs candidates: $($ByName['logs'].candidate_file_count)"
Write-Host "Harness candidates: $($ByName['harness'].candidate_file_count)"
Write-Host "Runtime candidates: $($ByName['runtime'].candidate_file_count)"
Write-Host "Skipped symlinks: $($Result.skipped_symlinks)"
Write-Host "Truncated: $($Result.truncated)"
Write-Host "Delete performed: $($Result.delete_performed)"
Write-Host "Absolute paths exposed: $($Result.absolute_paths_included)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard retention preview status and prompt: ready"
Write-Host "Data Retention Preview smoke test passed."
