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
        $Client.Headers["Accept"] = "application/json"
        $Client.Headers["Content-Type"] =
            "application/json; charset=utf-8"
        $Json = @{ message = $Message } |
            ConvertTo-Json -Compress
        return (
            $Utf8.GetString(
                $Client.UploadData(
                    "$BaseUrl/api/v1/agent/tasks",
                    "POST",
                    $Utf8.GetBytes($Json)
                )
            ) |
                ConvertFrom-Json
        )
    }
    finally {
        $Client.Dispose()
    }
}

Write-Host "Checking versioned Agent Skills at $BaseUrl/dashboard"

$Catalog = Get-Utf8Json "$BaseUrl/api/v1/harness/skills"
$Skills = @($Catalog.skills)
$Skill = @(
    $Skills |
        Where-Object {
            $_.name -eq "vision.investigate_removed_item"
        }
)
if (
    -not $Catalog.read_only -or
    $Catalog.count -ne $Skills.Count -or
    $Skill.Count -ne 1 -or
    $Skill[0].version -ne "1.0.0" -or
    @($Skill[0].allowed_risks) -notcontains "L0" -or
    [string]::IsNullOrWhiteSpace(
        [string]$Skill[0].instructions_sha256
    )
) {
    throw "The Agent Skill catalog is invalid"
}

$Task = Invoke-Utf8AgentTask (
    "Who took the bottle in the most recent removal event?"
)
$ToolResults = @($Task.tool_results)
$AllowedTools = @(
    "event.query",
    "event.get_detail",
    "evidence.verify_event"
)
if (
    $Task.status -ne "COMPLETED" -or
    $Task.skill.name -ne "vision.investigate_removed_item" -or
    $Task.skill.version -ne "1.0.0" -or
    $ToolResults.Count -lt 1 -or
    $Task.steps -gt $Skill[0].max_steps -or
    [string]::IsNullOrWhiteSpace([string]$Task.answer)
) {
    $Task | ConvertTo-Json -Depth 20
    throw (
        "The Skill-routed Agent task is invalid: " +
        "status=$($Task.status), " +
        "skill=$($Task.skill.name), " +
        "steps=$($Task.steps), " +
        "tools=$($ToolResults.Count), " +
        "answer_empty=$([string]::IsNullOrWhiteSpace([string]$Task.answer))"
    )
}
foreach ($ToolResult in $ToolResults) {
    if (
        $AllowedTools -notcontains $ToolResult.tool_name -or
        $ToolResult.status -ne "SUCCEEDED"
    ) {
        throw "The Skill task used a disallowed or failed tool"
    }
}

$Trace = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/" +
    "$($Task.task_id)/trace?limit=100"
)
$SkillRecords = @(
    @($Trace.records) |
        Where-Object {
            $_.record_type -eq "SKILL_SELECTED"
        }
)
if (
    $SkillRecords.Count -ne 1 -or
    $SkillRecords[0].skill_name -ne
        "vision.investigate_removed_item" -or
    $SkillRecords[0].skill_version -ne "1.0.0" -or
    $SkillRecords[0].skill_sha256 -ne
        $Task.skill.instructions_sha256
) {
    throw "The pinned Skill trace is inconsistent"
}

$Checkpoint = Get-Utf8Json (
    "$BaseUrl/api/v1/agent/tasks/$($Task.task_id)"
)
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.active_skill.name -ne
        "vision.investigate_removed_item" -or
    $Checkpoint.active_skill.instructions_sha256 -ne
        $Task.skill.instructions_sha256
) {
    throw "The pinned Skill checkpoint is inconsistent"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
if (
    $Html -notmatch 'id="agent-run-skill"' -or
    $Javascript -notmatch "SKILL_SELECTED" -or
    $Javascript -notmatch "agentRunSkill"
) {
    throw "Dashboard Skill Workbench assets are incomplete"
}

Write-Host
Write-Host "Agent Skills acceptance summary:"
Write-Host "Catalog skills: $($Catalog.count)"
Write-Host "Task: $($Task.status)"
Write-Host "Skill: $($Task.skill.name)@$($Task.skill.version)"
Write-Host (
    "Skill SHA-256: " +
    "$($Task.skill.instructions_sha256.Substring(0, 16))..."
)
Write-Host "Steps: $($Task.steps)"
Write-Host "Tool calls: $($ToolResults.Count)"
Write-Host "Allowed risks: $(@($Task.skill.allowed_risks) -join ', ')"
Write-Host "Checkpoint: pinned"
Write-Host "Trace: SKILL_SELECTED"
Write-Host "Workbench Skill assets: ready"
Write-Host "Agent Skills smoke test passed."
