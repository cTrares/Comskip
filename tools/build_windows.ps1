[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Msys2Root = "C:\msys64",
    [switch]$SkipNative,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$temporaryRoot = Join-Path $repoRoot "_temp\reproducible-build"
$venvRoot = Join-Path $temporaryRoot "python"
$bash = Join-Path $Msys2Root "usr\bin\bash.exe"

if (-not $SkipNative) {
    if (-not (Test-Path -LiteralPath $bash -PathType Leaf)) {
        throw "MSYS2 bash not found: $bash"
    }

    $env:MSYSTEM = "MINGW64"
    $env:CHERE_INVOKING = "1"
    Push-Location $repoRoot
    try {
        & $bash -lc "./autogen.sh && ./configure && make -j2"
        if ($LASTEXITCODE -ne 0) { throw "Native build failed ($LASTEXITCODE)." }
    }
    finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
& $Python -m venv $venvRoot
if ($LASTEXITCODE -ne 0) { throw "Could not create Python build environment." }

$buildPython = Join-Path $venvRoot "Scripts\python.exe"
& $buildPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }
& $buildPython -m pip install -r (Join-Path $repoRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Could not install Python build requirements." }

if (-not $SkipTests) {
    Push-Location (Join-Path $repoRoot "tools\hybrid_logo")
    try {
        & $buildPython -m unittest discover -p "test_*.py"
        if ($LASTEXITCODE -ne 0) { throw "Python tests failed ($LASTEXITCODE)." }
    }
    finally {
        Pop-Location
    }
}

$pythonDist = Join-Path $temporaryRoot "python-dist"
$pythonWork = Join-Path $temporaryRoot "python-work"
Push-Location (Join-Path $repoRoot "tools\hybrid_logo")
try {
    & $buildPython -m PyInstaller --noconfirm --clean `
        --distpath $pythonDist --workpath $pythonWork comskip-final-v4.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed ($LASTEXITCODE)." }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath (Join-Path $pythonDist "comskip-final.exe") -PathType Leaf)) {
    throw "PyInstaller did not create comskip-final.exe."
}

if (-not $SkipNative) {
    Push-Location $repoRoot
    try {
        & $bash (Join-Path $repoRoot "tools\package_windows_mingw.sh") `
            (Join-Path $pythonDist "comskip-final.exe")
        if ($LASTEXITCODE -ne 0) { throw "Portable packaging failed ($LASTEXITCODE)." }
    }
    finally {
        Pop-Location
    }
}

Write-Host "Build completed. Portable output: $repoRoot\dist\ComSkip"
