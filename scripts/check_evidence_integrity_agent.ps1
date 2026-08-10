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

function Assert-SafeIntegrity {
    param(
        [object]$Integrity,
        [string]$Source
    )
    $References = [int]$Integrity.referenced_evidence_count
    $Valid = [int]$Integrity.valid_evidence_count
    $IssueCount = [int]$Integrity.issue_count
    $Issues = @($Integrity.issues)
    if (
        $Integrity.status -notin @("PASS", "WARN") -or
        [int]$Integrity.checked_event_count -lt 0 -or
        [int]$Integrity.checked_event_count -gt 50 -or
        $References -lt 0 -or
        $Valid -lt 0 -or
        $IssueCount -lt 0 -or
        $References -ne ($Valid + $IssueCount) -or
        [int]$Integrity.unique_valid_file_count -gt $Valid -or
        $Issues.Count -gt 20 -or
        $Integrity.jpeg_signature_checked -ne $true -or
        $Integrity.paths_included -ne $false -or
        $Integrity.absolute_paths_included -ne $false -or
        $Integrity.read_only -ne $true
    ) {
        throw "$Source evidence integrity result is invalid"
    }
    if (
        $Integrity.status -eq "PASS" -and
        $IssueCount -ne 0
    ) {
        throw "$Source PASS result contains issues"
    }
    if (
        $Integrity.status -eq "WARN" -and
        $IssueCount -eq 0
    ) {
        throw "$Source WARN result contains no issues"
    }
    foreach ($Issue in $Issues) {
        $Names = @($Issue.PSObject.Properties.Name)
        if (
            $Names -contains "path" -or
            $Names -contains "evidence_path" -or
            [string]$Issue.event_id -notmatch (
                '^evt_[0-9a-f]{32}$'
            ) -or
            $Issue.evidence_kind -notin @(
                "primary",
                "before",
                "after"
            ) -or
            $Issue.code -notin @(
                "UNSAFE_PATH",
                "MISSING_FILE",
                "UNSUPPORTED_TYPE",
                "INVALID_JPEG",
                "UNREADABLE_FILE"
            )
        ) {
            throw "$Source exposed an unsafe issue record"
        }
    }
}

Write-Host (
    "Checking recent event evidence integrity at " +
    "$BaseUrl"
)

$Direct = Invoke-Utf8JsonGet `
    -Path "/api/v1/events/evidence-integrity?limit=50"
Assert-SafeIntegrity -Integrity $Direct -Source "Direct API"

$Tools = Invoke-Utf8JsonGet -Path "/api/v1/harness/tools"
$Tool = @(
    $Tools.tools | Where-Object {
        $_.name -eq "evidence.verify_recent"
    }
)
if (
    $Tool.Count -ne 1 -or
    $Tool[0].annotations.readOnlyHint -ne $true -or
    $Tool[0].annotations.riskLevel -ne "L0" -or
    $Tool[0].annotations.autoExecute -ne $true -or
    $Tool[0].annotations.requiresConfirmation -ne $false -or
    [int]$Tool[0].inputSchema.properties.limit.maximum -ne 100 -or
    [int]$Tool[0].inputSchema.properties.minutes.maximum -ne 1440
) {
    throw "Evidence integrity tool policy is invalid"
}

$Harness = Invoke-Utf8JsonPost `
    -Path (
        "/api/v1/harness/tools/" +
        "evidence.verify_recent/invoke"
    ) `
    -Payload @{ limit = 50 }
if (
    $Harness.status -ne "SUCCEEDED" -or
    $Harness.tool_name -ne "evidence.verify_recent"
) {
    throw "Harness evidence integrity query failed"
}
Assert-SafeIntegrity `
    -Integrity $Harness.result `
    -Source "Harness"

$Task = Invoke-Utf8JsonPost `
    -Path "/api/v1/agent/tasks" `
    -Payload @{
        message = "Check recent event evidence integrity"
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
    $Results[0].tool_name -ne "evidence.verify_recent" -or
    $Results[0].status -ne "SUCCEEDED" -or
    $WriteCalls.Count -ne 0 -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer)
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Agent evidence integrity query failed"
}
Assert-SafeIntegrity `
    -Integrity $Results[0].result `
    -Source "Agent"

$Checkpoint = Invoke-Utf8JsonGet -Path (
    "/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $null -ne $Checkpoint.pending_confirmation
) {
    throw "Evidence integrity checkpoint is inconsistent"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    $Dashboard -notmatch 'id="evidence-integrity-status"' -or
    $Dashboard -notmatch 'id="evidence-integrity-prompt"' -or
    $Javascript -notmatch (
        '/api/v1/events/evidence-integrity'
    ) -or
    $Javascript -notmatch 'renderEvidenceIntegrity'
) {
    throw "Dashboard evidence integrity assets are incomplete"
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
Write-Host "Evidence Integrity Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($Tool[0].annotations.riskLevel)"
Write-Host (
    "Confirmation required: " +
    $Tool[0].annotations.requiresConfirmation
)
Write-Host "Status: $($Direct.status)"
Write-Host "Checked events: $($Direct.checked_event_count)"
Write-Host (
    "Events with evidence: " +
    $Direct.events_with_evidence
)
Write-Host (
    "Events without evidence: " +
    $Direct.events_without_evidence
)
Write-Host (
    "Evidence references: " +
    $Direct.referenced_evidence_count
)
Write-Host "Valid evidence: $($Direct.valid_evidence_count)"
Write-Host "Issues: $($Direct.issue_count)"
if (@($Direct.issues).Count -gt 0) {
    Write-Host "Issue codes:"
    foreach ($Issue in @($Direct.issues)) {
        Write-Host (
            "  $($Issue.event_id) " +
            "$($Issue.evidence_kind) $($Issue.code)"
        )
    }
}
Write-Host "Paths exposed: $($Direct.paths_included)"
Write-Host "Read only: $($Direct.read_only)"
Write-Host "Write tool calls: $($WriteCalls.Count)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "MCP read-only tools: $($McpTools.Count)"
Write-Host "Dashboard evidence status and prompt: ready"
Write-Host "Evidence Integrity Agent smoke test passed."
