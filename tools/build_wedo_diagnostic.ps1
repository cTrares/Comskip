[CmdletBinding()]
param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $repoRoot "_temp\wedo-diagnostic-build"
$sourceRoot = Join-Path $repoRoot "tools\hybrid_logo"
$portableRoot = Join-Path $repoRoot "dist\ComSkip"
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$previousConfig = $env:PYINSTALLER_CONFIG_DIR
$env:TEMP = $buildRoot
$env:TMP = $buildRoot
$env:PYINSTALLER_CONFIG_DIR = Join-Path $buildRoot "cache"
try {
    & $Python -B -c "import sys,unittest; sys.path.insert(0, sys.argv[1]); names=['test_wedo_fallback_diagnostic','test_video_end_bounds','test_wedo_sparse_mode','test_wedo_native_tail','test_wedo_movies_detector','test_wedo_movies_tail','test_comskip_final','test_commercial_macro_mode','test_public_broadcaster_fast_mode','test_hybrid_logo_analysis','test_internal_logo_parallel_score']; r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromNames(names)); sys.exit(not r.wasSuccessful())" $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw "Diagnostic regression tests failed." }
    & $Python -B -m PyInstaller --noconfirm --clean --onefile --name comskip-wedo-diagnose `
        --paths $sourceRoot --specpath $buildRoot --workpath (Join-Path $buildRoot "work") `
        --distpath $portableRoot (Join-Path $sourceRoot "wedo_fallback_diagnostic.py")
    if ($LASTEXITCODE -ne 0) { throw "Diagnostic build failed." }
    & (Join-Path $portableRoot "comskip-wedo-diagnose.exe") --version
    if ($LASTEXITCODE -ne 0) { throw "Diagnostic EXE did not start." }
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    $env:PYINSTALLER_CONFIG_DIR = $previousConfig
}
