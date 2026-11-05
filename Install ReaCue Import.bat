@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\install_import_windows.ps1"
set "rc=%errorlevel%"
pause
exit /b %rc%
