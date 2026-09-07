@echo off
setlocal EnableExtensions
"%~dp0..\comskip-wedo-diagnose.exe" %*
set "diagResult=%errorlevel%"
echo.
pause
exit /b %diagResult%
