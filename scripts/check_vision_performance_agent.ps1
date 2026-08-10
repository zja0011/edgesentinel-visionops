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

Write-Host "Checking live vision performance Agent at $BaseUrl"

$Direct = Invoke-Utf8Get -Path "/api/v1/vision/performance"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text -Path "/dashboard/assets/dashboard.js"

$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "vision.get_performance"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "vision.get_performance policy metadata is invalid"
}

if (
    $Direct.status -ne "MEETS_TARGET" -or
    $Direct.stale -ne $false -or
    [int]$Direct.sample_count -lt 20 -or
    [double]$Direct.processing_fps -lt 5.0 -or
    [double]$Direct.pipeline_latency_ms.p95 -gt 200.0 -or
    $Direct.targets.fps_met -ne $true -or
    $Direct.targets.p95_met -ne $true -or
    $Direct.targets.all_met -ne $true -or
    $Direct.read_only -ne $true
) {
    $Direct | ConvertTo-Json -Depth 12
    throw "Direct vision performance does not meet the acceptance target"
}

$Task = Invoke-Utf8AgentTask -Message (
    "What is the current vision performance, processing FPS, and P95 latency?"
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "vision.get_performance" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Vision performance Agent task failed"
}

$Result = $Results[0].result
if (
    $Result.status -ne "MEETS_TARGET" -or
    $Result.stale -ne $false -or
    [int]$Result.sample_count -lt 20 -or
    [double]$Result.processing_fps -lt 5.0 -or
    [double]$Result.pipeline_latency_ms.p95 -gt 200.0 -or
    $Result.targets.all_met -ne $true -or
    $Result.read_only -ne $true -or
    $Result.PSObject.Properties.Name -contains "detections"
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Vision performance Agent result is invalid"
}

foreach ($Value in @("FPS", "P95", "MEETS_TARGET")) {
    if (-not ([string]$Task.answer).Contains($Value)) {
        throw "Agent answer is missing performance value: $Value"
    }
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "vision.get_performance"
    ) -or
    $Checkpoint.tool_results[0].result.targets.all_met -ne $true
) {
    throw "Vision performance checkpoint does not match"
}

if (
    $Dashboard -notmatch 'id="vision-performance-runtime"' -or
    $Dashboard -notmatch 'id="vision-performance-prompt"' -or
    $Javascript -notmatch (
        'performance: "/api/v1/vision/performance"'
    ) -or
    $Javascript -notmatch 'renderVisionPerformance'
) {
    throw "Dashboard vision performance assets are incomplete"
}

Write-Host ""
Write-Host "Vision Performance Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Status: $($Result.status)"
Write-Host "Frame ID: $($Result.frame_id)"
Write-Host "Window samples: $($Result.sample_count)"
Write-Host "Processing FPS: $($Result.processing_fps)"
Write-Host "Average latency: $($Result.pipeline_latency_ms.average) ms"
Write-Host "P50 latency: $($Result.pipeline_latency_ms.p50) ms"
Write-Host "P95 latency: $($Result.pipeline_latency_ms.p95) ms"
Write-Host "FPS target >= $($Result.targets.minimum_fps): $($Result.targets.fps_met)"
Write-Host "P95 target <= $($Result.targets.maximum_p95_ms) ms: $($Result.targets.p95_met)"
Write-Host "All targets met: $($Result.targets.all_met)"
Write-Host "Vision stale: $($Result.stale)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard performance status and prompt: ready"
Write-Host "Vision Performance Agent smoke test passed."
