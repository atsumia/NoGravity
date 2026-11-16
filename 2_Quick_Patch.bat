@echo off
setlocal
cd /d "%~dp0"
title NoGravity - Local Patch
call "%~dp0run_nogravity.bat" --apply
set "NG_EXIT=%errorlevel%"
echo.
pause
exit /b %NG_EXIT%
