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

Write-Host "Checking persisted runtime benchmark Agent at $BaseUrl"

$Direct = Invoke-Utf8Get -Path "/api/v1/system/benchmark"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text -Path "/dashboard/assets/dashboard.js"

$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "system.get_runtime_benchmark"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "system.get_runtime_benchmark policy metadata is invalid"
}

if (
    $Direct.status -ne "PASS" -or
    [int]$Direct.sample_count -lt 7 -or
    [int]$Direct.sample_count -ne (
        [int]$Direct.expected_sample_count
    ) -or
    [double]$Direct.api_success_percent -lt 95.0 -or
    [double]$Direct.vision_fresh_percent -lt 95.0 -or
    [double]$Direct.performance.minimum_fps -lt 5.0 -or
    [double]$Direct.performance.maximum_observed_p95_ms -gt 200.0 -or
    [double]$Direct.resources.peak_memory_used_gib -gt 3.3 -or
    [double]$Direct.resources.maximum_temperature_celsius -gt 75.0 -or
    [int]$Direct.camera.restart_count_delta -ne 0 -or
    $Direct.samples_included -ne $false -or
    $Direct.contains_secret -ne $false -or
    $Direct.absolute_paths_included -ne $false -or
    $Direct.read_only -ne $true -or
    [string]$Direct.report_sha256 -notmatch '^[0-9a-f]{64}$' -or
    [string]$Direct.report_path -notmatch (
        '^data/benchmarks/runtime-benchmark-' +
        '\d{8}T\d{6}\+0800\.json$'
    ) -or
    $Direct.PSObject.Properties.Name -contains "samples"
) {
    $Direct | ConvertTo-Json -Depth 12
    throw "Latest runtime benchmark summary is invalid"
}

$Task = Invoke-Utf8AgentTask -Message (
    "Did the latest runtime benchmark pass?"
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "system.get_runtime_benchmark" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Runtime benchmark Agent task failed"
}

$Result = $Results[0].result
if (
    $Result.status -ne "PASS" -or
    [string]$Result.report_sha256 -ne (
        [string]$Direct.report_sha256
    ) -or
    $Result.samples_included -ne $false -or
    $Result.contains_secret -ne $false -or
    $Result.absolute_paths_included -ne $false -or
    $Result.read_only -ne $true -or
    $Result.PSObject.Properties.Name -contains "samples"
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Runtime benchmark Agent result is invalid"
}

foreach ($Value in @("PASS", "FPS", "P95", "100")) {
    if (-not ([string]$Task.answer).Contains($Value)) {
        throw "Agent answer is missing benchmark value: $Value"
    }
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "system.get_runtime_benchmark"
    ) -or
    [string]$Checkpoint.tool_results[0].result.report_sha256 -ne (
        [string]$Direct.report_sha256
    )
) {
    throw "Runtime benchmark checkpoint does not match"
}

if (
    $Dashboard -notmatch 'id="runtime-benchmark-status"' -or
    $Dashboard -notmatch 'id="runtime-benchmark-prompt"' -or
    $Javascript -notmatch (
        'benchmark: "/api/v1/system/benchmark"'
    ) -or
    $Javascript -notmatch 'renderRuntimeBenchmark'
) {
    throw "Dashboard runtime benchmark assets are incomplete"
}

Write-Host ""
Write-Host "Runtime Benchmark Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Status: $($Result.status)"
Write-Host "Duration: $($Result.actual_duration_seconds) seconds"
Write-Host "Samples: $($Result.sample_count)/$($Result.expected_sample_count)"
Write-Host "API success: $($Result.api_success_percent)%"
Write-Host "Vision fresh: $($Result.vision_fresh_percent)%"
Write-Host "Minimum FPS: $($Result.performance.minimum_fps)"
Write-Host "Maximum observed P95: $($Result.performance.maximum_observed_p95_ms) ms"
Write-Host "Peak memory: $($Result.resources.peak_memory_used_gib) GiB"
Write-Host "Maximum temperature: $($Result.resources.maximum_temperature_celsius) C"
Write-Host "Camera restart delta: $($Result.camera.restart_count_delta)"
Write-Host "Report: $($Result.report_path)"
Write-Host "SHA-256: $($Result.report_sha256)"
Write-Host "Raw samples exposed: $($Result.samples_included)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard runtime benchmark status and prompt: ready"
Write-Host "Runtime Benchmark Agent smoke test passed."
