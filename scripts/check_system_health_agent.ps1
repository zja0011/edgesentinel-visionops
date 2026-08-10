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
    $Json = @{ message = $Message } |
        ConvertTo-Json -Compress
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

Write-Host "Checking read-only Jetson health Agent at $BaseUrl"

$Health = Invoke-Utf8Get -Path "/health"
$Direct = Invoke-Utf8Get -Path "/api/v1/system/status"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"

if ($Health.status -ne "ok" -or $Direct.status -ne "ok") {
    throw "Jetson API or direct device monitor is not healthy"
}
$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "system.get_health"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "system.get_health policy metadata is invalid"
}

$Task = Invoke-Utf8AgentTask `
    -Message "check Jetson system health"
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "system.get_health" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "System health Agent task failed"
}

$Result = $Results[0].result
$AllowedStatuses = @("OK", "WARNING", "CRITICAL", "DEGRADED")
if (
    $Result.status -notin $AllowedStatuses -or
    $Result.read_only -ne $true -or
    $Result.source_status -ne "ok" -or
    $Result.timestamp -notmatch "\+08:00$" -or
    $null -eq $Result.checks.load -or
    $null -eq $Result.checks.memory -or
    $null -eq $Result.checks.disk -or
    $null -eq $Result.checks.temperature -or
    $Result.checks.memory.warning_at -ne 85 -or
    $Result.checks.memory.critical_at -ne 95 -or
    $Result.checks.disk.warning_at -ne 85 -or
    $Result.checks.disk.critical_at -ne 95 -or
    $Result.checks.temperature.warning_at -ne 75 -or
    $Result.checks.temperature.critical_at -ne 85
) {
    $Result | ConvertTo-Json -Depth 12
    throw "System health result contract is invalid"
}

$MemoryDifference = [Math]::Abs(
    [double]$Result.checks.memory.used_percent -
    [double]$Direct.memory.used_percent
)
$DiskDifference = [Math]::Abs(
    [double]$Result.checks.disk.used_percent -
    [double]$Direct.disk.used_percent
)
if ($MemoryDifference -gt 5 -or $DiskDifference -gt 1) {
    throw "Agent health metrics do not match the direct monitor"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "system.get_health"
    ) -or
    $Checkpoint.tool_results[0].result.status -ne (
        $Result.status
    )
) {
    throw "System health checkpoint does not match"
}
if (
    -not $Dashboard.Contains('id="system-health-prompt"') -or
    -not $Dashboard.Contains(
        'data-prompt="Jetson'
    )
) {
    throw "Dashboard system health prompt is missing"
}

$Temperature = $Result.checks.temperature.max_celsius
if ($null -eq $Temperature) {
    $Temperature = "unavailable"
}

Write-Host ""
Write-Host "System Health Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Overall status: $($Result.status)"
Write-Host "Load used: $($Result.checks.load.used_percent)%"
Write-Host "Memory used: $($Result.checks.memory.used_percent)%"
Write-Host "Disk used: $($Result.checks.disk.used_percent)%"
Write-Host "Maximum temperature: $Temperature C"
Write-Host "Issues: $(@($Result.issues).Count)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard health prompt: ready"
Write-Host "System Health Agent smoke test passed."
