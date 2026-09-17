@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-nextread.ps1"
if errorlevel 1 (
    echo.
    echo Startup failed. Error details were saved to:
    echo %~dp0logs\launcher.log
    echo.
    pause
)

endlocal
