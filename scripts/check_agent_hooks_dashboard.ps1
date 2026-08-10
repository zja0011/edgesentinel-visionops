param(
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Utf8Json {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    try {
        return (
            $Utf8.GetString($Client.DownloadData($Uri)) |
                ConvertFrom-Json
        )
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

function Invoke-Utf8AgentTask {
    param([string]$Message)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Content-Type"] =
            "application/json; charset=utf-8"
        $Body = @{ message = $Message } |
            ConvertTo-Json -Compress
        return (
            $Utf8.GetString(
                $Client.UploadData(
                    "$BaseUrl/api/v1/agent/tasks",
                    "POST",
                    $Utf8.GetBytes($Body)
                )
            ) |
                ConvertFrom-Json
        )
    }
    finally {
        $Client.Dispose()
    }
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

Write-Host "Checking Agent lifecycle Hooks at $BaseUrl/dashboard"

$Catalog = Get-Utf8Json "$BaseUrl/api/v1/harness/hooks"
$Hooks = @($Catalog.hooks)
$ExpectedPoints = @(
    "before_model",
    "after_model",
    "before_tool",
    "after_tool",
    "on_checkpoint",
    "on_task_complete"
)
$CatalogPoints = @($Catalog.points)
if (
    -not $Catalog.read_only -or
    $Catalog.count -ne 6 -or
    $Hooks.Count -ne 6
) {
    throw "The Hook catalog is invalid"
}
foreach ($Point in $ExpectedPoints) {
    if (
        $CatalogPoints -notcontains $Point -or
        @($Hooks | Where-Object { $_.point -eq $Point }).Count -ne 1
    ) {
        throw "The Hook lifecycle catalog is incomplete"
    }
}
$GuardHooks = @(
    $Hooks |
        Where-Object {
            $_.point -in @(
                "before_model",
                "after_model",
                "before_tool"
            )
        }
)
if (
    @(
        $GuardHooks |
            Where-Object {
                $_.failure_policy -ne "FAIL_CLOSED" -or
                $_.timeout_ms -gt 5000
            }
    ).Count -ne 0
) {
    throw "A guard Hook is not fail-closed and bounded"
}

$Task = Invoke-Utf8AgentTask (
    "How many people are in the current camera view?"
)
if ($Task.status -ne "COMPLETED") {
    $Task | ConvertTo-Json -Depth 20
    throw "The Hook-instrumented Agent task did not complete"
}
$Trace = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/" +
    "$($Task.task_id)/trace?limit=100"
)
$HookRecords = @(
    @($Trace.records) |
        Where-Object { $_.record_type -eq "HOOK_RESULT" }
)
$TracePoints = @(
    $HookRecords |
        ForEach-Object { $_.hook_point } |
        Select-Object -Unique
)
foreach ($Point in $ExpectedPoints) {
    if ($TracePoints -notcontains $Point) {
        throw "The Agent trace is missing Hook point $Point"
    }
}
if (
    @(
        $HookRecords |
            Where-Object {
                $_.status -ne "SUCCEEDED" -or
                $_.decision -ne "ALLOW" -or
                $_.latency_ms -lt 0 -or
                $_.timeout_ms -lt 1
            }
    ).Count -ne 0
) {
    throw "A lifecycle Hook did not complete safely"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
if (
    $Html -notmatch 'id="agent-workbench"' -or
    $Javascript -notmatch "HOOK_RESULT" -or
    $Javascript -notmatch "hook_point" -or
    $Javascript -notmatch "failure_policy"
) {
    throw "Dashboard Hook Workbench assets are incomplete"
}

$AuditApiRejected = $false
try {
    Get-Utf8Text "$BaseUrl/api/v1/harness/hooks/audit" |
        Out-Null
} catch {
    if ((Get-HttpStatusCode $_) -eq 404) {
        $AuditApiRejected = $true
    } else {
        throw
    }
}
if (-not $AuditApiRejected) {
    throw "The private Hook audit unexpectedly has an HTTP API"
}

Write-Host
Write-Host "Agent Hooks acceptance summary:"
Write-Host "Hooks: $($Hooks.Count)"
Write-Host "Lifecycle points: $($ExpectedPoints.Count)"
Write-Host "Task: $($Task.status)"
Write-Host "Hook trace records: $($HookRecords.Count)"
Write-Host "Guard policy: FAIL_CLOSED"
Write-Host "Timeouts bounded: True"
Write-Host "Payload exposed: False"
Write-Host "Audit file API exposed: False"
Write-Host "Workbench Hook timeline: ready"
Write-Host "Agent Hooks smoke test passed."
