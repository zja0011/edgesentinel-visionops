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
        $ResponseBytes = $Client.DownloadData("$BaseUrl$Path")
        $ResponseJson = [System.Text.Encoding]::UTF8.GetString(
            $ResponseBytes
        )
        return $ResponseJson | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

function Invoke-Utf8AgentTask {
    param([string]$Message)

    $Json = @{
        message = $Message
    } | ConvertTo-Json -Compress
    $Body = [System.Text.Encoding]::UTF8.GetBytes($Json)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Content-Type"] = "application/json; charset=utf-8"
        $ResponseBytes = $Client.UploadData(
            "$BaseUrl/api/v1/agent/tasks",
            "POST",
            $Body
        )
        $ResponseJson = [System.Text.Encoding]::UTF8.GetString(
            $ResponseBytes
        )
        return $ResponseJson | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

Write-Host "Checking the DeepSeek Agent API at $BaseUrl"

$Health = Invoke-Utf8JsonGet -Path "/health"
if (
    $Health.status -ne "ok" -or
    $Health.agent_model.mode -ne "remote" -or
    $Health.agent_model.provider -ne "deepseek" -or
    $Health.agent_model.model -ne "deepseek-v4-flash" -or
    $Health.agent_model.external_requests_enabled -ne $true
) {
    $Health | ConvertTo-Json -Depth 8
    throw "The API is not running with the expected DeepSeek model"
}

$Message = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String(
        "6K+36LCD55So5LqL5Lu25p+l6K+i5bel5YW35p+l6K+i5pyA6L+RMuadoeeTtuWtkOS6i+S7tuOAguW3peWFt+WPguaVsOW/hemhu+S9v+eUqOiLseaWhyBvYmplY3RfY2xhc3M9Ym90dGxlIOWSjCBsaW1pdD0y77yM54S25ZCO5qC55o2u55yf5a6e5bel5YW357uT5p6c55So5Lit5paH5Zue562U44CC"
    )
)
$Task = Invoke-Utf8AgentTask -Message $Message
$ToolResults = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $Task.model -ne "chat-completions-compatible" -or
    $Task.steps -lt 2 -or
    $Task.steps -gt 3 -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer) -or
    $ToolResults.Count -lt 1 -or
    $ToolResults.Count -gt 2
) {
    $Task | ConvertTo-Json -Depth 12
    throw "The DeepSeek Agent task did not complete as expected"
}

foreach ($ToolResult in $ToolResults) {
    if (
        $ToolResult.tool_name -ne "event.query" -or
        $ToolResult.status -ne "SUCCEEDED"
    ) {
        $Task | ConvertTo-Json -Depth 12
        throw "An unexpected or failed tool call was returned"
    }
}

$LastTool = $ToolResults[$ToolResults.Count - 1]
if ($LastTool.result.count -ne 2) {
    $Task | ConvertTo-Json -Depth 12
    throw "The final event.query result did not contain two events"
}

$Checkpoint = Invoke-Utf8JsonGet `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
$History = @($Checkpoint.model_history)
$AssistantMessages = @(
    $History | Where-Object { $_.role -eq "assistant" }
)
$ToolMessages = @(
    $History | Where-Object { $_.role -eq "tool" }
)
if (
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.answer -ne $Task.answer -or
    $Checkpoint.model_identity -ne
        "chat-completions-compatible:deepseek-v4-flash" -or
    $History.Count -lt 3 -or
    $History[0].role -ne "user" -or
    $AssistantMessages.Count -ne $ToolResults.Count -or
    $ToolMessages.Count -ne $ToolResults.Count
) {
    $Checkpoint | ConvertTo-Json -Depth 12
    throw "The DeepSeek Agent checkpoint validation failed"
}

Write-Host ""
Write-Host "DeepSeek Agent API acceptance summary:"
Write-Host "Health model: $($Health.agent_model.provider) $($Health.agent_model.model)"
Write-Host "Task: $($Task.status)"
Write-Host "Task ID: $($Task.task_id)"
Write-Host "Steps: $($Task.steps)"
Write-Host "Tool calls: $($ToolResults.Count)"
Write-Host "Final event count: $($LastTool.result.count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "DeepSeek Agent API smoke test passed."
