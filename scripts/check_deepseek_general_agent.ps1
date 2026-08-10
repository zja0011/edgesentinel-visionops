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

Write-Host "Checking a general DeepSeek question at $BaseUrl"

$Health = Invoke-Utf8JsonGet -Path "/health"
if (
    $Health.status -ne "ok" -or
    $Health.agent_model.mode -ne "remote" -or
    $Health.agent_model.provider -ne "deepseek" -or
    $Health.agent_model.external_requests_enabled -ne $true
) {
    throw "The API is not running in remote DeepSeek mode"
}

$Message = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String(
        "5LuK5aSp5piv5pif5pyf5Yeg77yf6K+35qC55o2u5LiK5LiL5paH5Lit55qE5b2T5YmN5YyX5Lqs5pe26Ze077yM5Y+q55So4oCc5LuK5aSp5piv5pif5pyfWOKAneS4gOWPpeS4reaWh+WbnuetlOOAgg=="
    )
)
$Task = Invoke-Utf8AgentTask -Message $Message
$ToolResults = @($Task.tool_results)

$HealthTime = [DateTimeOffset]::Parse(
    [string]$Health.timestamp,
    [System.Globalization.CultureInfo]::InvariantCulture
)
$WeekdayBase64 = @(
    "5pif5pyf5pel",
    "5pif5pyf5LiA",
    "5pif5pyf5LqM",
    "5pif5pyf5LiJ",
    "5pif5pyf5Zub",
    "5pif5pyf5LqU",
    "5pif5pyf5YWt"
)
$ExpectedWeekday = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String(
        $WeekdayBase64[[int]$HealthTime.DayOfWeek]
    )
)

if (
    $Task.status -ne "COMPLETED" -or
    $Task.model -ne "chat-completions-compatible" -or
    $Task.steps -ne 1 -or
    $ToolResults.Count -ne 0 -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer) -or
    -not ([string]$Task.answer).Contains($ExpectedWeekday)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "The general DeepSeek answer is invalid"
}

$Checkpoint = Invoke-Utf8JsonGet `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.model_identity -ne
        "chat-completions-compatible:deepseek-v4-flash" -or
    @($Checkpoint.tool_results).Count -ne 0 -or
    $Checkpoint.answer -ne $Task.answer
) {
    throw "The general-question checkpoint is inconsistent"
}

Write-Host ""
Write-Host "DeepSeek General Question acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Model: $($Health.agent_model.model)"
Write-Host "Expected weekday: $ExpectedWeekday"
Write-Host "Tool calls: $($ToolResults.Count)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "DeepSeek General Question smoke test passed."
