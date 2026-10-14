@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Please complete the README setup steps.
) else (
    ".venv\Scripts\python.exe" -m scripts.check_setup
    echo.
    echo If all services are reachable, double-click start-nextread.cmd in File Explorer.
    echo If access is still denied, share these results with your computer administrator.
)
echo.
pause
endlocal
