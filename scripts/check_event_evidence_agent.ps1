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

function Invoke-Utf8JsonPost {
    param(
        [string]$Path,
        [hashtable]$Payload
    )
    $Json = $Payload | ConvertTo-Json -Compress
    $Body = [System.Text.Encoding]::UTF8.GetBytes($Json)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Content-Type"] = (
            "application/json; charset=utf-8"
        )
        $Bytes = $Client.UploadData(
            "$BaseUrl$Path",
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

function Get-Bytes {
    param([string]$Path)
    $Client = New-Object System.Net.WebClient
    try {
        return $Client.DownloadData("$BaseUrl$Path")
    }
    finally {
        $Client.Dispose()
    }
}

function Get-Sha256 {
    param([byte[]]$Bytes)
    $Algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $Hash = $Algorithm.ComputeHash($Bytes)
        return (
            ($Hash | ForEach-Object {
                $_.ToString("x2")
            }) -join ""
        )
    }
    finally {
        $Algorithm.Dispose()
    }
}

function Assert-SafeExactIntegrity {
    param(
        [object]$Integrity,
        [string]$EventId,
        [string]$Source
    )
    $Evidence = @($Integrity.evidence)
    if (
        $Integrity.status -ne "PASS" -or
        [string]$Integrity.event.event_id -ne $EventId -or
        [int]$Integrity.referenced_evidence_count -lt 1 -or
        [int]$Integrity.valid_evidence_count -ne (
            [int]$Integrity.referenced_evidence_count
        ) -or
        [int]$Integrity.issue_count -ne 0 -or
        $Evidence.Count -ne (
            [int]$Integrity.referenced_evidence_count
        ) -or
        $Evidence.Count -gt 3 -or
        $Integrity.jpeg_signature_checked -ne $true -or
        $Integrity.sha256_checked -ne $true -or
        $Integrity.paths_included -ne $false -or
        $Integrity.absolute_paths_included -ne $false -or
        $Integrity.read_only -ne $true
    ) {
        throw "$Source exact evidence integrity is invalid"
    }
    foreach ($Item in $Evidence) {
        $Names = @($Item.PSObject.Properties.Name)
        if (
            $Item.kind -notin @("primary", "before", "after") -or
            $Item.status -ne "VALID" -or
            [int64]$Item.bytes -lt 4 -or
            [string]$Item.sha256 -notmatch '^[0-9a-f]{64}$' -or
            [string]$Item.url -notmatch (
                '^/api/v1/events/evt_[0-9a-f]{32}/evidence/' +
                '(primary|before|after)$'
            ) -or
            $Names -contains "path" -or
            $Names -contains "evidence_path"
        ) {
            throw "$Source exposed an unsafe evidence record"
        }
    }
}

Write-Host (
    "Checking exact event evidence at " +
    "$BaseUrl"
)

$Recent = Invoke-Utf8JsonGet `
    -Path "/api/v1/events?limit=50"
$Selected = @(
    $Recent.events | Where-Object {
        $Urls = $_.evidence_urls
        $null -ne $Urls -and
        @($Urls.PSObject.Properties).Count -gt 0
    } | Select-Object -First 1
)
if ($Selected.Count -ne 1) {
    throw "No recent event with evidence is available"
}
$EventId = [string]$Selected[0].event_id
$Before = Invoke-Utf8JsonGet `
    -Path "/api/v1/events/$EventId"

$Direct = Invoke-Utf8JsonGet `
    -Path "/api/v1/events/$EventId/evidence-integrity"
Assert-SafeExactIntegrity `
    -Integrity $Direct `
    -EventId $EventId `
    -Source "Direct API"

$FirstEvidence = @($Direct.evidence)[0]
$ImageBytes = Get-Bytes -Path $FirstEvidence.url
if (
    $ImageBytes.Length -ne [int64]$FirstEvidence.bytes -or
    $ImageBytes.Length -lt 4 -or
    $ImageBytes[0] -ne 0xff -or
    $ImageBytes[1] -ne 0xd8 -or
    $ImageBytes[$ImageBytes.Length - 2] -ne 0xff -or
    $ImageBytes[$ImageBytes.Length - 1] -ne 0xd9
) {
    throw "Downloaded evidence is not the verified JPEG"
}
$DownloadedSha256 = Get-Sha256 -Bytes $ImageBytes
if ($DownloadedSha256 -ne [string]$FirstEvidence.sha256) {
    throw "Downloaded evidence SHA-256 does not match"
}

$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$Tool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "evidence.verify_event"
    }
)
if (
    $Tool.Count -ne 1 -or
    $Tool[0].annotations.readOnlyHint -ne $true -or
    $Tool[0].annotations.riskLevel -ne "L0" -or
    $Tool[0].annotations.autoExecute -ne $true -or
    $Tool[0].annotations.requiresConfirmation -ne $false -or
    $Tool[0].inputSchema.required -notcontains "event_id"
) {
    throw "Exact evidence tool policy is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/harness/tools/" +
        "evidence.verify_event/invoke"
    ) `
    -Payload @{ event_id = $EventId }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "evidence.verify_event"
) {
    throw "Harness exact evidence query failed"
}
Assert-SafeExactIntegrity `
    -Integrity $Harness.result `
    -EventId $EventId `
    -Source "Harness"

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = (
            "Check evidence integrity for event " +
            $EventId
        )
    }
$Results = @($Task.tool_results)
$WriteCalls = @(
    $Results | Where-Object {
        $_.tool_name -in @(
            "system.cleanup_retained_data",
            "camera.restart",
            "camera.capture_snapshot",
            "report.generate",
            "event.acknowledge"
        )
    }
)
if (
    $Task.status -ne "COMPLETED" -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "evidence.verify_event" -or
    $Results[0].status -ne "SUCCEEDED" -or
    $WriteCalls.Count -ne 0 -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent exact evidence query failed"
}
Assert-SafeExactIntegrity `
    -Integrity $Results[0].result `
    -EventId $EventId `
    -Source "Agent"

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $null -ne $Checkpoint.pending_confirmation
) {
    throw "Exact evidence checkpoint is inconsistent"
}

$After = Invoke-Utf8JsonGet `
    -Path "/api/v1/events/$EventId"
if (
    [string]$After.status -ne [string]$Before.status -or
    [string]$After.acknowledged_at -ne (
        [string]$Before.acknowledged_at
    )
) {
    throw "Read-only evidence query changed event disposition"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="event-evidence-integrity"' -or
    $Javascript -notmatch '/evidence-integrity' -or
    $Javascript -notmatch 'renderEventEvidenceIntegrity'
) {
    throw "Dashboard exact evidence assets are incomplete"
}

$McpTools = @(
    $Tools.tools | Where-Object {
        $_.annotations.readOnlyHint -eq $true -and
        $_.annotations.riskLevel -eq "L0" -and
        $_.annotations.autoExecute -eq $true -and
        $_.annotations.requiresConfirmation -eq $false
    }
)
if ($McpTools.Count -ne 25) {
    throw "MCP read-only tool count is not 25"
}

Write-Host ""
Write-Host "Exact Event Evidence acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($Tool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $Tool[0].annotations.requiresConfirmation
)
Write-Host "Event ID: $EventId"
Write-Host "Event type: $($Direct.event.event_type)"
Write-Host "Object class: $($Direct.event.object_class)"
Write-Host "Status: $($Direct.status)"
Write-Host (
    "Evidence references: " +
    $Direct.referenced_evidence_count
)
foreach ($Item in @($Direct.evidence)) {
    Write-Host (
        "Evidence $($Item.kind): $($Item.status) " +
        "$($Item.bytes) bytes SHA-256 " +
        "$($Item.sha256.Substring(0, 16))..."
    )
}
Write-Host "Downloaded JPEG bytes: $($ImageBytes.Length)"
Write-Host "Downloaded SHA-256 match: True"
Write-Host "Paths exposed: $($Direct.paths_included)"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Event disposition unchanged: True"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard event evidence status: ready"
Write-Host "Exact Event Evidence smoke test passed."
