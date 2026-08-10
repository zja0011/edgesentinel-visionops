param(
    [string]$BaseUrl = "https://192.168.1.101:8443",
    [string]$Username = "zja",
    [string]$CertificatePath = ".\data\runtime\tls\edgesentinel-server.crt",
    [int]$HttpPort = 8000
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
if (-not ("EdgeSentinelCertificatePinning" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

public static class EdgeSentinelCertificatePinning
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
[EdgeSentinelCertificatePinning]::ExpectedFingerprint = `
    $script:ExpectedTlsFingerprint
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = `
    [EdgeSentinelCertificatePinning]::Callback

function Get-Status {
    param([string]$Uri, [Microsoft.PowerShell.Commands.WebRequestSession]$Session)
    try {
        $Response = Invoke-WebRequest -Uri $Uri -Method Get `
            -WebSession $Session -UseBasicParsing
        return [int]$Response.StatusCode
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

try {
    Write-Host "Checking certificate-pinned HTTPS Dashboard at $BaseUrl/dashboard"
    $Health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
    if (-not $Health.transport_security.tls_enabled -or
        -not $Health.transport_security.external_https_required -or
        -not $Health.authentication.cookie_secure) {
        throw "HTTPS health metadata is invalid"
    }
    $DashboardResponse = Invoke-WebRequest -Uri "$BaseUrl/dashboard" `
        -Method Get -UseBasicParsing
    if (-not $DashboardResponse.Headers["Strict-Transport-Security"] -or
        -not $DashboardResponse.Headers["Content-Security-Policy"] -or
        $DashboardResponse.Headers["X-Frame-Options"] -ne "DENY") {
        throw "HTTPS browser security headers are incomplete"
    }

    $HttpsUri = New-Object System.Uri($BaseUrl)
    $HttpBase = "http://$($HttpsUri.Host):$HttpPort"
    $RedirectRequest = [System.Net.HttpWebRequest]::Create("$HttpBase/dashboard")
    $RedirectRequest.AllowAutoRedirect = $false
    try {
        $RedirectResponse = $RedirectRequest.GetResponse()
    }
    catch [System.Net.WebException] {
        $RedirectResponse = $_.Exception.Response
    }
    $RedirectStatus = [int]$RedirectResponse.StatusCode
    $RedirectLocation = [string]$RedirectResponse.Headers["Location"]
    $RedirectResponse.Close()
    if ($RedirectStatus -ne 307 -or
        -not $RedirectLocation.StartsWith($BaseUrl)) {
        throw "External HTTP Dashboard did not redirect to pinned HTTPS"
    }

    $HttpApi = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $HttpApiStatus = Get-Status -Uri "$HttpBase/api/v1/system/status" -Session $HttpApi
    if ($HttpApiStatus -ne 426) {
        throw "External plaintext API was not rejected: HTTP $HttpApiStatus"
    }

    $Anonymous = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $AnonymousStatus = Get-Status -Uri "$BaseUrl/api/v1/system/status" -Session $Anonymous
    if ($AnonymousStatus -ne 401) {
        throw "Anonymous HTTPS API was not rejected: HTTP $AnonymousStatus"
    }

    $SecurePassword = Read-Host "Dashboard password for $Username" -AsSecureString
    $Credential = New-Object System.Management.Automation.PSCredential($Username, $SecurePassword)
    $PlainPassword = $Credential.GetNetworkCredential().Password
    $Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $Body = @{username = $Username; password = $PlainPassword} | ConvertTo-Json -Compress
    try {
        $Login = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/login" `
            -Method Post -WebSession $Session `
            -ContentType "application/json; charset=utf-8" `
            -Body $Utf8.GetBytes($Body)
    }
    finally {
        $PlainPassword = $null
        $Body = $null
    }
    $Cookie = $Session.Cookies.GetCookies($BaseUrl)["edgesentinel_session"]
    if (-not $Cookie -or -not $Cookie.HttpOnly -or -not $Cookie.Secure) {
        throw "HTTPS authentication cookie is not HttpOnly and Secure"
    }
    $Headers = @{"X-EdgeSentinel-CSRF" = [string]$Login.csrf_token}
    $Protected = Invoke-RestMethod -Uri "$BaseUrl/api/v1/system/status" `
        -Method Get -WebSession $Session
    if (-not $Protected) {
        throw "Authenticated HTTPS API is unavailable"
    }
    $PrivateKeyStatus = Get-Status `
        -Uri "$BaseUrl/api/v1/tls/private-key" -Session $Session
    if ($PrivateKeyStatus -ne 404) {
        throw "TLS private key endpoint is unexpectedly exposed"
    }
    $Logout = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/logout" `
        -Method Post -WebSession $Session -Headers $Headers

    Write-Host ""
    Write-Host "TLS Dashboard acceptance summary:"
    Write-Host "Status: PASS"
    Write-Host "Public origin:" $Health.transport_security.public_origin
    Write-Host "Pinned certificate SHA-256:" ($script:ExpectedTlsFingerprint.Substring(0, 16) + "...")
    Write-Host "HTTP Dashboard redirect: HTTP" $RedirectStatus
    Write-Host "Plaintext API rejected: HTTP" $HttpApiStatus
    Write-Host "Anonymous HTTPS API: HTTP" $AnonymousStatus
    Write-Host "Authenticated role:" $Login.role
    Write-Host "HttpOnly cookie:" $Cookie.HttpOnly
    Write-Host "Secure cookie:" $Cookie.Secure
    Write-Host "HSTS and CSP headers: ready"
    Write-Host "Private key API: HTTP" $PrivateKeyStatus
    Write-Host "Logout completed:" (-not $Logout.authenticated)
    Write-Host "TLS Dashboard smoke test passed."
}
finally {
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $PreviousCallback
    [System.Net.ServicePointManager]::SecurityProtocol = $PreviousSecurityProtocol
}
