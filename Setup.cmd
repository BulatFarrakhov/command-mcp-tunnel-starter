@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0vm\windows\Prepare.ps1" %*
if errorlevel 1 (
  echo.
  echo Setup did not finish. See the error above. Press any key to close.
  pause >nul
  exit /b 1
)
echo.
echo Setup finished. Press any key to close.
pause >nul
