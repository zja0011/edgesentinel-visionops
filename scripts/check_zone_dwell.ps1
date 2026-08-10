param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [int]$DwellTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"

function Invoke-Utf8JsonGet {
    param([string]$Path)

    $Client = New-Object System.Net.WebClient
    try {
        $Bytes = $Client.DownloadData("$BaseUrl$Path")
        $Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
        return $Text | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

function Invoke-Utf8AgentTask {
    param([string]$Message)

    $Json = @{
        message = $Message
    } | ConvertTo-Json -Compress
    $Body = [System.Text.Encoding]::UTF8.GetBytes($Json)
    $Client = New-Object System.Net.WebClient
    try {
        $Client.Headers["Content-Type"] = (
            "application/json; charset=utf-8"
        )
        $Bytes = $Client.UploadData(
            "$BaseUrl/api/v1/agent/tasks",
            "POST",
            $Body
        )
        $Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
        return $Text | ConvertFrom-Json
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

function Wait-ForPeopleCount {
    param(
        [int]$Minimum,
        [int]$Maximum,
        [int]$TimeoutSeconds
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $Deadline) {
        try {
            $People = Invoke-Utf8JsonGet `
                -Path "/api/v1/vision/people"
            if (
                $People.stale -eq $false -and
                [int]$People.current_people -ge $Minimum -and
                [int]$People.current_people -le $Maximum
            ) {
                return $People
            }
        }
        catch {
        }
        Start-Sleep -Seconds 1
    }
    throw "People count did not reach the expected range"
}

Write-Host "Checking ZONE_DWELL at $BaseUrl/dashboard"

$Health = Invoke-Utf8JsonGet -Path "/health"
$Camera = Invoke-Utf8JsonGet -Path "/api/v1/camera/status"
if (
    $Health.status -ne "ok" -or
    $Camera.status -ne "RUNNING"
) {
    throw "API or camera runtime is not healthy"
}

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    -not ($Dashboard.Contains('value="ZONE_DWELL"')) -or
    -not ($Javascript.Contains("ZONE_DWELL")) -or
    -not ($Javascript.Contains("long") -or
        $Javascript.Contains([char]0x505c))
) {
    throw "Dashboard dwell-event assets are incomplete"
}

Write-Host ""
Write-Host "PREPARE:"
Write-Host "1. Move every person completely out of the camera frame."
Write-Host "2. Keep the camera and Jetson running."
$null = Read-Host "Press Enter when the frame is empty"
$EmptyPeople = Wait-ForPeopleCount `
    -Minimum 0 `
    -Maximum 0 `
    -TimeoutSeconds 30
Start-Sleep -Seconds 3

$Baseline = Invoke-Utf8JsonGet `
    -Path (
        "/api/v1/events?type=ZONE_DWELL" +
        "&object_class=person&camera_id=camera_01&limit=100"
    )
$BaselineIds = @(
    @($Baseline.events) |
        ForEach-Object { $_.event_id }
)

Write-Host ""
Write-Host "ACTION REQUIRED:"
Write-Host "1. Walk into either the left or right zone."
Write-Host "2. Stand in that same zone without crossing the center band."
Write-Host "3. Remain visible and nearly still for at least 25 seconds."
$null = Read-Host "Press Enter once you are standing in the zone"
$DetectedPeople = Wait-ForPeopleCount `
    -Minimum 1 `
    -Maximum 4 `
    -TimeoutSeconds 15

$Deadline = [DateTime]::UtcNow.AddSeconds(
    $DwellTimeoutSeconds
)
$NewEvents = @()
while ([DateTime]::UtcNow -lt $Deadline) {
    $Events = Invoke-Utf8JsonGet `
        -Path (
            "/api/v1/events?type=ZONE_DWELL" +
            "&object_class=person&camera_id=camera_01&limit=100"
        )
    $NewEvents = @(
        @($Events.events) |
            Where-Object {
                $BaselineIds -notcontains $_.event_id
            }
    )
    if ($NewEvents.Count -ge 1) {
        break
    }
    Start-Sleep -Seconds 1
}

if ($NewEvents.Count -ne 1) {
    throw (
        "Expected exactly one new ZONE_DWELL event; got " +
        $NewEvents.Count
    )
}

$DwellEvent = $NewEvents[0]
if (
    $DwellEvent.event_type -ne "ZONE_DWELL" -or
    $DwellEvent.severity -ne "MEDIUM" -or
    $DwellEvent.object_class -ne "person" -or
    [double]$DwellEvent.details.dwell_seconds_threshold -ne 20 -or
    [double]$DwellEvent.details.observed_dwell_seconds -lt 20 -or
    [int]$DwellEvent.details.entered_frame_id -le 0
) {
    $DwellEvent | ConvertTo-Json -Depth 10
    throw "ZONE_DWELL event fields are inconsistent"
}

$EvidenceUrl = $DwellEvent.evidence_urls.primary
if (-not $EvidenceUrl) {
    throw "ZONE_DWELL evidence URL is missing"
}
$EvidenceClient = New-Object System.Net.WebClient
try {
    $Evidence = $EvidenceClient.DownloadData(
        "$BaseUrl$EvidenceUrl"
    )
}
finally {
    $EvidenceClient.Dispose()
}
if (
    $Evidence.Length -le 4 -or
    $Evidence[0] -ne 0xFF -or
    $Evidence[1] -ne 0xD8 -or
    $Evidence[$Evidence.Length - 2] -ne 0xFF -or
    $Evidence[$Evidence.Length - 1] -ne 0xD9
) {
    throw "ZONE_DWELL evidence is not a complete JPEG"
}

$AgentMessage = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String(
        "5pyA6L+R55qE5Lq65ZGY5YGc55WZ5LqL5Lu2"
    )
)
$Agent = Invoke-Utf8AgentTask -Message $AgentMessage
$AgentTools = @($Agent.tool_results)
if (
    $Agent.status -ne "COMPLETED" -or
    $AgentTools.Count -ne 1 -or
    $AgentTools[0].tool_name -ne "event.query" -or
    $AgentTools[0].status -ne "SUCCEEDED" -or
    [int]$AgentTools[0].result.count -lt 1 -or
    $AgentTools[0].result.events[0].event_type -ne "ZONE_DWELL"
) {
    $Agent | ConvertTo-Json -Depth 12
    throw "Agent dwell-event query failed"
}

Write-Host ""
Write-Host "ZONE_DWELL acceptance summary:"
Write-Host "Initial people: $($EmptyPeople.current_people)"
Write-Host "Detected people: $($DetectedPeople.current_people)"
Write-Host "Event ID: $($DwellEvent.event_id)"
Write-Host "Zone: $($DwellEvent.zone_id)"
Write-Host "Track: $($DwellEvent.track_id)"
Write-Host (
    "Threshold seconds: " +
    $DwellEvent.details.dwell_seconds_threshold
)
Write-Host (
    "Observed dwell seconds: " +
    $DwellEvent.details.observed_dwell_seconds
)
Write-Host "Evidence bytes: $($Evidence.Length)"
Write-Host "Agent dwell event count: $($AgentTools[0].result.count)"
Write-Host "Dashboard dwell assets: ready"
Write-Host "You may now leave the camera frame."
Write-Host "ZONE_DWELL smoke test passed."
