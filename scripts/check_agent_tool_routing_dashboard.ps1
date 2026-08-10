param(
    [string]$BaseUrl = "http://192.168.1.101:8000",
    [int]$MaximumPromptTokens = 5000
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Utf8Json {
    param([string]$Uri)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Accept"] = "application/json"
        return $Utf8.GetString($Client.DownloadData($Uri)) |
            ConvertFrom-Json
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

function Invoke-Utf8JsonPost {
    param([string]$Uri, [hashtable]$Body)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Accept"] = "application/json"
        $Client.Headers["Content-Type"] =
            "application/json; charset=utf-8"
        $Json = $Body | ConvertTo-Json -Depth 10 -Compress
        return $Utf8.GetString(
            $Client.UploadData(
                $Uri,
                "POST",
                $Utf8.GetBytes($Json)
            )
        ) | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

function Assert-TerminalRoute {
    param(
        [object]$Task,
        [string]$ExpectedMode,
        [string[]]$ExpectedTools
    )
    if ($Task.status -ne "COMPLETED") {
        throw "Agent task did not complete: $($Task.status)"
    }
    $Route = $Task.tool_route
    if (
        $null -eq $Route -or
        $Route.mode -ne $ExpectedMode -or
        $Route.fallback_used -or
        $Route.max_tools -ne 6 -or
        $Route.selected_count -ne $ExpectedTools.Count -or
        (@($Route.selected_tools) -join ",") -ne
            ($ExpectedTools -join ",")
    ) {
        $Task | ConvertTo-Json -Depth 12
        throw "Agent tool route is invalid"
    }
    if (
        $Task.execution.usage.prompt_tokens -le 0 -or
        $Task.execution.usage.prompt_tokens -ge
            $MaximumPromptTokens
    ) {
        throw (
            "Prompt token target was not met: " +
            $Task.execution.usage.prompt_tokens
        )
    }
}

function Assert-RoutePersistence {
    param([object]$Task)
    $Checkpoint = Get-Utf8Json (
        "$BaseUrl/api/v1/agent/tasks/$($Task.task_id)"
    )
    if (
        $Checkpoint.tool_route.mode -ne $Task.tool_route.mode -or
        (@($Checkpoint.tool_route.selected_tools) -join ",") -ne
            (@($Task.tool_route.selected_tools) -join ",")
    ) {
        throw "Checkpoint did not retain the pinned tool route"
    }
    $Trace = Get-Utf8Json (
        "$BaseUrl/api/v1/agent/tasks/$($Task.task_id)/trace?limit=100"
    )
    $Routes = @(
        $Trace.records |
            Where-Object { $_.record_type -eq "TOOL_ROUTE" }
    )
    if (
        $Routes.Count -ne 1 -or
        $Trace.model_content_exposed -or
        $Trace.raw_trace_exposed
    ) {
        throw "Sanitized TOOL_ROUTE trace is invalid"
    }
    return $Routes[0]
}

Write-Host (
    "Checking deterministic Agent tool routing at " +
    "$BaseUrl/dashboard"
)

$Health = Get-Utf8Json "$BaseUrl/health"
if (
    $Health.status -ne "ok" -or
    $Health.agent_model.mode -ne "remote" -or
    $Health.agent_model.provider -ne "deepseek"
) {
    throw "The API is not running in remote DeepSeek mode"
}

$General = Invoke-Utf8JsonPost `
    "$BaseUrl/api/v1/agent/tasks" `
    @{ message = "What weekday is it today? Answer briefly." }
Assert-TerminalRoute $General "NO_MATCH" @()
$GeneralRouteTrace = Assert-RoutePersistence $General

$People = Invoke-Utf8JsonPost `
    "$BaseUrl/api/v1/agent/tasks" `
    @{
        message = (
            "Use the tool to confirm how many people are " +
            "currently in the camera view."
        )
    }
Assert-TerminalRoute `
    $People `
    "DETERMINISTIC" `
    @("vision.get_people_count")
$PeopleRouteTrace = Assert-RoutePersistence $People

$PeopleTools = @($People.tool_results)
if (
    $PeopleTools.Count -ne 1 -or
    $PeopleTools[0].tool_name -ne "vision.get_people_count" -or
    $PeopleTools[0].status -ne "SUCCEEDED"
) {
    $People | ConvertTo-Json -Depth 12
    throw "The routed people-count tool call is invalid"
}
if (
    $People.tool_route.schema_bytes_after -le 0 -or
    $People.tool_route.schema_bytes_after -ge
        $People.tool_route.schema_bytes_before -or
    $People.tool_route.schema_reduction_percent -lt 90
) {
    throw "Tool-schema reduction is below the acceptance target"
}

$Html = Get-Utf8Text "$BaseUrl/dashboard"
$Javascript = Get-Utf8Text (
    "$BaseUrl/dashboard/assets/dashboard.js"
)
foreach ($Needle in @(
    'id="agent-run-tool-route"',
    "HARNESS RUN"
)) {
    if ($Html -notmatch [regex]::Escape($Needle)) {
        throw "Dashboard route metadata is incomplete: $Needle"
    }
}
foreach ($Needle in @(
    "TOOL_ROUTE",
    "TOOL_ROUTE_DENIED",
    "schema_reduction_percent",
    "agentRunToolRoute"
)) {
    if ($Javascript -notmatch [regex]::Escape($Needle)) {
        throw "Dashboard route assets are incomplete: $Needle"
    }
}

Write-Host
Write-Host "Agent Tool Routing Dashboard acceptance summary:"
Write-Host "General task: $($General.status)"
Write-Host "General route: $($General.tool_route.mode)"
Write-Host "General tools sent: $($General.tool_route.selected_count)"
Write-Host "General prompt tokens: $($General.execution.usage.prompt_tokens)"
Write-Host "People task: $($People.status)"
Write-Host "People route: $($People.tool_route.mode)"
Write-Host "People tool: $($PeopleTools[0].tool_name) $($PeopleTools[0].status)"
Write-Host "People prompt tokens: $($People.execution.usage.prompt_tokens)"
Write-Host (
    "Schema bytes: $($People.tool_route.schema_bytes_before) -> " +
    "$($People.tool_route.schema_bytes_after)"
)
Write-Host (
    "Schema reduction: " +
    "$($People.tool_route.schema_reduction_percent)%"
)
Write-Host "Maximum visible tools: $($People.tool_route.max_tools)"
Write-Host "Catalog fallback used: False"
Write-Host "Checkpoint route retained: True"
Write-Host (
    "TOOL_ROUTE trace records: " +
    "$(@($GeneralRouteTrace, $PeopleRouteTrace).Count)"
)
Write-Host "Model content exposed: False"
Write-Host "Workbench route assets: ready"
Write-Host "Agent Tool Routing Dashboard smoke test passed."
