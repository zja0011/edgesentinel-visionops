param(
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-Utf8JsonPost {
    param(
        [string]$Uri,
        [hashtable]$Body
    )
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    $Client.Headers["Content-Type"] =
        "application/json; charset=utf-8"
    $Json = $Body | ConvertTo-Json -Depth 10 -Compress
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

function Get-Utf8Text {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "*/*"
    return $Utf8.GetString($Client.DownloadData($Uri))
}

Write-Host "Checking Agent execution budgets at $BaseUrl/dashboard"

$Task = Invoke-Utf8JsonPost `
    -Uri "$BaseUrl/api/v1/agent/tasks" `
    -Body @{ message = "How many people are currently in the camera view?" }
$Execution = $Task.execution
$Limits = $Execution.limits
$Usage = $Execution.usage
$BudgetErrors = @()
if ($Task.status -ne "COMPLETED") {
    $BudgetErrors += "status=$($Task.status)"
}
if ($Task.task_id -notmatch '^task_[0-9a-f]{32}$') {
    $BudgetErrors += "task_id=$($Task.task_id)"
}
if ($null -eq $Execution) {
    $BudgetErrors += "execution=missing"
}
elseif ($null -eq $Limits -or $null -eq $Usage) {
    $BudgetErrors += "limits_or_usage=missing"
}
else {
    if ($Execution.schema_version -ne "1.0") {
        $BudgetErrors += "schema_version=$($Execution.schema_version)"
    }
    if ($Limits.max_wall_seconds -ne 60) {
        $BudgetErrors += "max_wall_seconds=$($Limits.max_wall_seconds)"
    }
    if ($Limits.max_model_calls -ne 5) {
        $BudgetErrors += "max_model_calls=$($Limits.max_model_calls)"
    }
    if ($Limits.max_tool_calls -ne 8) {
        $BudgetErrors += "max_tool_calls=$($Limits.max_tool_calls)"
    }
    if ($Limits.max_external_tool_calls -ne 2) {
        $BudgetErrors += (
            "max_external_tool_calls=" +
            $Limits.max_external_tool_calls
        )
    }
    if ($Usage.model_calls -lt 1 -or $Usage.model_calls -gt 5) {
        $BudgetErrors += "model_calls=$($Usage.model_calls)"
    }
    # A remote model may answer from the supplied compact context without
    # invoking a tool. Zero tool calls is valid; the bounded unit acceptance
    # test separately proves that tool calls are counted and capped.
    if ($Usage.tool_calls -lt 0 -or $Usage.tool_calls -gt 8) {
        $BudgetErrors += "tool_calls=$($Usage.tool_calls)"
    }
    if (
        $Usage.external_tool_calls -lt 0 -or
        $Usage.external_tool_calls -gt 2
    ) {
        $BudgetErrors += (
            "external_tool_calls=" +
            $Usage.external_tool_calls
        )
    }
    if ($Usage.elapsed_seconds -lt 0) {
        $BudgetErrors += "elapsed_seconds=$($Usage.elapsed_seconds)"
    }
    if ($Execution.cancel_requested) {
        $BudgetErrors += "cancel_requested=true"
    }
    if (-not $Execution.cooperative) {
        $BudgetErrors += "cooperative=false"
    }
    if ($Execution.force_terminated) {
        $BudgetErrors += "force_terminated=true"
    }
}
if ($BudgetErrors.Count -gt 0) {
    throw (
        "The Agent task execution budget is invalid: " +
        ($BudgetErrors -join ", ")
    )
}

$StoredTask = (
    Get-Utf8Text (
        "$BaseUrl/api/v1/agent/tasks/$($Task.task_id)"
    ) |
        ConvertFrom-Json
)
if (
    $StoredTask.task_id -ne $Task.task_id -or
    $StoredTask.execution.limits.max_wall_seconds -ne 60 -or
    $StoredTask.execution.usage.model_calls -ne
        $Usage.model_calls -or
    $StoredTask.execution.usage.tool_calls -ne
        $Usage.tool_calls
) {
    throw "The terminal checkpoint did not retain execution usage"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
$Stylesheet = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.css"
)
$AssetErrors = @()
if ($Html -notmatch 'id="agent-run-budget"') {
    $AssetErrors += "agent-run-budget"
}
if ($Html -notmatch 'id="agent-job-cancel"') {
    $AssetErrors += "agent-job-cancel"
}
if ($Javascript -notmatch 'EXECUTION_STOPPED') {
    $AssetErrors += "EXECUTION_STOPPED"
}
if (
    $Javascript -notmatch 'agentJobCancel\.textContent' -or
    $Javascript -notmatch 'job\.status === "RUNNING"'
) {
    $AssetErrors += "safe-stop-renderer"
}
if ($Javascript -notmatch 'max_external_tool_calls') {
    $AssetErrors += "max_external_tool_calls"
}
if ($Stylesheet -notmatch '\.agent-run-metadata') {
    $AssetErrors += "agent-run-metadata"
}
if ($AssetErrors.Count -gt 0) {
    throw (
        "Dashboard execution-control assets are incomplete: " +
        ($AssetErrors -join ", ")
    )
}

Write-Host
Write-Host "Agent Execution Budget Dashboard acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Task ID: $($Task.task_id)"
Write-Host "Model calls: $($Usage.model_calls)/$($Limits.max_model_calls)"
Write-Host "Tool calls: $($Usage.tool_calls)/$($Limits.max_tool_calls)"
Write-Host "External tools: $($Usage.external_tool_calls)/$($Limits.max_external_tool_calls)"
Write-Host "Wall deadline: $($Limits.max_wall_seconds) seconds"
Write-Host "Elapsed: $($Usage.elapsed_seconds) seconds"
Write-Host "Checkpoint usage retained: True"
Write-Host "Cooperative cancellation: True"
Write-Host "Force termination used: $($Execution.force_terminated)"
Write-Host "Dashboard budget assets: ready"
Write-Host "Agent Execution Budget Dashboard smoke test passed."
