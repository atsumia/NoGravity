@echo off
setlocal
cd /d "%~dp0"
title NoGravity - Antigravity Doctor

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "PY="
where py.exe >nul 2>&1 && for /f "delims=" %%i in ('where py.exe 2^>nul') do if not defined PY set "PY=%%i -3"
if defined PY goto :RUN

where python.exe >nul 2>&1 && for /f "delims=" %%i in ('where python.exe 2^>nul') do if not defined PY set "PY=%%i"
if defined PY goto :RUN

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto :RUN
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe" & goto :RUN
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe" & goto :RUN
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe" & goto :RUN
if exist "%ProgramFiles%\Python311\python.exe" set "PY=%ProgramFiles%\Python311\python.exe" & goto :RUN
if exist "%ProgramFiles%\Python310\python.exe" set "PY=%ProgramFiles%\Python310\python.exe" & goto :RUN
if exist "%ProgramFiles%\Python312\python.exe" set "PY=%ProgramFiles%\Python312\python.exe" & goto :RUN
if exist "%ProgramFiles%\Python313\python.exe" set "PY=%ProgramFiles%\Python313\python.exe" & goto :RUN

color 0C
echo.
echo ======================================================================
echo  [ERROR] Python 3 was not detected on this system!
echo ======================================================================
echo  NoGravity requires Python 3 (3.8 or newer).
echo  Install it via Windows Terminal / PowerShell:
echo      winget install Python.Python.3.11
echo  Or download from: https://www.python.org/downloads/
echo ======================================================================
echo.
pause
exit /b 1

:RUN
%PY% "%~dp0nogravity.py" %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Process exited with code: %errorlevel%
    pause
)
exit /b %errorlevel%