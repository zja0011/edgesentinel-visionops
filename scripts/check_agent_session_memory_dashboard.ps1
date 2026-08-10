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
    $Json = $Body | ConvertTo-Json -Depth 12 -Compress
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

function Get-Utf8Json {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    return (
        $Utf8.GetString($Client.DownloadData($Uri)) |
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

Write-Host "Checking bounded Agent session memory at $BaseUrl/dashboard"

$CreatedSessionId = $null
$SessionCleared = $false
try {
$Created = Invoke-Utf8JsonPost `
    -Uri "$BaseUrl/api/v1/agent/sessions" `
    -Body @{}
if ($Created.session_id -notmatch '^sess_[0-9a-f]{32}$') {
    throw "The explicit Agent session was not created"
}
$CreatedSessionId = $Created.session_id

$First = Invoke-Utf8JsonPost `
    -Uri "$BaseUrl/api/v1/agent/tasks" `
    -Body @{
        message = (
            "For this conversation, remember the code word cobalt. " +
            "Reply briefly and do not call a tool."
        )
        session_id = $Created.session_id
    }
if (
    $First.status -ne "COMPLETED" -or
    $First.session_id -notmatch '^sess_[0-9a-f]{32}$' -or
    [int]$First.memory.turn_count -ne 1
) {
    throw "The first session-memory task is invalid"
}

$Second = Invoke-Utf8JsonPost `
    -Uri "$BaseUrl/api/v1/agent/tasks" `
    -Body @{
        message = (
            "What code word did I ask you to remember in the " +
            "previous turn? Reply with only that word."
        )
        session_id = $First.session_id
    }
if (
    $Second.status -ne "COMPLETED" -or
    $Second.session_id -ne $First.session_id -or
    [int]$Second.memory.turn_count -ne 2 -or
    $Second.answer -notmatch '(?i)cobalt'
) {
    throw "The follow-up task did not use the bounded session"
}

$Session = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/sessions/$($First.session_id)"
)
$Turns = @($Session.turns)
$TurnJson = $Turns | ConvertTo-Json -Depth 12 -Compress
if (
    $Session.turn_count -ne 2 -or
    $Turns.Count -ne 2 -or
    $Session.max_turns -ne 12 -or
    $Session.retention_days -ne 7 -or
    -not $Session.persistent_across_restart -or
    $Session.raw_tool_results_stored -or
    $Session.images_stored -or
    $Session.evidence_paths_stored -or
    $TurnJson -match '(?i)evidence_path|api[_-]?key|authorization'
) {
    throw "The persisted session has invalid bounds or privacy metadata"
}

$Trace = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/$($Second.task_id)/trace?limit=100"
)
$Checkpoint = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/$($Second.task_id)"
)
$CheckpointHistory = @($Checkpoint.model_history)
if (
    $CheckpointHistory.Count -ne 1 -or
    $CheckpointHistory[0].task_id -ne $Second.task_id
) {
    throw "The terminal checkpoint retained prior session turns"
}
$MemoryTrace = @(
    $Trace.records |
        Where-Object { $_.record_type -eq "SESSION_MEMORY" }
)
if (
    $MemoryTrace.Count -ne 1 -or
    $MemoryTrace[0].memory_action -ne "SAVED" -or
    [int]$MemoryTrace[0].prior_turn_count -ne 1 -or
    [int]$MemoryTrace[0].turn_count -ne 2
) {
    throw "The session memory trace is missing or inconsistent"
}

$InvalidClearRejected = $false
try {
    Invoke-Utf8JsonPost `
        -Uri (
            "$BaseUrl/api/v1/agent/sessions/" +
            "$($First.session_id)/clear"
        ) `
        -Body @{ confirmation = "yes" } | Out-Null
} catch {
    if ((Get-HttpStatusCode $_) -eq 422) {
        $InvalidClearRejected = $true
    } else {
        throw
    }
}
if (-not $InvalidClearRejected) {
    throw "Session clear accepted an invalid confirmation phrase"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
$Stylesheet = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.css"
)
if (
    $Html -notmatch 'id="agent-session-memory"' -or
    $Html -notmatch 'id="agent-session-clear"' -or
    $Javascript -notmatch 'window\.sessionStorage' -or
    $Javascript -notmatch 'CLEAR_AGENT_SESSION' -or
    $Javascript -notmatch 'SESSION_MEMORY' -or
    $Stylesheet -notmatch '\.agent-session-memory'
) {
    throw "Dashboard session-memory assets are incomplete"
}

$Cleared = Invoke-Utf8JsonPost `
    -Uri (
        "$BaseUrl/api/v1/agent/sessions/" +
        "$($First.session_id)/clear"
    ) `
    -Body @{ confirmation = "CLEAR_AGENT_SESSION" }
$AfterClear = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/sessions/$($First.session_id)"
)
if (
    $Cleared.status -ne "CLEARED" -or
    [int]$Cleared.cleared_turns -ne 2 -or
    [int]$AfterClear.turn_count -ne 0
) {
    throw "The confirmed session clear did not remove both turns"
}
$SessionCleared = $true

Write-Host
Write-Host "Agent Session Memory acceptance summary:"
Write-Host "First task: $($First.status)"
Write-Host "Follow-up task: $($Second.status)"
Write-Host "Same session ID: True"
Write-Host "Remembered code word: cobalt"
Write-Host "Turns before clear: $($Session.turn_count)/$($Session.max_turns)"
Write-Host "Retention days: $($Session.retention_days)"
Write-Host "Persistent across restart: $($Session.persistent_across_restart)"
Write-Host "Raw tool results stored: $($Session.raw_tool_results_stored)"
Write-Host "Images stored: $($Session.images_stored)"
Write-Host "Evidence paths stored: $($Session.evidence_paths_stored)"
Write-Host "Trace: SESSION_MEMORY SAVED"
Write-Host "Terminal checkpoint history: 1 current-task record"
Write-Host "Invalid clear phrase: HTTP 422"
Write-Host "Turns after clear: $($AfterClear.turn_count)"
Write-Host "Dashboard session assets: ready"
Write-Host "Agent Session Memory smoke test passed."
} finally {
    if ($null -ne $CreatedSessionId -and -not $SessionCleared) {
        try {
            Invoke-Utf8JsonPost `
                -Uri (
                    "$BaseUrl/api/v1/agent/sessions/" +
                    "$CreatedSessionId/clear"
                ) `
                -Body @{
                    confirmation = "CLEAR_AGENT_SESSION"
                } | Out-Null
        } catch {
            Write-Warning (
                "Could not clean up test session " +
                "$CreatedSessionId"
            )
        }
    }
}
