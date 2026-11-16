@echo off
setlocal
cd /d "%~dp0"
title NoGravity - Restore Original
call "%~dp0run_nogravity.bat" --revert
set "NG_EXIT=%errorlevel%"
echo.
pause
exit /b %NG_EXIT%
