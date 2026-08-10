param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"

Write-Host "Checking EdgeSentinel API at $BaseUrl"

$Health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
if ($Health.status -ne "ok") {
    throw "API health check failed: $($Health | ConvertTo-Json -Depth 6)"
}

$Events = Invoke-RestMethod `
    -Uri "$BaseUrl/api/v1/events?limit=3" `
    -Method Get

$Tools = Invoke-RestMethod `
    -Uri "$BaseUrl/api/v1/harness/tools" `
    -Method Get
$ExpectedTools = @(
    "camera.capture_snapshot",
    "camera.get_status",
    "camera.restart",
    "evidence.verify_event",
    "evidence.verify_recent",
    "event.acknowledge",
    "event.get_detail",
    "event.query",
    "event.summarize",
    "inventory.compare_state",
    "inventory.get_current_state",
    "inventory.get_removed_items",
    "report.generate",
    "system.cleanup_retained_data",
    "system.get_health",
    "system.get_retention_cleanup_history",
    "system.get_runtime_benchmark",
    "system.get_storage_usage",
    "system.preview_data_retention",
    "vision.get_model_info",
    "vision.get_performance",
    "vision.count_objects",
    "vision.get_current_objects",
    "vision.get_people_count",
    "vision.get_track_history",
    "vision.get_zone_status"
)
$ActualTools = @($Tools.tools | ForEach-Object { $_.name } | Sort-Object)
$MissingTools = @($ExpectedTools | Where-Object {
    $_ -notin $ActualTools
})
$UnexpectedTools = @($ActualTools | Where-Object {
    $_ -notin $ExpectedTools
})
if (
    $Tools.count -ne $ExpectedTools.Count -or
    $MissingTools.Count -gt 0 -or
    $UnexpectedTools.Count -gt 0
) {
    throw "Unexpected Harness tool registry"
}

$ToolArguments = @{
    object_class = "bottle"
    limit = 2
} | ConvertTo-Json
$ToolCall = Invoke-RestMethod `
    -Uri "$BaseUrl/api/v1/harness/tools/event.query/invoke" `
    -Method Post `
    -ContentType "application/json" `
    -Body $ToolArguments
if ($ToolCall.status -ne "SUCCEEDED") {
    throw "Harness event.query failed"
}

$Docs = Invoke-WebRequest `
    -Uri "$BaseUrl/docs" `
    -Method Get `
    -UseBasicParsing
if ($Docs.StatusCode -ne 200) {
    throw "API documentation returned HTTP $($Docs.StatusCode)"
}

$EvidencePath = $null
foreach ($EventRecord in $Events.events) {
    if (
        $EventRecord.evidence_urls -and
        $EventRecord.evidence_urls.primary
    ) {
        $EvidencePath = $EventRecord.evidence_urls.primary
        break
    }
}
if (-not $EvidencePath) {
    throw "No recent event exposed a primary evidence URL"
}

$Evidence = Invoke-WebRequest `
    -Uri "$BaseUrl$EvidencePath" `
    -Method Get `
    -UseBasicParsing
if ($Evidence.StatusCode -ne 200) {
    throw "Evidence request returned HTTP $($Evidence.StatusCode)"
}
if ($Evidence.Headers["Content-Type"] -notlike "image/jpeg*") {
    throw "Unexpected evidence content type: $($Evidence.Headers['Content-Type'])"
}
if ($Evidence.RawContentLength -le 0) {
    throw "Evidence response was empty"
}

Write-Host ""
Write-Host "Health:"
$Health | ConvertTo-Json -Depth 6

Write-Host ""
Write-Host "Latest events:"
$Events | ConvertTo-Json -Depth 10

Write-Host ""
Write-Host "Docs HTTP status: $($Docs.StatusCode)"
Write-Host "Evidence URL: $EvidencePath"
Write-Host "Evidence bytes: $($Evidence.RawContentLength)"
Write-Host "Harness tools: $($ActualTools -join ', ')"
Write-Host "Harness call ID: $($ToolCall.call_id)"
Write-Host "Harness event count: $($ToolCall.result.count)"
Write-Host "API smoke test passed."
