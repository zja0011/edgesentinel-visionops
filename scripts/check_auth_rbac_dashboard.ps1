param(
    [string]$BaseUrl = "http://192.168.1.101:8000",
    [string]$Username = "admin"
)

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$BaseUrl = $BaseUrl.TrimEnd("/")

function Get-HttpStatus {
    param(
        [string]$Method,
        [string]$Uri,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        [hashtable]$Headers,
        [string]$Body
    )
    try {
        $Arguments = @{
            Uri = $Uri
            Method = $Method
            WebSession = $Session
            UseBasicParsing = $true
        }
        if ($Headers) { $Arguments.Headers = $Headers }
        if ($Body) {
            $Arguments.Body = $Utf8.GetBytes($Body)
            $Arguments.ContentType = "application/json; charset=utf-8"
        }
        $Response = Invoke-WebRequest @Arguments
        return [int]$Response.StatusCode
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

Write-Host "Checking Dashboard authentication and RBAC at $BaseUrl/dashboard"

try {
    $Health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
}
catch [System.Net.WebException] {
    if ($_.Exception.Response -and
        [int]$_.Exception.Response.StatusCode -eq 503) {
        throw "Service is degraded because authentication is not ready. Run configure_auth_boot.sh install with a new 12+ character password, then restart the service."
    }
    throw
}
if (-not $Health.authentication.enabled -or -not $Health.authentication.ready) {
    throw "Authentication is not enabled and ready"
}
if ($Health.authentication.credentials_exposed) {
    throw "Authentication health metadata exposed credentials"
}

$Anonymous = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$AnonymousStatus = Get-HttpStatus -Method "GET" `
    -Uri "$BaseUrl/api/v1/system/status" -Session $Anonymous
if ($AnonymousStatus -ne 401) {
    throw "Unauthenticated API request was not rejected: HTTP $AnonymousStatus"
}

$Invalid = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$InvalidBody = @{username = $Username; password = "definitely-invalid-password"} |
    ConvertTo-Json -Compress
$InvalidStatus = Get-HttpStatus -Method "POST" `
    -Uri "$BaseUrl/api/v1/auth/login" -Session $Invalid -Body $InvalidBody
if ($InvalidStatus -ne 401) {
    throw "Invalid login was not rejected: HTTP $InvalidStatus"
}

$SecurePassword = Read-Host "Dashboard password for $Username" -AsSecureString
$Credential = New-Object System.Management.Automation.PSCredential(
    $Username,
    $SecurePassword
)
$PlainPassword = $Credential.GetNetworkCredential().Password
$Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$LoginBody = @{username = $Username; password = $PlainPassword} |
    ConvertTo-Json -Compress
try {
    $Login = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/login" `
        -Method Post -WebSession $Session `
        -ContentType "application/json; charset=utf-8" `
        -Body $Utf8.GetBytes($LoginBody)
}
finally {
    $PlainPassword = $null
    $LoginBody = $null
}

if (-not $Login.authenticated -or $Login.role -ne "admin") {
    throw "The authenticated administrator session is invalid"
}
$Cookie = $Session.Cookies.GetCookies($BaseUrl)["edgesentinel_session"]
if (-not $Cookie -or -not $Cookie.HttpOnly) {
    throw "The HttpOnly authentication cookie is missing"
}
$Csrf = [string]$Login.csrf_token
if ([string]::IsNullOrWhiteSpace($Csrf)) {
    throw "The CSRF token is missing"
}

$MissingCsrf = Get-HttpStatus -Method "POST" `
    -Uri "$BaseUrl/api/v1/agent/sessions" -Session $Session
if ($MissingCsrf -ne 403) {
    throw "Mutation without CSRF was not rejected: HTTP $MissingCsrf"
}

$Headers = @{"X-EdgeSentinel-CSRF" = $Csrf; Accept = "application/json"}
$SessionCreate = Invoke-RestMethod -Uri "$BaseUrl/api/v1/agent/sessions" `
    -Method Post -WebSession $Session -Headers $Headers
if (-not $SessionCreate.session_id) {
    throw "Authenticated mutation did not complete"
}

$AuditStatus = Get-HttpStatus -Method "GET" `
    -Uri "$BaseUrl/api/v1/auth/audit" -Session $Session
if ($AuditStatus -ne 404) {
    throw "The authentication audit file API is unexpectedly exposed"
}

$Dashboard = (Invoke-WebRequest -Uri "$BaseUrl/dashboard" -UseBasicParsing).Content
$Javascript = (Invoke-WebRequest `
    -Uri "$BaseUrl/dashboard/assets/dashboard.js" -UseBasicParsing).Content
if ($Dashboard -notmatch 'id="auth-login-form"' -or
    $Dashboard -notmatch 'id="auth-logout"' -or
    $Javascript -notmatch 'initializeAuthentication' -or
    $Javascript -notmatch 'X-EdgeSentinel-CSRF') {
    throw "Dashboard authentication assets are incomplete"
}

$Logout = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/logout" `
    -Method Post -WebSession $Session -Headers $Headers
if ($Logout.authenticated) {
    throw "Logout response is invalid"
}
$AfterLogout = Get-HttpStatus -Method "GET" `
    -Uri "$BaseUrl/api/v1/system/status" -Session $Session
if ($AfterLogout -ne 401) {
    throw "The logged-out session remained usable: HTTP $AfterLogout"
}

Write-Host ""
Write-Host "Authentication and RBAC acceptance summary:"
Write-Host "Authentication enabled:" $Health.authentication.enabled
Write-Host "Authentication ready:" $Health.authentication.ready
Write-Host "Configured roles:" ($Health.authentication.configured_roles -join ", ")
Write-Host "Anonymous API: HTTP" $AnonymousStatus
Write-Host "Invalid login: HTTP" $InvalidStatus
Write-Host "Authenticated role:" $Login.role
Write-Host "HttpOnly cookie:" $Cookie.HttpOnly
Write-Host "CSRF required: True"
Write-Host "Missing CSRF: HTTP" $MissingCsrf
Write-Host "Authenticated mutation: SUCCEEDED"
Write-Host "Audit file API: HTTP" $AuditStatus
Write-Host "Logout invalidated session: True"
Write-Host "Dashboard login assets: ready"
Write-Host "Authentication and RBAC smoke test passed."
