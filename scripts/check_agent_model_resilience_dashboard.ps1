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

Write-Host (
    "Checking Agent model resilience at $BaseUrl/dashboard"
)

$Before = Get-Utf8Json "$BaseUrl/health"
$BeforeModel = $Before.agent_model
$BeforeResilience = $BeforeModel.resilience
if (
    $Before.status -ne "ok" -or
    $BeforeModel.mode -ne "remote" -or
    $BeforeModel.provider -ne "deepseek" -or
    -not $BeforeResilience.enabled -or
    $BeforeResilience.retry_max_attempts -ne 2 -or
    $BeforeResilience.failure_threshold -ne 3 -or
    $BeforeResilience.cooldown_seconds -ne 60 -or
    -not $BeforeResilience.offline_fallback_enabled
) {
    $Before | ConvertTo-Json -Depth 12
    throw "The model resilience runtime is not configured safely"
}

$Task = Invoke-Utf8JsonPost `
    "$BaseUrl/api/v1/agent/tasks" `
    @{ message = "What weekday is it today? Answer briefly." }
if (
    $Task.status -ne "COMPLETED" -or
    $Task.tool_route.mode -ne "NO_MATCH" -or
    $Task.tool_route.selected_count -ne 0
) {
    $Task | ConvertTo-Json -Depth 12
    throw "The bounded resilience probe task is invalid"
}

$Runtime = $Task.model_resilience
if (
    $null -eq $Runtime -or
    $Runtime.model_calls -lt 1 -or
    $Runtime.remote_attempts -lt $Runtime.model_calls -or
    $Runtime.retry_count -lt 0 -or
    $Runtime.last_requested_mode -ne "remote" -or
    $Runtime.last_served_mode -ne "remote" -or
    $Runtime.fallback_count -ne 0 -or
    $Runtime.circuit_state -ne "CLOSED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "The successful remote model path is invalid"
}

$Checkpoint = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.model_resilience.model_calls -ne
        $Runtime.model_calls -or
    $Checkpoint.model_resilience.remote_attempts -ne
        $Runtime.remote_attempts -or
    $Checkpoint.model_resilience.circuit_state -ne
        $Runtime.circuit_state
) {
    throw "Checkpoint did not retain model resilience metadata"
}

$Trace = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/$($Task.task_id)/trace?limit=100"
)
$Records = @(
    $Trace.records |
        Where-Object { $_.record_type -eq "MODEL_RESILIENCE" }
)
if (
    $Records.Count -ne $Runtime.model_calls -or
    @($Records | Where-Object {
        $_.requested_mode -ne "remote" -or
        $_.served_mode -ne "remote" -or
        $_.circuit_state -ne "CLOSED"
    }).Count -ne 0 -or
    $Trace.model_content_exposed -or
    $Trace.raw_trace_exposed
) {
    throw "The sanitized MODEL_RESILIENCE trace is invalid"
}

$After = Get-Utf8Json "$BaseUrl/health"
$AfterResilience = $After.agent_model.resilience
if (
    $AfterResilience.remote_requests -lt
        ($BeforeResilience.remote_requests + 1) -or
    $AfterResilience.remote_successes -lt
        ($BeforeResilience.remote_successes + 1) -or
    $AfterResilience.circuit_state -ne "CLOSED"
) {
    throw "Provider health counters did not advance safely"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
foreach ($Needle in @(
    'id="agent-model-resilience"',
    'id="agent-run-model-resilience"'
)) {
    if ($Html -notmatch [regex]::Escape($Needle)) {
        throw "Dashboard resilience metadata is incomplete: $Needle"
    }
}
foreach ($Needle in @(
    "MODEL_RESILIENCE",
    "fallback_reason",
    "circuit_state",
    "agentRunModelResilience"
)) {
    if ($Javascript -notmatch [regex]::Escape($Needle)) {
        throw "Dashboard resilience assets are incomplete: $Needle"
    }
}

Write-Host
Write-Host "Agent Model Resilience Dashboard acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Model: $($Task.model)"
Write-Host "Requested mode: $($Runtime.last_requested_mode)"
Write-Host "Served mode: $($Runtime.last_served_mode)"
Write-Host "Model calls: $($Runtime.model_calls)"
Write-Host "Remote attempts: $($Runtime.remote_attempts)"
Write-Host "Retries: $($Runtime.retry_count)"
Write-Host "Fallbacks: $($Runtime.fallback_count)"
Write-Host "Circuit: $($AfterResilience.circuit_state)"
Write-Host "Failure threshold: $($AfterResilience.failure_threshold)"
Write-Host "Cooldown seconds: $($AfterResilience.cooldown_seconds)"
Write-Host "Offline fallback enabled: True"
Write-Host "Checkpoint resilience retained: True"
Write-Host "MODEL_RESILIENCE trace records: $($Records.Count)"
Write-Host "Model content exposed: False"
Write-Host "Dashboard resilience assets: ready"
Write-Host "Agent Model Resilience Dashboard smoke test passed."
