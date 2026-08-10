param(
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-Utf8JsonPost {
    param([string]$Uri, [hashtable]$Body)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    $Client.Headers["Content-Type"] = "application/json; charset=utf-8"
    $Json = $Body | ConvertTo-Json -Depth 10 -Compress
    return $Utf8.GetString(
        $Client.UploadData($Uri, "POST", $Utf8.GetBytes($Json))
    ) | ConvertFrom-Json
}

function Invoke-Utf8JsonPut {
    param([string]$Uri, [hashtable]$Body)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    $Client.Headers["Content-Type"] = "application/json; charset=utf-8"
    $Json = $Body | ConvertTo-Json -Depth 10 -Compress
    return $Utf8.GetString(
        $Client.UploadData($Uri, "PUT", $Utf8.GetBytes($Json))
    ) | ConvertFrom-Json
}

function Get-Utf8Json {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    $Client.Headers["Accept"] = "application/json"
    return $Utf8.GetString($Client.DownloadData($Uri)) |
        ConvertFrom-Json
}

function Get-Utf8Text {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    return $Utf8.GetString($Client.DownloadData($Uri))
}

Write-Host "Checking confirmed long-term Agent memory at $BaseUrl/dashboard"

$Health = Get-Utf8Json "$BaseUrl/health"
$InitialMode = $Health.agent_model.mode
if ($InitialMode -eq "remote") {
    $null = Invoke-Utf8JsonPut `
        -Uri "$BaseUrl/api/v1/agent/model-mode" `
        -Body @{ mode = "offline"; confirmation = "SWITCH_AGENT_MODEL" }
}

$Suffix = [DateTime]::UtcNow.Ticks
$Key = "acceptance-code-$Suffix"
$Value = "amber-$Suffix"
$MemoryId = $null
try {
    $Pending = Invoke-Utf8JsonPost `
        -Uri "$BaseUrl/api/v1/agent/tasks" `
        -Body @{ message = "remember my $Key is $Value" }
    if (
        $Pending.status -ne "AWAITING_CONFIRMATION" -or
        $Pending.pending_confirmation.tool_name -ne "memory.remember" -or
        $Pending.pending_confirmation.risk -ne "L1" -or
        @($Pending.tool_results).Count -ne 0
    ) {
        throw "The remember task did not stop at the L1 confirmation gate"
    }

    $Confirmed = Invoke-Utf8JsonPost `
        -Uri "$BaseUrl/api/v1/agent/tasks/$($Pending.task_id)/confirm" `
        -Body @{ confirmation = "CONFIRM_TOOL_EXECUTION" }
    $RememberTool = @($Confirmed.tool_results) | Where-Object {
        $_.tool_name -eq "memory.remember"
    } | Select-Object -First 1
    if (
        $Confirmed.status -ne "COMPLETED" -or
        $Confirmed.task_id -ne $Pending.task_id -or
        $RememberTool.status -ne "SUCCEEDED" -or
        $RememberTool.result.value -ne $Value
    ) {
        throw "The confirmed memory write is invalid"
    }
    $MemoryId = $RememberTool.result.memory_id

    $EncodedKey = [Uri]::EscapeDataString($Key)
    $Search = Get-Utf8Json (
        "$BaseUrl/api/v1/agent/memories?query=$EncodedKey&limit=5"
    )
    if (
        $Search.count -ne 1 -or
        $Search.records[0].memory_id -ne $MemoryId -or
        $Search.records[0].provenance.source -ne "user_confirmed" -or
        -not $Search.records[0].provenance.confirmation_required -or
        -not $Search.read_only -or
        $Search.raw_tool_results_stored -or
        $Search.images_stored -or
        $Search.evidence_paths_stored
    ) {
        throw "The persisted long-term memory is invalid"
    }

    $ForgetPending = Invoke-Utf8JsonPost `
        -Uri "$BaseUrl/api/v1/agent/tasks" `
        -Body @{ message = "forget memory $MemoryId" }
    if (
        $ForgetPending.status -ne "AWAITING_CONFIRMATION" -or
        $ForgetPending.pending_confirmation.tool_name -ne "memory.forget" -or
        $ForgetPending.pending_confirmation.risk -ne "L1"
    ) {
        throw "The forget task did not stop at the L1 confirmation gate"
    }
    $Forgotten = Invoke-Utf8JsonPost `
        -Uri "$BaseUrl/api/v1/agent/tasks/$($ForgetPending.task_id)/confirm" `
        -Body @{ confirmation = "CONFIRM_TOOL_EXECUTION" }
    $ForgetTool = @($Forgotten.tool_results) | Where-Object {
        $_.tool_name -eq "memory.forget"
    } | Select-Object -First 1
    if (
        $Forgotten.status -ne "COMPLETED" -or
        $ForgetTool.status -ne "SUCCEEDED" -or
        -not $ForgetTool.result.delete_performed
    ) {
        throw "The confirmed memory deletion is invalid"
    }
    $After = Get-Utf8Json (
        "$BaseUrl/api/v1/agent/memories?query=$EncodedKey&limit=5"
    )
    if ($After.count -ne 0) {
        throw "The deleted memory is still returned"
    }

    $Tools = Get-Utf8Json "$BaseUrl/api/v1/harness/tools"
    $Schemas = @($Tools.tools)
    $McpTools = @($Schemas | Where-Object {
        $_.annotations.riskLevel -eq "L0" -and
        $_.annotations.readOnlyHint
    })
    if (
        $Schemas.Count -ne 33 -or
        $McpTools.Count -ne 25 -or
        "memory.search" -notin @($McpTools.name)
    ) {
        throw "The memory tool catalog is invalid"
    }

    $Html = Get-Utf8Text "$BaseUrl/dashboard"
    $Javascript = Get-Utf8Text "$BaseUrl/dashboard/assets/dashboard.js"
    $Stylesheet = Get-Utf8Text "$BaseUrl/dashboard/assets/dashboard.css"
    if (
        $Html -notmatch 'id="agent-long-term-memory"' -or
        $Html -notmatch 'id="agent-long-term-list"' -or
        $Javascript -notmatch 'refreshLongTermMemory' -or
        $Javascript -notmatch 'memory\.remember' -or
        $Stylesheet -notmatch '\.agent-long-term-memory'
    ) {
        throw "Dashboard long-term memory assets are incomplete"
    }

    Write-Host
    Write-Host "Agent Long-Term Memory Dashboard acceptance summary:"
    Write-Host "Remember task: $($Pending.status)"
    Write-Host "Remember risk: $($Pending.pending_confirmation.risk)"
    Write-Host "Confirmed task: $($Confirmed.status)"
    Write-Host "Memory ID: $MemoryId"
    Write-Host "Kind: $($RememberTool.result.kind)"
    Write-Host "Revision: $($RememberTool.result.revision)"
    Write-Host "Provenance: $($Search.records[0].provenance.source)"
    Write-Host "Forget task: $($Forgotten.status)"
    Write-Host "Delete performed: $($ForgetTool.result.delete_performed)"
    Write-Host "Raw tool results stored: $($Search.raw_tool_results_stored)"
    Write-Host "Images stored: $($Search.images_stored)"
    Write-Host "MCP read-only tools: $($McpTools.Count)"
    Write-Host "Dashboard long-term memory assets: ready"
    Write-Host "Agent Long-Term Memory Dashboard smoke test passed."
}
finally {
    if ($InitialMode -eq "remote") {
        $null = Invoke-Utf8JsonPut `
            -Uri "$BaseUrl/api/v1/agent/model-mode" `
            -Body @{ mode = "online"; confirmation = "SWITCH_AGENT_MODEL" }
    }
}
