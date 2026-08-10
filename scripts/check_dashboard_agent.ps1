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
        $Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
        return $Text | ConvertFrom-Json
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
        $Client.Headers["Content-Type"] = "application/json; charset=utf-8"
        $Bytes = $Client.UploadData(
            "$BaseUrl/api/v1/agent/tasks",
            "POST",
            $Body
        )
        $Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
        return $Text | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

Write-Host "Checking Dashboard Agent chat at $BaseUrl/dashboard"

$Health = Invoke-Utf8JsonGet -Path "/health"
if (
    $Health.status -ne "ok" -or
    $Health.agent_model.mode -ne "offline"
) {
    throw "Start the API in offline mode with scripts/run_api_server.sh"
}

$Message = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String(
        "5p+l6K+i5pyA6L+R55qE55O25a2Q5LqL5Lu2"
    )
)
$Task = Invoke-Utf8AgentTask -Message $Message
$Tools = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $Task.model -ne "offline-rule-mock" -or
    $Tools.Count -ne 1 -or
    $Tools[0].tool_name -ne "event.query" -or
    $Tools[0].status -ne "SUCCEEDED" -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Dashboard Agent task failed"
}

$Checkpoint = Invoke-Utf8JsonGet `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.answer -ne $Task.answer
) {
    throw "Dashboard Agent checkpoint validation failed"
}

Write-Host ""
Write-Host "Dashboard Agent acceptance summary:"
Write-Host "Model: $($Task.model)"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Tools[0].tool_name) $($Tools[0].status)"
Write-Host "Event count: $($Tools[0].result.count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard Agent chat smoke test passed."
