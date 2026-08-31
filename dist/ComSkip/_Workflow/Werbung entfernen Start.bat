@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py.exe >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0Werbung entfernen.py"
  exit /b %errorlevel%
)
where python.exe >nul 2>nul
if not errorlevel 1 (
  python "%~dp0Werbung entfernen.py"
  exit /b %errorlevel%
)
echo Python 3 wurde nicht gefunden.
pause
exit /b 2
