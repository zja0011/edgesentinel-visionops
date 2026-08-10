$ErrorActionPreference = "Stop"

$ProjectDir = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)
$WheelDir = Join-Path $ProjectDir "vendor\wheels"
$Requirements = Join-Path $ProjectDir "requirements-api-py36.txt"

New-Item -ItemType Directory -Force -Path $WheelDir | Out-Null

Write-Host "Downloading the Python 3.6-compatible pip bootstrap..."
python -m pip download `
    --dest $WheelDir `
    --only-binary=:all: `
    --no-deps `
    --python-version 3.6.9 `
    pip==21.3.1

Write-Host "Downloading pure-Python API packages for CPython 3.6.9..."
python -m pip download `
    --dest $WheelDir `
    --only-binary=:all: `
    --platform manylinux2014_aarch64 `
    --python-version 3.6.9 `
    --implementation cp `
    --abi cp36m `
    fastapi==0.83.0 `
    uvicorn==0.16.0

Write-Host "Downloading dependencies selected only on Python 3.6..."
python -m pip download `
    --dest $WheelDir `
    --only-binary=:all: `
    --no-deps `
    --python-version 3.6.9 `
    contextlib2==21.6.0 `
    importlib-metadata==4.8.3 `
    zipp==3.6.0

Write-Host "Downloading Python 3.6 backports and the Jetson aarch64 wheel..."
python -m pip download `
    --dest $WheelDir `
    --only-binary=:all: `
    --no-deps `
    --platform manylinux2014_aarch64 `
    --python-version 3.6.9 `
    --implementation cp `
    --abi cp36m `
    dataclasses==0.8 `
    immutables==0.19

python -m pip download `
    --dest $WheelDir `
    --no-deps `
    contextvars==2.4

$ContextvarsSource = Join-Path $WheelDir "contextvars-2.4.tar.gz"
python -m pip wheel `
    --wheel-dir $WheelDir `
    --no-deps `
    $ContextvarsSource

$Missing = @()
$BootstrapPip = Get-ChildItem -LiteralPath $WheelDir -File |
    Where-Object { $_.Name -eq "pip-21.3.1-py3-none-any.whl" } |
    Select-Object -First 1
if (-not $BootstrapPip) {
    $Missing += "pip==21.3.1 (bootstrap)"
}

Get-Content -LiteralPath $Requirements |
    Where-Object { $_ -and -not $_.StartsWith("#") } |
    ForEach-Object {
        $PackageName = ($_ -split "==")[0].ToLower().Replace("-", "_")
        $Match = Get-ChildItem -LiteralPath $WheelDir -File |
            Where-Object {
                $_.Name.ToLower().Replace("-", "_").StartsWith(
                    $PackageName + "_"
                )
            } |
            Select-Object -First 1
        if (-not $Match) {
            $Missing += $_
        }
    }

if ($Missing.Count -gt 0) {
    throw "Offline package bundle is incomplete: $($Missing -join ', ')"
}

Write-Host ""
Write-Host "Offline API bundle is ready:"
Get-ChildItem -LiteralPath $WheelDir -File |
    Sort-Object Name |
    Select-Object Name, Length
