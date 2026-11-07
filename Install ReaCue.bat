@echo off
rem Double-clic pour installer ReaCue (Windows). / Double-click to install ReaCue (Windows).
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\install_windows.ps1" %*
set "REACUE_EXIT_CODE=%ERRORLEVEL%"
echo.
pause
exit /b %REACUE_EXIT_CODE%
