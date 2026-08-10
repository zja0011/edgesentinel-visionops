param(
    [ValidateSet("install", "status")]
    [string]$Action = "status",
    [string]$KeyDirectory = ""
)

$ErrorActionPreference = "Stop"
if (-not $KeyDirectory) {
    $KeyDirectory = Join-Path $env:LOCALAPPDATA "EdgeSentinel\recovery-sync"
}
$KeyDirectory = [IO.Path]::GetFullPath($KeyDirectory)
$PrivateKey = Join-Path $KeyDirectory "id_ed25519"
$PublicKey = "$PrivateKey.pub"
$Comment = "edgesentinel-recovery-sync"

function Assert-PrivateKeyAcl {
    if (-not (Test-Path -LiteralPath $PrivateKey -PathType Leaf)) {
        throw "Recovery synchronization private key is missing"
    }
    if ((Get-Item -LiteralPath $PrivateKey -Force).Attributes -band
        [IO.FileAttributes]::ReparsePoint) {
        throw "Recovery synchronization private key cannot be a reparse point"
    }
    $CurrentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $AllowedSids = @($CurrentSid, "S-1-5-18", "S-1-5-32-544")
    $CurrentIdentityFound = $false
    foreach ($Rule in (Get-Acl -LiteralPath $PrivateKey).Access) {
        try {
            $Sid = $Rule.IdentityReference.Translate(
                [Security.Principal.SecurityIdentifier]
            ).Value
        }
        catch {
            throw "Recovery synchronization private key ACL identity is invalid"
        }
        if ($Rule.AccessControlType -eq
            [Security.AccessControl.AccessControlType]::Allow) {
            if ($Sid -notin $AllowedSids) {
                throw "Recovery synchronization private key ACL is too broad"
            }
            if ($Sid -eq $CurrentSid) {
                $CurrentIdentityFound = $true
            }
        }
    }
    if (-not $CurrentIdentityFound) {
        throw "Recovery synchronization private key ACL excludes the current user"
    }
}

function Remove-GeneratedIdentity {
    if (Test-Path -LiteralPath $PrivateKey -PathType Leaf) {
        Remove-Item -LiteralPath $PrivateKey -Force
    }
    if (Test-Path -LiteralPath $PublicKey -PathType Leaf) {
        Remove-Item -LiteralPath $PublicKey -Force
    }
}

function Show-Status {
    $Installed = (Test-Path -LiteralPath $PrivateKey -PathType Leaf) -and
        (Test-Path -LiteralPath $PublicKey -PathType Leaf)
    Write-Host "Off-device recovery sync identity installed:" $Installed
    Write-Host "Private key:" $PrivateKey
    if ($Installed) {
        Assert-PrivateKeyAcl
        & ssh-keygen -lf $PublicKey
        if ($LASTEXITCODE -ne 0) {
            throw "Recovery synchronization public key is invalid"
        }
        Write-Host "Private key passphrase: none (restricted remote forced command)"
        Write-Host "Private key ACL: current user + SYSTEM + Administrators only"
        Write-Host "Private key exposed: False"
    }
}

if ($Action -eq "install") {
    if ((Test-Path -LiteralPath $PrivateKey) -or
        (Test-Path -LiteralPath $PublicKey)) {
        throw "Recovery synchronization identity already exists; refusing to overwrite"
    }
    New-Item -ItemType Directory -Force -Path $KeyDirectory | Out-Null
    # Windows PowerShell 5.1 drops a native-process empty-string argument.
    # A quoted empty string survives CommandLineToArgvW as ssh-keygen's -N value.
    & ssh-keygen -q -t ed25519 -N '""' -C $Comment -f $PrivateKey
    if ($LASTEXITCODE -ne 0) {
        Remove-GeneratedIdentity
        throw "Recovery synchronization identity generation failed"
    }
    $Account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls $PrivateKey /inheritance:r /grant:r "${Account}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Remove-GeneratedIdentity
        throw "Recovery synchronization private key permission hardening failed"
    }
    Assert-PrivateKeyAcl
    Write-Host "Dedicated off-device recovery sync identity installed."
    Write-Host "Private key:" $PrivateKey
    Write-Host "Public key:" $PublicKey
    Write-Host "Private key passphrase: none (remote access must use the forced command gate)"
    Write-Host "Private key exposed: False"
    Write-Host ""
    Write-Host "Next, copy only the public key to the Jetson:"
    Write-Host "scp `"$PublicKey`" nvidia@192.168.1.101:/home/nvidia/edgesentinel-recovery-sync.pub"
}
else {
    Show-Status
}
