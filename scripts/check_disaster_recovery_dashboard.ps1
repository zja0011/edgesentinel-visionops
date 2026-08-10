param(
    [string]$BaseUrl = "https://192.168.1.101:8443",
    [string]$Username = "zja",
    [string]$CertificatePath = ".\data\runtime\tls\edgesentinel-server.crt",
    [switch]$AssetsOnly
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$BaseUrl = $BaseUrl.TrimEnd("/")
$CertificatePath = (Resolve-Path -LiteralPath $CertificatePath).Path
$PinnedCertificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertificatePath)
$Sha256 = [System.Security.Cryptography.SHA256]::Create()
$script:ExpectedTlsFingerprint = (($Sha256.ComputeHash($PinnedCertificate.RawData) |
    ForEach-Object { $_.ToString("X2") }) -join "")
$Sha256.Dispose()
$PreviousSecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol
[System.Net.ServicePointManager]::SecurityProtocol = `
    $PreviousSecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
$PreviousCallback = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
if (-not ("EdgeSentinelRecoveryCertificatePinning" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

public static class EdgeSentinelRecoveryCertificatePinning
{
    public static string ExpectedFingerprint = "";

    public static bool Validate(
        object sender,
        X509Certificate certificate,
        X509Chain chain,
        SslPolicyErrors errors)
    {
        if (certificate == null || String.IsNullOrEmpty(ExpectedFingerprint))
            return false;
        using (SHA256 hasher = SHA256.Create())
        {
            byte[] digest = hasher.ComputeHash(certificate.GetRawCertData());
            string actual = BitConverter.ToString(digest).Replace("-", "");
            return String.Equals(
                actual,
                ExpectedFingerprint,
                StringComparison.OrdinalIgnoreCase);
        }
    }

    public static readonly RemoteCertificateValidationCallback Callback =
        new RemoteCertificateValidationCallback(Validate);
}
"@
}
[EdgeSentinelRecoveryCertificatePinning]::ExpectedFingerprint = `
    $script:ExpectedTlsFingerprint
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = `
    [EdgeSentinelRecoveryCertificatePinning]::Callback

function Invoke-JsonRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        [hashtable]$Headers = @{},
        [hashtable]$Body = $null
    )
    $Parameters = @{
        Uri = $Uri
        Method = $Method
        WebSession = $Session
        Headers = $Headers
    }
    if ($null -ne $Body) {
        $Json = $Body | ConvertTo-Json -Depth 10 -Compress
        $Parameters.ContentType = "application/json; charset=utf-8"
        $Parameters.Body = $Utf8.GetBytes($Json)
    }
    return Invoke-RestMethod @Parameters
}

function Get-ExpectedErrorStatus {
    param(
        [string]$Method,
        [string]$Uri,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        [hashtable]$Headers,
        [hashtable]$Body
    )
    try {
        $null = Invoke-JsonRequest -Method $Method -Uri $Uri `
            -Session $Session -Headers $Headers -Body $Body
        return 200
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function Get-ToolResult {
    param([object]$Task, [string]$ToolName)
    return @($Task.tool_results) | Where-Object {
        $_.tool_name -eq $ToolName
    } | Select-Object -First 1
}

try {
    Write-Host "Checking confirmation-gated disaster recovery at $BaseUrl/dashboard"
    $Health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
    if (-not $Health.transport_security.tls_enabled -or
        -not $Health.authentication.ready) {
        throw "TLS or Dashboard authentication is not ready"
    }

    $Html = (Invoke-WebRequest -Uri "$BaseUrl/dashboard" `
        -UseBasicParsing).Content
    $Javascript = (Invoke-WebRequest `
        -Uri "$BaseUrl/dashboard/assets/dashboard.js" `
        -UseBasicParsing).Content
    $HasStatusPrompt = $Html -match 'id="recovery-status-prompt"'
    $HasCreatePrompt = $Html -match 'id="recovery-create-prompt"'
    $HasRecoveryTool = $Javascript -match 'recovery\.create_backup'
    $HasPendingBranch = $Javascript -match `
        'pending\.tool_name === "recovery\.create_backup"'
    $HasActionBranch = $Javascript -match `
        'activeAgentToolName === "recovery\.create_backup"'
    if (-not $HasStatusPrompt -or
        -not $HasCreatePrompt -or
        -not $HasRecoveryTool -or
        -not $HasPendingBranch -or
        -not $HasActionBranch) {
        throw (
            "Dashboard disaster-recovery assets are incomplete: " +
            "status_prompt=$HasStatusPrompt, " +
            "create_prompt=$HasCreatePrompt, " +
            "tool=$HasRecoveryTool, " +
            "pending_branch=$HasPendingBranch, " +
            "action_branch=$HasActionBranch"
        )
    }
    if ($AssetsOnly) {
        Write-Host ""
        Write-Host "Disaster Recovery Dashboard asset recheck summary:"
        Write-Host "Status prompt: ready"
        Write-Host "Create prompt: ready"
        Write-Host "L1 confirmation description: ready"
        Write-Host "L1 confirmation action: ready"
        Write-Host "No backup created by this recheck: True"
        Write-Host "Disaster Recovery Dashboard smoke test passed."
        return
    }

    $SecurePassword = Read-Host "Dashboard password for $Username" -AsSecureString
    $Credential = New-Object System.Management.Automation.PSCredential($Username, $SecurePassword)
    $PlainPassword = $Credential.GetNetworkCredential().Password
    $Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    try {
        $Login = Invoke-JsonRequest -Method Post `
            -Uri "$BaseUrl/api/v1/auth/login" -Session $Session `
            -Body @{username = $Username; password = $PlainPassword}
    }
    finally {
        $PlainPassword = $null
    }
    if ($Login.role -ne "admin") {
        throw "Disaster recovery acceptance requires the admin role"
    }
    $Headers = @{"X-EdgeSentinel-CSRF" = [string]$Login.csrf_token}
    $InitialMode = $Health.agent_model.mode
    if ($InitialMode -ne "offline") {
        $null = Invoke-JsonRequest -Method Put `
            -Uri "$BaseUrl/api/v1/agent/model-mode" `
            -Session $Session -Headers $Headers `
            -Body @{mode = "offline"; confirmation = "SWITCH_AGENT_MODEL"}
    }

    $StatusTask = Invoke-JsonRequest -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks" -Session $Session `
        -Headers $Headers -Body @{message = "list recovery backups"}
    $StatusTool = Get-ToolResult $StatusTask "recovery.get_status"
    if ($StatusTask.status -ne "COMPLETED" -or
        $StatusTool.status -ne "SUCCEEDED" -or
        -not $StatusTool.result.read_only -or
        $StatusTool.result.credentials_included) {
        throw (
            "The read-only recovery status task is invalid: " +
            "task=$($StatusTask.status), " +
            "tool=$($StatusTool.tool_name), " +
            "tool_status=$($StatusTool.status)"
        )
    }
    $BeforeCount = [int]$StatusTool.result.backup_count

    $CancelledPending = Invoke-JsonRequest -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks" -Session $Session `
        -Headers $Headers -Body @{message = "create disaster recovery backup"}
    if ($CancelledPending.status -ne "AWAITING_CONFIRMATION" -or
        $CancelledPending.pending_confirmation.tool_name -ne "recovery.create_backup" -or
        $CancelledPending.pending_confirmation.risk -ne "L1" -or
        @($CancelledPending.tool_results).Count -ne 0) {
        throw "The cancelled backup task did not stop at the L1 gate"
    }
    $Cancelled = Invoke-JsonRequest -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks/$($CancelledPending.task_id)/cancel" `
        -Session $Session -Headers $Headers -Body @{cancel = $true}
    if ($Cancelled.status -ne "CANCELLED" -or
        @($Cancelled.tool_results).Count -ne 0) {
        throw "Cancelling the recovery task executed a tool"
    }

    $Pending = Invoke-JsonRequest -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks" -Session $Session `
        -Headers $Headers -Body @{message = "create disaster recovery backup"}
    if ($Pending.status -ne "AWAITING_CONFIRMATION" -or
        $Pending.pending_confirmation.tool_name -ne "recovery.create_backup" -or
        $Pending.pending_confirmation.risk -ne "L1") {
        throw "The backup task did not stop at the L1 confirmation gate"
    }
    $InvalidConfirmation = Get-ExpectedErrorStatus -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks/$($Pending.task_id)/confirm" `
        -Session $Session -Headers $Headers -Body @{confirmation = "yes"}
    if ($InvalidConfirmation -ne 422) {
        throw "Invalid backup confirmation was not rejected: HTTP $InvalidConfirmation"
    }

    $Confirmed = Invoke-JsonRequest -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks/$($Pending.task_id)/confirm" `
        -Session $Session -Headers $Headers `
        -Body @{confirmation = "CONFIRM_TOOL_EXECUTION"}
    $BackupTool = Get-ToolResult $Confirmed "recovery.create_backup"
    if ($Confirmed.status -ne "COMPLETED" -or
        $Confirmed.task_id -ne $Pending.task_id -or
        $BackupTool.status -ne "SUCCEEDED" -or
        $BackupTool.result.status -ne "COMPLETE" -or
        -not $BackupTool.result.sqlite_consistent -or
        $BackupTool.result.credentials_included -or
        $BackupTool.result.absolute_paths_included -or
        $BackupTool.result.file_count -lt 1 -or
        $BackupTool.result.manifest_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw "The confirmed disaster-recovery backup is invalid"
    }

    $PublicTask = Invoke-JsonRequest -Method Get `
        -Uri "$BaseUrl/api/v1/agent/tasks/$($Pending.task_id)" `
        -Session $Session
    $PublicFields = @($PublicTask.PSObject.Properties.Name)
    if ($PublicTask.steps -lt 1 -or
        "step" -in $PublicFields -or
        "user_message" -in $PublicFields -or
        "model_history" -in $PublicFields) {
        throw "The public task checkpoint contract is unsafe or incomplete"
    }

    $DuplicateConfirmation = Get-ExpectedErrorStatus -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks/$($Pending.task_id)/confirm" `
        -Session $Session -Headers $Headers `
        -Body @{confirmation = "CONFIRM_TOOL_EXECUTION"}
    if ($DuplicateConfirmation -ne 409) {
        throw "Duplicate backup confirmation was not rejected: HTTP $DuplicateConfirmation"
    }

    $AfterTask = Invoke-JsonRequest -Method Post `
        -Uri "$BaseUrl/api/v1/agent/tasks" -Session $Session `
        -Headers $Headers -Body @{message = "list recovery backups"}
    $AfterTool = Get-ToolResult $AfterTask "recovery.get_status"
    $BackupIds = @($AfterTool.result.backups | ForEach-Object { $_.backup_id })
    if ($AfterTool.result.backup_count -lt ($BeforeCount + 1) -or
        $BackupTool.result.backup_id -notin $BackupIds) {
        throw "The verified backup is absent from recovery status"
    }

    $Tools = Invoke-JsonRequest -Method Get `
        -Uri "$BaseUrl/api/v1/harness/tools" -Session $Session
    $Schemas = @($Tools.tools)
    $McpTools = @($Schemas | Where-Object {
        $_.annotations.riskLevel -eq "L0" -and
        $_.annotations.readOnlyHint
    })
    if ($Schemas.Count -ne 33 -or $McpTools.Count -ne 25 -or
        "recovery.get_status" -notin @($McpTools.name) -or
        "recovery.preview_restore" -notin @($McpTools.name) -or
        "recovery.create_backup" -in @($McpTools.name)) {
        throw "The recovery tool catalog is invalid"
    }

    Write-Host ""
    Write-Host "Disaster Recovery Dashboard acceptance summary:"
    Write-Host "Status task: $($StatusTask.status)"
    Write-Host "Status tool: $($StatusTool.tool_name) $($StatusTool.status)"
    Write-Host "Pending tool: $($Pending.pending_confirmation.tool_name)"
    Write-Host "Pending risk: $($Pending.pending_confirmation.risk)"
    Write-Host "Cancelled task: $($Cancelled.status)"
    Write-Host "Cancelled tool calls:" @($Cancelled.tool_results).Count
    Write-Host "Invalid confirmation: HTTP" $InvalidConfirmation
    Write-Host "Confirmed task: $($Confirmed.status)"
    Write-Host "Backup ID: $($BackupTool.result.backup_id)"
    Write-Host "Files: $($BackupTool.result.file_count)"
    Write-Host "Bytes: $($BackupTool.result.bytes)"
    Write-Host "SQLite consistent: $($BackupTool.result.sqlite_consistent)"
    Write-Host "Credentials included: $($BackupTool.result.credentials_included)"
    Write-Host "Manifest SHA-256: $($BackupTool.result.manifest_sha256)"
    Write-Host "Public task steps: $($PublicTask.steps)"
    Write-Host "Duplicate confirmation: HTTP" $DuplicateConfirmation
    Write-Host "Verified backups: $($AfterTool.result.backup_count)"
    Write-Host "MCP read-only tools: $($McpTools.Count)"
    Write-Host "Dashboard recovery assets: ready"
    Write-Host "Disaster Recovery Dashboard smoke test passed."
}
finally {
    if ($Session -and $Headers) {
        if ($InitialMode -and $InitialMode -ne "offline") {
            try {
                $null = Invoke-JsonRequest -Method Put `
                    -Uri "$BaseUrl/api/v1/agent/model-mode" `
                    -Session $Session -Headers $Headers `
                    -Body @{mode = "online"; confirmation = "SWITCH_AGENT_MODEL"}
            }
            catch {
                Write-Warning "Could not restore the original remote model mode."
            }
        }
        try {
            $null = Invoke-JsonRequest -Method Post `
                -Uri "$BaseUrl/api/v1/auth/logout" `
                -Session $Session -Headers $Headers
        }
        catch {
            Write-Warning "Could not close the acceptance-test session."
        }
    }
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $PreviousCallback
    [System.Net.ServicePointManager]::SecurityProtocol = $PreviousSecurityProtocol
}
