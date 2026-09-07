@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py.exe >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0Werbung entfernen WeDo-Test.py"
  exit /b
)
where python.exe >nul 2>nul
if not errorlevel 1 (
  python "%~dp0Werbung entfernen WeDo-Test.py"
  exit /b
)
echo Python 3 wurde nicht gefunden.
pause
exit /b 2
