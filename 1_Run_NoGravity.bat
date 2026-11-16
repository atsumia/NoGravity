@echo off
setlocal
cd /d "%~dp0"
title NoGravity - Antigravity Doctor
call "%~dp0run_nogravity.bat" %*
set "NG_EXIT=%errorlevel%"
if not "%NG_EXIT%"=="0" pause
exit /b %NG_EXIT%
