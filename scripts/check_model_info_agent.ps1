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

Write-Host "Checking read-only vision model Agent at $BaseUrl"

$Direct = Invoke-Utf8Get -Path "/api/v1/vision/model"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text -Path "/dashboard/assets/dashboard.js"

$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "vision.get_model_info"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "vision.get_model_info policy metadata is invalid"
}

$Task = Invoke-Utf8AgentTask -Message (
    "What vision model version is active and is its TensorRT engine intact?"
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "vision.get_model_info" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Vision model Agent task failed"
}

$Result = $Results[0].result
$Artifact = $Result.artifact
$Verification = $Result.verification
$RelativePath = [string]$Artifact.relative_path
if (
    $Result.network -ne "ssd-mobilenet-v2" -or
    $Result.backend -ne "TensorRT" -or
    $Artifact.precision -ne "FP16" -or
    [int64]$Artifact.size_bytes -le 0 -or
    ([string]$Artifact.sha256).Length -ne 64 -or
    $Verification.status -ne "MATCH" -or
    $Verification.expected_sha256 -ne $Artifact.sha256 -or
    $Verification.current_sha256 -ne $Artifact.sha256 -or
    $Result.read_only -ne $true -or
    $Result.absolute_paths_included -ne $false -or
    [string]::IsNullOrWhiteSpace($RelativePath) -or
    $RelativePath -match '^[\\/]' -or
    $RelativePath -match '^[A-Za-z]:' -or
    @($RelativePath -split '/') -contains '..'
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Vision model result contract is invalid"
}

if (
    $Direct.manifest_id -ne $Result.manifest_id -or
    $Direct.verification.status -ne "MATCH" -or
    $Direct.verification.current_sha256 -ne (
        $Result.verification.current_sha256
    )
) {
    throw "Agent model result does not match the direct API"
}

$RequiredAnswerValues = @(
    "ssd-mobilenet-v2",
    "TensorRT",
    "FP16",
    "MATCH"
)
foreach ($Value in $RequiredAnswerValues) {
    if (-not ([string]$Task.answer).Contains($Value)) {
        throw "Agent answer is missing model value: $Value"
    }
}
if (
    ([string]$Task.answer).Contains("unknown") -or
    ([string]$Task.answer).Contains("UNKNOWN")
) {
    throw "Agent answer contains unknown model fields"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "vision.get_model_info"
    ) -or
    $Checkpoint.tool_results[0].result.verification.status -ne (
        "MATCH"
    )
) {
    throw "Vision model checkpoint does not match"
}

if (
    $Dashboard -notmatch 'id="vision-model-runtime"' -or
    $Dashboard -notmatch (
        'id="model-info-prompt"[\s\S]{0,180}data-prompt="'
    ) -or
    $Javascript -notmatch 'model: "/api/v1/vision/model"' -or
    $Javascript -notmatch 'renderVisionModel'
) {
    throw "Dashboard vision model assets are incomplete"
}

Write-Host ""
Write-Host "Vision Model Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Manifest ID: $($Result.manifest_id)"
Write-Host "Network: $($Result.network)"
Write-Host "Backend: $($Result.backend)"
Write-Host "Precision: $($Artifact.precision)"
Write-Host "Engine: $RelativePath"
Write-Host "Engine bytes: $($Artifact.size_bytes)"
Write-Host "SHA-256: $($Artifact.sha256)"
Write-Host "Integrity: $($Verification.status)"
Write-Host "L4T: $($Result.platform.l4t_release)"
Write-Host "Architecture: $($Result.platform.architecture)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Absolute paths exposed: $($Result.absolute_paths_included)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard model status and prompt: ready"
Write-Host "Vision Model Agent smoke test passed."
