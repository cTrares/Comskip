[CmdletBinding()]
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $repoRoot "_temp\wedo-test-build"
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
    & $Python -B -c "import sys,unittest; sys.path.insert(0, sys.argv[1]); names=['test_video_end_bounds','test_wedo_sparse_mode','test_wedo_native_tail','test_wedo_movies_detector','test_wedo_movies_tail','test_comskip_final','test_commercial_macro_mode','test_public_broadcaster_fast_mode','test_hybrid_logo_analysis','test_internal_logo_parallel_score']; result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromNames(names)); sys.exit(not result.wasSuccessful())" $sourceRoot
    if ($LASTEXITCODE -ne 0) { throw "WeDo regression tests failed." }
    & $Python -B -m PyInstaller --noconfirm --clean --onefile --name comskip-wedo-test `
        --paths $sourceRoot --specpath $buildRoot --workpath (Join-Path $buildRoot "work") `
        --distpath $portableRoot (Join-Path $sourceRoot "comskip_final.py")
    if ($LASTEXITCODE -ne 0) { throw "WeDo test build failed." }
    & (Join-Path $portableRoot "comskip-wedo-test.exe") --version
    if ($LASTEXITCODE -ne 0) { throw "WeDo test executable did not start." }
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    $env:PYINSTALLER_CONFIG_DIR = $previousConfig
}
Write-Host "Separate test EXE: $portableRoot\comskip-wedo-test.exe"
