[CmdletBinding()]
param(
    [string]$PortableRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")) "dist\ComSkip")
)

$ErrorActionPreference = "Stop"
$PortableRoot = (Resolve-Path -LiteralPath $PortableRoot).Path
$required = @(
    "comskip.exe",
    "ComskipGUI.exe",
    "comskip-final.exe",
    "ffmpeg.exe",
    "ffprobe.exe",
    "comskip.ini",
    "comskip.dictionary",
    "Makromodus-Sender.txt",
    "Schnellmodus-Sender.txt",
    "_Workflow\Werbung entfernen.py",
    "_Workflow\Werbung entfernen Start.bat",
    "_Workflow\Filme final schneiden.bat"
)

$missing = @($required | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $PortableRoot $_) -PathType Leaf)
})
if ($missing.Count) {
    throw "Portable runtime is incomplete: $($missing -join ', ')"
}

Push-Location $PortableRoot
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$smokeTemp = Join-Path (Split-Path -Parent $PortableRoot) "..\_temp\portable-smoke"
$smokeTemp = [System.IO.Path]::GetFullPath($smokeTemp)
New-Item -ItemType Directory -Force -Path $smokeTemp | Out-Null
$env:TEMP = $smokeTemp
$env:TMP = $smokeTemp
try {
    & ".\comskip-final.exe" --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "comskip-final.exe smoke test failed ($LASTEXITCODE)." }

    & ".\ffmpeg.exe" -version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg.exe smoke test failed ($LASTEXITCODE)." }

    & ".\ffprobe.exe" -version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "ffprobe.exe smoke test failed ($LASTEXITCODE)." }

    # Comskip returns a non-zero code for help/no-input on some revisions. A
    # successful process start is sufficient here to detect missing DLLs.
    $nativeOutput = & ".\comskip.exe" --help 2>&1
    if ($nativeOutput -match "The code execution cannot proceed|was not found") {
        throw "comskip.exe could not load a runtime dependency."
    }
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    Pop-Location
}

Write-Host "Portable smoke test passed: $PortableRoot"
