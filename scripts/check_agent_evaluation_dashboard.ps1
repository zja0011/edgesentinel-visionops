param(
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Utf8Text {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "*/*"
    return $Utf8.GetString($Client.DownloadData($Uri))
}

Write-Host "Checking the Agent Harness evaluation at $BaseUrl/dashboard"

$Report = (
    Get-Utf8Text "$BaseUrl/api/v1/harness/evaluations/latest" |
        ConvertFrom-Json
)
$Summary = $Report.summary
$Metrics = $Report.metrics
$Runtime = $Report.runtime
$Dataset = $Report.dataset
$Cases = @($Report.cases)

if (
    $Report.status -ne "PASS" -or
    $Dataset.dataset_id -ne "edgesentinel.agent-routing" -or
    $Dataset.version -ne "1.0.0" -or
    $Dataset.case_count -ne 7 -or
    $Dataset.sha256 -notmatch '^[0-9a-f]{64}$' -or
    $Summary.passed_cases -ne 7 -or
    $Summary.failed_cases -ne 0 -or
    $Summary.pass_rate -ne 1 -or
    $Cases.Count -ne 7
) {
    throw "The evaluation identity or result is invalid"
}

if (
    $Metrics.tool_selection_accuracy.rate -ne 1 -or
    $Metrics.argument_accuracy.rate -ne 1 -or
    $Metrics.tool_outcome_accuracy.rate -ne 1 -or
    $Metrics.confirmation_gate_accuracy.rate -ne 1 -or
    $Metrics.default_deny_accuracy.rate -ne 1 -or
    $Metrics.unexpected_policy_violations -ne 0
) {
    throw "The evaluation metrics are below the acceptance baseline"
}

if (
    $Runtime.mode -ne "offline-deterministic" -or
    $Runtime.external_requests -ne $false -or
    $Runtime.device_tools_executed -ne $false -or
    $Runtime.isolated_handlers -ne $true -or
    $Report.read_only -ne $true -or
    $Report.prompts_in_report -ne $false -or
    $Report.raw_model_content_in_report -ne $false -or
    $Metrics.model_tokens.available -ne $false -or
    $Metrics.estimated_cost.available -ne $false
) {
    throw "The isolated evaluation privacy contract is invalid"
}

$Serialized = $Report | ConvertTo-Json -Depth 20 -Compress
if (
    $Serialized -match '摄像头里面现在站着几位' -or
    $Serialized -match 'How many people are in the current camera view'
) {
    throw "An evaluation prompt was exposed in the report"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
$Stylesheet = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.css"
)
if (
    $Html -notmatch 'id="agent-evaluation-baseline"' -or
    $Html -notmatch 'id="agent-evaluation-badge"' -or
    $Javascript -notmatch 'renderAgentEvaluation' -or
    $Javascript -notmatch '/api/v1/harness/evaluations/latest' -or
    $Stylesheet -notmatch '\.agent-evaluation-baseline'
) {
    throw "Dashboard evaluation assets are incomplete"
}

Write-Host
Write-Host "Agent Evaluation Dashboard acceptance summary:"
Write-Host "Status: $($Report.status)"
Write-Host "Evaluation ID: $($Report.evaluation_id)"
Write-Host "Dataset: $($Dataset.dataset_id)@$($Dataset.version)"
Write-Host "Dataset SHA-256: $($Dataset.sha256)"
Write-Host "Cases: $($Summary.passed_cases)/$($Summary.total_cases)"
Write-Host "Tool selection: $([int](100 * $Metrics.tool_selection_accuracy.rate))%"
Write-Host "Argument accuracy: $([int](100 * $Metrics.argument_accuracy.rate))%"
Write-Host "Confirmation gates: $($Metrics.confirmation_gate_accuracy.passed)/$($Metrics.confirmation_gate_accuracy.total)"
Write-Host "Default deny: $($Metrics.default_deny_accuracy.passed)/$($Metrics.default_deny_accuracy.total)"
Write-Host "Unexpected policy violations: $($Metrics.unexpected_policy_violations)"
Write-Host "External requests: $($Runtime.external_requests)"
Write-Host "Device tools executed: $($Runtime.device_tools_executed)"
Write-Host "Prompts exposed: $($Report.prompts_in_report)"
Write-Host "Dashboard evaluation assets: ready"
Write-Host "Agent Evaluation Dashboard smoke test passed."
