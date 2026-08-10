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

function Get-HttpStatusCode {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)
    $Exception = $ErrorRecord.Exception
    while ($null -ne $Exception) {
        if ($null -ne $Exception.Response) {
            return [int]$Exception.Response.StatusCode
        }
        $Exception = $Exception.InnerException
    }
    return $null
}

Write-Host "Checking the Agent Harness Workbench at $BaseUrl/dashboard"

$Task = Invoke-Utf8JsonPost `
    -Uri "$BaseUrl/api/v1/agent/tasks" `
    -Body @{ message = "How many people are in the current camera view?" }
if (
    $Task.status -ne "COMPLETED" -or
    [string]::IsNullOrWhiteSpace($Task.task_id)
) {
    throw "The read-only Agent task did not complete"
}

$Trace = (
    Get-Utf8Text (
        "$BaseUrl/api/v1/agent/tasks/" +
        "$($Task.task_id)/trace?limit=100"
    ) |
        ConvertFrom-Json
)
$Records = @($Trace.records)
if (
    $Trace.task_id -ne $Task.task_id -or
    -not $Trace.read_only -or
    $Trace.model_content_exposed -or
    $Trace.raw_trace_exposed -or
    $Records.Count -lt 3
) {
    throw "The bounded Agent trace response is invalid"
}
$RecordTypes = @($Records | ForEach-Object { $_.record_type })
if (
    $RecordTypes -notcontains "MODEL_DECISION" -or
    $RecordTypes -notcontains "TOOL_RESULT" -or
    $RecordTypes -notcontains "TASK_RESULT"
) {
    throw "The Agent lifecycle trace is incomplete"
}
$ToolRecord = @(
    $Records |
        Where-Object { $_.record_type -eq "TOOL_RESULT" }
)[-1]
if (
    $ToolRecord.tool_name -ne "vision.get_people_count" -or
    $ToolRecord.status -ne "SUCCEEDED" -or
    $ToolRecord.tool_policy.riskLevel -ne "L0"
) {
    throw "The traced tool result or policy is invalid"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
$Stylesheet = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.css"
)
if (
    $Html -notmatch 'id="agent-workbench"' -or
    $Html -notmatch 'id="agent-run-timeline"' -or
    $Javascript -notmatch "renderAgentWorkbench" -or
    $Javascript -notmatch "appendTraceRecord" -or
    $Stylesheet -notmatch "\.agent-run-timeline"
) {
    throw "Dashboard Harness Workbench assets are incomplete"
}

$UnknownTraceRejected = $false
try {
    Get-Utf8Text (
        "$BaseUrl/api/v1/agent/tasks/" +
        "task_00000000000000000000000000000000/trace"
    ) | Out-Null
} catch {
    if ((Get-HttpStatusCode $_) -eq 404) {
        $UnknownTraceRejected = $true
    } else {
        throw
    }
}
if (-not $UnknownTraceRejected) {
    throw "An unknown task trace was not rejected"
}

Write-Host
Write-Host "Agent Harness Workbench acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Task ID: $($Task.task_id)"
Write-Host "Model: $($Task.model)"
Write-Host "Steps: $($Task.steps)"
Write-Host "Trace records: $($Records.Count)"
Write-Host "Lifecycle: MODEL_DECISION -> TOOL_RESULT -> TASK_RESULT"
Write-Host "Tool: $($ToolRecord.tool_name) $($ToolRecord.status)"
Write-Host "Policy: $($ToolRecord.tool_policy.riskLevel)"
Write-Host "Model content exposed: False"
Write-Host "Raw trace exposed: False"
Write-Host "Unknown task trace: HTTP 404"
Write-Host "Workbench assets: ready"
Write-Host "Agent Harness Workbench smoke test passed."
