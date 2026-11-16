@echo off
setlocal
cd /d "%~dp0"
title NoGravity - Clean Conflicts
net session >nul 2>&1
if %errorlevel% neq 0 (
    set "NG_LAUNCHER=%~f0"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:NG_LAUNCHER -Verb RunAs"
    exit /b
)
call "%~dp0run_nogravity.bat" --clean
set "NG_EXIT=%errorlevel%"
echo.
pause
exit /b %NG_EXIT%
