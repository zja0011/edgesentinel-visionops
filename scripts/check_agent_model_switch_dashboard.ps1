param(
    [string]$BaseUrl = "http://192.168.1.101:8000"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Invoke-JsonRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Body
    )
    if ($Method -eq "GET") {
        return Invoke-RestMethod -Uri $Uri -Method Get
    }
    $Json = $Body | ConvertTo-Json -Depth 10 -Compress
    return Invoke-RestMethod `
        -Uri $Uri `
        -Method $Method `
        -ContentType "application/json; charset=utf-8" `
        -Body $Utf8.GetBytes($Json)
}

function Set-AgentMode {
    param([string]$Mode)
    return Invoke-JsonRequest `
        -Method Put `
        -Uri "$BaseUrl/api/v1/agent/model-mode" `
        -Body @{
            mode = $Mode
            confirmation = "SWITCH_AGENT_MODEL"
        }
}

Write-Host "Checking Dashboard online/offline Agent switching at $BaseUrl"
$Initial = Invoke-JsonRequest `
    -Method Get `
    -Uri "$BaseUrl/api/v1/agent/model-mode"
$InitialMode = $Initial.mode

if (-not $Initial.runtime_switchable) {
    throw "Agent runtime is not switchable"
}
if ($Initial.available_modes -notcontains "remote") {
    throw "Persistent DeepSeek runtime is unavailable"
}

$InvalidRejected = $false
try {
    Invoke-JsonRequest `
        -Method Put `
        -Uri "$BaseUrl/api/v1/agent/model-mode" `
        -Body @{ mode = "offline"; confirmation = "yes" } |
        Out-Null
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 422) {
        $InvalidRejected = $true
    } else {
        throw
    }
}
if (-not $InvalidRejected) {
    throw "Invalid switch confirmation was not rejected"
}

try {
    $Offline = Set-AgentMode -Mode "offline"
    if ($Offline.mode -ne "offline") {
        throw "Offline mode was not selected"
    }
    $Task = Invoke-JsonRequest `
        -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks" `
        -Body @{ message = "how many people are standing in the camera view?" }
    $Tool = @($Task.tool_results)[-1]
    if (
        $Task.status -ne "COMPLETED" -or
        $Task.model -ne "offline-rule-mock" -or
        $Tool.tool_name -ne "vision.get_people_count" -or
        $Tool.status -ne "SUCCEEDED"
    ) {
        throw "Offline paraphrased people query failed"
    }

    $Online = Set-AgentMode -Mode "online"
    if (
        $Online.mode -ne "remote" -or
        $Online.provider -ne "deepseek"
    ) {
        throw "Online DeepSeek mode was not selected"
    }

    $WebClient = New-Object System.Net.WebClient
    $WebClient.Encoding = [System.Text.Encoding]::UTF8
    $Html = $WebClient.DownloadString("$BaseUrl/dashboard")
    $Javascript = $WebClient.DownloadString(
        "$BaseUrl/dashboard/assets/dashboard.js"
    )
    if (
        $Html -notmatch 'id="agent-mode-online"' -or
        $Html -notmatch 'id="agent-mode-offline"' -or
        $Javascript -notmatch "SWITCH_AGENT_MODEL"
    ) {
        throw "Dashboard model-switch assets are incomplete"
    }

    Write-Host
    Write-Host "Agent Model Switch acceptance summary:"
    Write-Host "Initial mode: $InitialMode"
    Write-Host "Invalid confirmation: HTTP 422"
    Write-Host "Offline mode: $($Offline.mode)"
    Write-Host "Offline paraphrase tool: $($Tool.tool_name) $($Tool.status)"
    Write-Host "Online mode: $($Online.mode)"
    Write-Host "Online provider: $($Online.provider)"
    Write-Host "Restart default: $($Online.boot_mode)"
    Write-Host "Dashboard switch assets: ready"
    Write-Host "Agent Model Switch smoke test passed."
} finally {
    if ($InitialMode -eq "offline") {
        Set-AgentMode -Mode "offline" | Out-Null
    } else {
        Set-AgentMode -Mode "online" | Out-Null
    }
}
