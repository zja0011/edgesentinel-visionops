param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [int]$OutageTimeoutSeconds = 60,
    [int]$RecoveryTimeoutSeconds = 180
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

function Wait-ForRunningCamera {
    param(
        [int]$MinimumGeneration,
        [int]$MinimumRestartCount,
        [int]$TimeoutSeconds
    )

    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $Deadline) {
        try {
            $Camera = Invoke-Utf8JsonGet `
                -Path "/api/v1/camera/status"
            $People = Invoke-Utf8JsonGet `
                -Path "/api/v1/vision/people"
            if (
                $Camera.status -eq "RUNNING" -and
                $Camera.state_stale -eq $false -and
                $Camera.worker_running -eq $true -and
                [int]$Camera.generation -ge $MinimumGeneration -and
                [int]$Camera.restart_count -ge (
                    $MinimumRestartCount
                ) -and
                $People.stale -eq $false
            ) {
                return [PSCustomObject]@{
                    Camera = $Camera
                    People = $People
                }
            }
        }
        catch {
        }
        Start-Sleep -Seconds 1
    }
    throw "Camera did not reach RUNNING before the timeout"
}

Write-Host (
    "Checking camera disconnect recovery at " +
    "$BaseUrl/dashboard"
)
Write-Host "Waiting for the initial healthy camera state..."

$Initial = Wait-ForRunningCamera `
    -MinimumGeneration 1 `
    -MinimumRestartCount 0 `
    -TimeoutSeconds $RecoveryTimeoutSeconds
$BaselineCamera = $Initial.Camera
$BaselinePeople = $Initial.People
$BaselineOffline = Invoke-Utf8JsonGet `
    -Path (
        "/api/v1/events?type=CAMERA_OFFLINE" +
        "&camera_id=camera_01&limit=100"
    )
$BaselineRecovered = Invoke-Utf8JsonGet `
    -Path (
        "/api/v1/events?type=CAMERA_RECOVERED" +
        "&camera_id=camera_01&limit=100"
    )
$BaselineOfflineIds = @(
    @($BaselineOffline.events) |
        ForEach-Object { $_.event_id }
)
$BaselineRecoveredIds = @(
    @($BaselineRecovered.events) |
        ForEach-Object { $_.event_id }
)

$Dashboard = Get-Utf8Text -Path "/dashboard"
$Javascript = Get-Utf8Text `
    -Path "/dashboard/assets/dashboard.js"
if (
    -not ($Dashboard.Contains('id="camera-runtime-status"')) -or
    -not ($Javascript.Contains('camera: "/api/v1/camera/status"')) -or
    -not ($Javascript.Contains("renderCameraStatus")) -or
    -not ($Javascript.Contains("CAMERA_OFFLINE")) -or
    -not ($Javascript.Contains("CAMERA_RECOVERED"))
) {
    throw "Dashboard camera supervisor assets are incomplete"
}

Write-Host ""
Write-Host "ACTION REQUIRED:"
Write-Host "1. Unplug only the USB camera from the Jetson."
Write-Host "2. Leave the network adapter and Jetson power connected."
$null = Read-Host "Press Enter after the camera is unplugged"

$OutageStarted = [DateTime]::UtcNow
$OutageDeadline = $OutageStarted.AddSeconds(
    $OutageTimeoutSeconds
)
$OutageCamera = $null
$OutagePeople = $null
$ApiStayedOnline = $true
while ([DateTime]::UtcNow -lt $OutageDeadline) {
    try {
        $Health = Invoke-Utf8JsonGet -Path "/health"
        $Camera = Invoke-Utf8JsonGet `
            -Path "/api/v1/camera/status"
        $People = Invoke-Utf8JsonGet `
            -Path "/api/v1/vision/people"
        if ($Health.status -ne "ok") {
            $ApiStayedOnline = $false
            break
        }
        if (
            $Camera.status -ne "RUNNING" -and
            $People.stale -eq $true
        ) {
            $OutageCamera = $Camera
            $OutagePeople = $People
            break
        }
    }
    catch {
        $ApiStayedOnline = $false
        break
    }
    Start-Sleep -Seconds 1
}

if (
    -not $ApiStayedOnline -or
    $null -eq $OutageCamera -or
    $null -eq $OutagePeople
) {
    throw (
        "The outage was not detected while keeping the API online. " +
        "Reconnect the camera, then inspect the runtime log."
    )
}

Write-Host ""
Write-Host "Outage detected safely."
Write-Host "Reconnect the same USB camera to the Jetson now."
$null = Read-Host "Press Enter after the camera is reconnected"

$RecoveryStarted = [DateTime]::UtcNow
$Recovered = Wait-ForRunningCamera `
    -MinimumGeneration ([int]$BaselineCamera.generation + 1) `
    -MinimumRestartCount (
        [int]$BaselineCamera.restart_count + 1
    ) `
    -TimeoutSeconds $RecoveryTimeoutSeconds
$RecoveredCamera = $Recovered.Camera
$RecoveredPeople = $Recovered.People
$RecoverySeconds = [Math]::Round(
    (
        [DateTime]::UtcNow - $RecoveryStarted
    ).TotalSeconds,
    1
)
$FinalHealth = Invoke-Utf8JsonGet -Path "/health"
if (
    $FinalHealth.status -ne "ok" -or
    $RecoveredCamera.status -ne "RUNNING" -or
    $RecoveredPeople.stale -ne $false
) {
    throw "The camera recovery result is inconsistent"
}

$LifecycleDeadline = [DateTime]::UtcNow.AddSeconds(30)
$OfflineEvents = $null
$RecoveredEvents = $null
while ([DateTime]::UtcNow -lt $LifecycleDeadline) {
    $OfflineEvents = Invoke-Utf8JsonGet `
        -Path (
            "/api/v1/events?type=CAMERA_OFFLINE" +
            "&camera_id=camera_01&limit=100"
        )
    $RecoveredEvents = Invoke-Utf8JsonGet `
        -Path (
            "/api/v1/events?type=CAMERA_RECOVERED" +
            "&camera_id=camera_01&limit=100"
        )
    $NewOfflineEvents = @(
        @($OfflineEvents.events) |
            Where-Object {
                $BaselineOfflineIds -notcontains $_.event_id
            }
    )
    $NewRecoveredEvents = @(
        @($RecoveredEvents.events) |
            Where-Object {
                $BaselineRecoveredIds -notcontains $_.event_id
            }
    )
    if (
        $NewOfflineEvents.Count -ge 1 -and
        $NewRecoveredEvents.Count -ge 1
    ) {
        break
    }
    Start-Sleep -Seconds 1
}

$OfflineAdded = $NewOfflineEvents.Count
$RecoveredAdded = $NewRecoveredEvents.Count
if ($OfflineAdded -ne 1 -or $RecoveredAdded -ne 1) {
    throw (
        "Expected exactly one offline and one recovered event; " +
        "got offline=$OfflineAdded recovered=$RecoveredAdded"
    )
}

$OfflineEvent = $NewOfflineEvents[0]
$RecoveredEvent = $NewRecoveredEvents[0]
if (
    $OfflineEvent.object_class -ne "camera" -or
    $OfflineEvent.severity -ne "HIGH" -or
    $RecoveredEvent.object_class -ne "camera" -or
    $RecoveredEvent.severity -ne "INFO" -or
    $RecoveredEvent.details.offline_event_id -ne (
        $OfflineEvent.event_id
    ) -or
    [double]$RecoveredEvent.details.outage_duration_seconds -lt 0
) {
    throw "Camera lifecycle events are inconsistent"
}

$AgentMessage = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String(
        "5pyA6L+R5pGE5YOP5aS05pWF6Zqc5LiO5oGi5aSN5LqL5Lu2"
    )
)
$Agent = Invoke-Utf8AgentTask -Message $AgentMessage
$AgentTools = @($Agent.tool_results)
if (
    $Agent.status -ne "COMPLETED" -or
    $AgentTools.Count -ne 1 -or
    $AgentTools[0].tool_name -ne "event.query" -or
    $AgentTools[0].status -ne "SUCCEEDED" -or
    [int]$AgentTools[0].result.count -lt 2 -or
    $AgentTools[0].result.events[0].object_class -ne "camera"
) {
    $Agent | ConvertTo-Json -Depth 12
    throw "Agent camera lifecycle query failed"
}

Write-Host ""
Write-Host "Camera Recovery acceptance summary:"
Write-Host "Baseline status: $($BaselineCamera.status)"
Write-Host "Baseline generation: $($BaselineCamera.generation)"
Write-Host "Outage status: $($OutageCamera.status)"
Write-Host "Vision stale during outage: $($OutagePeople.stale)"
Write-Host "API stayed online: $ApiStayedOnline"
Write-Host "Recovered status: $($RecoveredCamera.status)"
Write-Host "Recovered generation: $($RecoveredCamera.generation)"
Write-Host "Restart count: $($RecoveredCamera.restart_count)"
Write-Host "Recovered vision stale: $($RecoveredPeople.stale)"
Write-Host "Recovered frame ID: $($RecoveredPeople.frame_id)"
Write-Host "Recovery wait seconds: $RecoverySeconds"
Write-Host "CAMERA_OFFLINE events added: $OfflineAdded"
Write-Host "CAMERA_RECOVERED events added: $RecoveredAdded"
Write-Host (
    "Lifecycle event link: " +
    $RecoveredEvent.details.offline_event_id
)
Write-Host (
    "Recorded outage seconds: " +
    $RecoveredEvent.details.outage_duration_seconds
)
Write-Host "Agent camera event count: $($AgentTools[0].result.count)"
Write-Host "Dashboard camera status assets: ready"
Write-Host "Camera Recovery smoke test passed."
