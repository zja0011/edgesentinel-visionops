param(
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Utf8Json {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Accept"] = "application/json"
        return $Utf8.GetString($Client.DownloadData($Uri)) |
            ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

function Get-Utf8Text {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    try {
        return $Utf8.GetString($Client.DownloadData($Uri))
    }
    finally {
        $Client.Dispose()
    }
}

function Invoke-Utf8JsonPost {
    param([string]$Uri, [hashtable]$Body)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Accept"] = "application/json"
        $Client.Headers["Content-Type"] =
            "application/json; charset=utf-8"
        $Json = $Body | ConvertTo-Json -Depth 10 -Compress
        return $Utf8.GetString(
            $Client.UploadData(
                $Uri,
                "POST",
                $Utf8.GetBytes($Json)
            )
        ) | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

Write-Host "Checking Agent token governance at $BaseUrl/dashboard"

$Health = Get-Utf8Json "$BaseUrl/health"
if (
    $Health.status -ne "ok" -or
    $Health.agent_model.mode -ne "remote" -or
    $Health.agent_model.provider -ne "deepseek"
) {
    throw "The API is not running in remote DeepSeek mode"
}

$Task = Invoke-Utf8JsonPost `
    "$BaseUrl/api/v1/agent/tasks" `
    @{ message = "How many people are currently in the camera view?" }
$Execution = $Task.execution
$Limits = $Execution.limits
$Usage = $Execution.usage
$Cost = $Execution.cost_estimate
$Errors = @()
if ($Task.status -ne "COMPLETED") {
    $Errors += "status=$($Task.status)"
}
if ($Limits.max_total_tokens -ne 16384) {
    $Errors += "max_total_tokens=$($Limits.max_total_tokens)"
}
if (
    $Usage.model_calls -lt 1 -or
    $Usage.model_usage_reports -ne $Usage.model_calls -or
    $Usage.model_usage_missing -ne 0 -or
    $Usage.prompt_tokens -le 0 -or
    $Usage.completion_tokens -le 0 -or
    $Usage.total_tokens -lt (
        $Usage.prompt_tokens + $Usage.completion_tokens
    ) -or
    $Usage.total_tokens -gt $Limits.max_total_tokens
) {
    $Errors += "provider_usage=invalid"
}
if ($null -eq $Cost -or $Cost.currency -ne "USD") {
    $Errors += "cost_estimate=missing"
}
elseif ($Cost.available) {
    if (
        [string]::IsNullOrWhiteSpace($Cost.rate_card_id) -or
        $Cost.estimated_cost_usd -lt 0 -or
        $Cost.max_estimated_cost_usd -le 0
    ) {
        $Errors += "configured_cost=invalid"
    }
}
elseif (
    $null -ne $Cost.rate_card_id -or
    $null -ne $Cost.estimated_cost_usd
) {
    $Errors += "unconfigured_cost_was_fabricated"
}
if ($Errors.Count -gt 0) {
    $Task | ConvertTo-Json -Depth 12
    throw (
        "The Agent token governance result is invalid: " +
        ($Errors -join ", ")
    )
}

$Checkpoint = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.execution.usage.total_tokens -ne
        $Usage.total_tokens -or
    $Checkpoint.execution.usage.model_usage_reports -ne
        $Usage.model_usage_reports
) {
    throw "The terminal checkpoint did not retain model usage"
}

$Trace = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/$($Task.task_id)/trace?limit=100"
)
$UsageRecords = @(
    $Trace.records |
        Where-Object { $_.record_type -eq "MODEL_USAGE" }
)
if (
    $UsageRecords.Count -ne $Usage.model_calls -or
    @($UsageRecords | Where-Object {
        -not $_.usage_reported -or
        $_.total_tokens -le 0 -or
        $_.cumulative_total_tokens -le 0
    }).Count -ne 0 -or
    $Trace.model_content_exposed -or
    $Trace.raw_trace_exposed
) {
    throw "The sanitized MODEL_USAGE trace is invalid"
}

$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
$AssetErrors = @()
foreach ($Needle in @(
    "MODEL_USAGE",
    "max_total_tokens",
    "total_tokens",
    "estimated_cost_usd",
    "cost n/a"
)) {
    if ($Javascript -notmatch [regex]::Escape($Needle)) {
        $AssetErrors += $Needle
    }
}
if ($AssetErrors.Count -gt 0) {
    throw (
        "Dashboard token-governance assets are incomplete: " +
        ($AssetErrors -join ", ")
    )
}

$CostStatus = if ($Cost.available) {
    "$($Cost.estimated_cost_usd) USD ($($Cost.rate_card_id))"
}
else {
    "unavailable (rate card not configured)"
}

Write-Host
Write-Host "Agent Token Governance Dashboard acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Model: $($Task.model)"
Write-Host "Model calls: $($Usage.model_calls)"
Write-Host "Usage reports: $($Usage.model_usage_reports)"
Write-Host "Prompt tokens: $($Usage.prompt_tokens)"
Write-Host "Completion tokens: $($Usage.completion_tokens)"
Write-Host "Total tokens: $($Usage.total_tokens)/$($Limits.max_total_tokens)"
Write-Host "Estimated cost: $CostStatus"
Write-Host "Checkpoint usage retained: True"
Write-Host "MODEL_USAGE trace records: $($UsageRecords.Count)"
Write-Host "Model content exposed: False"
Write-Host "Dashboard token assets: ready"
Write-Host "Agent Token Governance Dashboard smoke test passed."
