param(
    [string]$JetsonAddress = "192.168.1.101",
    [int]$Port = 8000,
    [int]$WaitSeconds = 60
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://${JetsonAddress}:$Port"

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

function Invoke-Utf8Get {
    param([string]$Path)
    return (Get-Utf8Text -Path $Path) | ConvertFrom-Json
}

function Invoke-Utf8AgentTask {
    param([string]$Message)
    $Json = @{ message = $Message } |
        ConvertTo-Json -Compress
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
        return [System.Text.Encoding]::UTF8.GetString(
            $Bytes
        ) | ConvertFrom-Json
    }
    finally {
        $Client.Dispose()
    }
}

function Wait-NoPersonTrack {
    $Deadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        try {
            $Candidate = Invoke-Utf8Get -Path (
                "/api/v1/vision/tracks" +
                "?object_class=person&limit=20"
            )
            if (
                $Candidate.status -eq "available" -and
                $Candidate.stale -eq $false -and
                [int]$Candidate.track_count -eq 0
            ) {
                return
            }
        }
        catch {
            $Candidate = $null
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    throw "Retained person tracks did not clear"
}

function Wait-LeftPersonTrack {
    $Deadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        try {
            $Candidate = Invoke-Utf8Get -Path (
                "/api/v1/vision/tracks" +
                "?object_class=person&limit=20"
            )
            $Tracks = @(
                $Candidate.tracks |
                    Where-Object {
                        $_.visible -eq $true -and
                        [int]$_.observation_count -ge 10 -and
                        "left_zone" -in @($_.current_zone_ids)
                    } |
                    Sort-Object observation_count -Descending
            )
            if (
                $Candidate.status -eq "available" -and
                $Candidate.stale -eq $false -and
                $Tracks.Count -ge 1
            ) {
                return $Tracks[0]
            }
        }
        catch {
            $Candidate = $null
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    throw "A stable person track was not found in the left zone"
}

function Wait-RightwardTrack {
    param([int]$TrackId)
    $Deadline = (Get-Date).AddSeconds($WaitSeconds)
    $LastCandidate = $null
    do {
        try {
            $Candidate = Invoke-Utf8Get -Path (
                "/api/v1/vision/tracks" +
                "?track_id=$TrackId&limit=1"
            )
            $LastCandidate = $Candidate
            $Tracks = @($Candidate.tracks)
            if (
                $Candidate.status -eq "available" -and
                $Candidate.stale -eq $false -and
                $Tracks.Count -eq 1 -and
                $Tracks[0].visible -eq $true -and
                $Tracks[0].movement -match "right" -and
                [double]$Tracks[0].displacement -ge 0.08 -and
                [int]$Tracks[0].sampled_point_count -ge 2 -and
                @($Tracks[0].current_zone_ids).Count -ge 1
            ) {
                return $Candidate
            }
        }
        catch {
            $Candidate = $null
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    if ($null -ne $LastCandidate) {
        Write-Host ""
        Write-Host "Last response for track ${TrackId}:"
        $LastCandidate | ConvertTo-Json -Depth 10
    }
    try {
        $CurrentPeople = Invoke-Utf8Get -Path (
            "/api/v1/vision/tracks" +
            "?object_class=person&limit=20"
        )
        Write-Host "Current retained person tracks:"
        $CurrentPeople | ConvertTo-Json -Depth 10
    }
    catch {
        Write-Host "Current person tracks could not be read."
    }
    throw (
        "Track $TrackId did not retain a measurable rightward path. " +
        "The target may have moved too quickly or received a new ID."
    )
}

Write-Host "Checking live track-history Agent at $BaseUrl"

$Health = Invoke-Utf8Get -Path "/health"
$Tools = Invoke-Utf8Get -Path "/api/v1/harness/tools"
$Dashboard = Get-Utf8Text -Path "/dashboard"
if ($Health.status -ne "ok") {
    throw "EdgeSentinel API is not healthy"
}
$ToolDefinition = @(
    $Tools.tools | Where-Object {
        $_.name -eq "vision.get_track_history"
    }
)
if (
    $ToolDefinition.Count -ne 1 -or
    $ToolDefinition[0].annotations.readOnlyHint -ne $true -or
    $ToolDefinition[0].annotations.riskLevel -ne "L0" -or
    $ToolDefinition[0].annotations.autoExecute -ne $true -or
    $ToolDefinition[0].annotations.requiresConfirmation -ne $false
) {
    throw "vision.get_track_history policy metadata is invalid"
}

Write-Host ""
Write-Host "PREPARE:"
Write-Host "1. Move every person completely out of the camera frame."
Write-Host "2. Keep the camera view empty."
Read-Host "Press Enter when no person is visible"
Wait-NoPersonTrack

Write-Host ""
Write-Host "ACTION 1:"
Write-Host "1. Stand fully inside the left zone."
Write-Host "2. Keep your feet away from the center neutral band."
Write-Host "3. Remain visible and still until the track is acquired."
Read-Host "Press Enter once you are standing in the left zone"
$InitialTrack = Wait-LeftPersonTrack
$TrackId = [int]$InitialTrack.track_id

Write-Host ""
Write-Host "Track $TrackId acquired."
Write-Host "ACTION 2:"
Write-Host "1. Take two or three slow side-steps to your right."
Write-Host "2. Stay inside the left zone and do not enter the center band."
Write-Host "3. Stop and remain fully visible."
Read-Host "Press Enter after the slow rightward movement"

$Direct = Wait-RightwardTrack -TrackId $TrackId
$DirectTrack = @($Direct.tracks)[0]
$Points = @($DirectTrack.points)
foreach ($Point in $Points) {
    if (
        [double]$Point.x -lt 0.0 -or
        [double]$Point.x -gt 1.0 -or
        [double]$Point.y -lt 0.0 -or
        [double]$Point.y -gt 1.0
    ) {
        throw "Track history contains a non-normalized point"
    }
}

$Task = Invoke-Utf8AgentTask -Message (
    "Show track history for track $TrackId."
)
$Results = @($Task.tool_results)
if (
    $Task.status -ne "COMPLETED" -or
    $null -ne $Task.pending_confirmation -or
    $Results.Count -ne 1 -or
    $Results[0].tool_name -ne "vision.get_track_history" -or
    $Results[0].status -ne "SUCCEEDED"
) {
    $Task | ConvertTo-Json -Depth 12
    throw "Track-history Agent task failed"
}

$Result = $Results[0].result
$Tracks = @($Result.tracks)
if (
    $Result.stale -ne $false -or
    $Result.read_only -ne $true -or
    [int]$Result.selected_track_id -ne $TrackId -or
    [int]$Result.track_count -ne 1 -or
    $Tracks.Count -ne 1 -or
    [int]$Tracks[0].track_id -ne $TrackId -or
    $Tracks[0].class_name -ne "person" -or
    $Tracks[0].visible -ne $true -or
    $Tracks[0].movement -notmatch "right" -or
    [double]$Tracks[0].displacement -lt 0.08 -or
    [int]$Tracks[0].sampled_point_count -lt 2 -or
    @($Tracks[0].current_zone_ids).Count -lt 1
) {
    $Result | ConvertTo-Json -Depth 12
    throw "Track-history Agent result is invalid"
}
if (
    $null -ne $Result.detections -or
    $null -ne $Tracks[0].bbox
) {
    throw "Track history exposed forbidden detection details"
}

$Checkpoint = Invoke-Utf8Get `
    -Path "/api/v1/agent/tasks/$($Task.task_id)"
if (
    $Checkpoint.status -ne "COMPLETED" -or
    $Checkpoint.task_id -ne $Task.task_id -or
    $Checkpoint.tool_results[0].tool_name -ne (
        "vision.get_track_history"
    ) -or
    [int]$Checkpoint.tool_results[0].result.tracks[0].track_id -ne (
        $TrackId
    )
) {
    throw "Track-history checkpoint does not match"
}
if ($Dashboard -notmatch (
    'id="track-history-prompt"[\s\S]{0,180}data-prompt="'
)) {
    throw "Dashboard track-history prompt is missing"
}

Write-Host ""
Write-Host "Track History Agent acceptance summary:"
Write-Host "Task: $($Task.status)"
Write-Host "Tool: $($Results[0].tool_name) $($Results[0].status)"
Write-Host "Risk: $($ToolDefinition[0].annotations.riskLevel)"
Write-Host "Confirmation required: $($ToolDefinition[0].annotations.requiresConfirmation)"
Write-Host "Track ID: $($Tracks[0].track_id)"
Write-Host "Object class: $($Tracks[0].class_name)"
Write-Host "Movement: $($Tracks[0].movement)"
Write-Host "Normalized displacement: $($Tracks[0].displacement)"
Write-Host "Observations: $($Tracks[0].observation_count)"
Write-Host "Sampled points: $($Tracks[0].sampled_point_count)"
Write-Host "Current zones: $(@($Tracks[0].current_zone_ids) -join ', ')"
Write-Host "Vision stale: $($Result.stale)"
Write-Host "Read only: $($Result.read_only)"
Write-Host "Checkpoint: $($Checkpoint.status)"
Write-Host "Answer: $($Task.answer)"
Write-Host "Dashboard track prompt: ready"
Write-Host "You may now leave the camera frame."
Write-Host "Track History Agent smoke test passed."
