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

function Assert-StorageResult {
    param(
        [object]$Result,
        [string]$Source
    )
    $Categories = @($Result.categories)
    $CategoryNames = @(
        "evidence",
        "events",
        "logs",
        "harness",
        "reports",
        "benchmarks",
        "runtime",
        "state",
        "other"
    )
    $ActualNames = @(
        $Categories | ForEach-Object { $_.name }
    )
    $CategoryFiles = (
        $Categories |
        Measure-Object -Property file_count -Sum
    ).Sum
    $CategoryBytes = (
        $Categories |
        Measure-Object -Property bytes -Sum
    ).Sum
    $Raw = $Result | ConvertTo-Json -Depth 10 -Compress

    if (
        $Result.status -ne "COMPLETE" -or
        $Result.root -ne "data" -or
        [int]$Result.totals.file_count -lt 1 -or
        [double]$Result.totals.bytes -lt 1 -or
        $Categories.Count -ne 9 -or
        @($CategoryNames | Where-Object {
            $_ -notin $ActualNames
        }).Count -ne 0 -or
        [int64]$CategoryFiles -ne (
            [int64]$Result.totals.file_count
        ) -or
        [int64]$CategoryBytes -ne (
            [int64]$Result.totals.bytes
        ) -or
        [int]$Result.scan_errors -ne 0 -or
        $Result.truncated -ne $false -or
        [int]$Result.max_files -ne 100000 -or
        $Result.absolute_paths_included -ne $false -or
        $Result.read_only -ne $true -or
        $Raw.Contains("/workspace/") -or
        $Raw.Contains("/home/nvidia/")
    ) {
        $Result | ConvertTo-Json -Depth 10
        throw "$Source storage result is invalid"
    }
}

Write-Host "Checking bounded project storage at $BaseUrl"

$Direct = Invoke-Utf8Get -Path "/api/v1/system/storage"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text -Path "/dashboard/assets/dashboard.js"

Assert-StorageResult -Result $Direct -Source "Direct API"

$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "system.get_storage_usage"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "system.get_storage_usage policy metadata is invalid"
}

$Task = Invoke-Utf8AgentTask -Message (
    "How much project data storage is used?"
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "system.get_storage_usage" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Storage usage Agent task failed"
}

$Result = $Results[0].result
Assert-StorageResult -Result $Result -Source "Agent"

if (
    -not ([string]$Task.answer).Contains("data") -or
    -not ([string]$Task.answer).Contains(
        [string]$Result.totals.file_count
    ) -or
    -not ([string]$Task.answer).Contains(
        [string]$Result.totals.bytes
    )
) {
    throw "Agent answer is missing bounded storage values"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "system.get_storage_usage"
    ) -or
    [int64]$Checkpoint.tool_results[0].result.totals.bytes -ne (
        [int64]$Result.totals.bytes
    )
) {
    throw "Storage usage checkpoint does not match"
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
    $Dashboard -notmatch 'id="storage-usage"' -or
    $Dashboard -notmatch 'id="storage-usage-prompt"' -or
    $Dashboard -notmatch '19[^<]*5[^<]*3' -or
    $Javascript -notmatch (
        'storage: "/api/v1/system/storage"'
    ) -or
    $Javascript -notmatch 'renderStorageUsage'
) {
    throw "Dashboard storage assets are incomplete"
}

$ByName = @{}
foreach ($Category in @($Result.categories)) {
    $ByName[$Category.name] = $Category
}

Write-Host ""
Write-Host "Storage Usage Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Status: $($Result.status)"
Write-Host "Root: $($Result.root)"
Write-Host "Files: $($Result.totals.file_count)"
Write-Host "Directories: $($Result.totals.directory_count)"
Write-Host "Total bytes: $($Result.totals.bytes)"
Write-Host "Evidence bytes: $($ByName['evidence'].bytes)"
Write-Host "Events bytes: $($ByName['events'].bytes)"
Write-Host "Harness bytes: $($ByName['harness'].bytes)"
Write-Host "Skipped symlinks: $($Result.skipped_symlinks)"
Write-Host "Scan errors: $($Result.scan_errors)"
Write-Host "Truncated: $($Result.truncated)"
Write-Host "Absolute paths exposed: $($Result.absolute_paths_included)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard storage status and prompt: ready"
Write-Host "Storage Usage Agent smoke test passed."
