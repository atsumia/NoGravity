@echo off
setlocal
cd /d "%~dp0"
title NoGravity - Clean Conflicts

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

echo [*] Cleaning conflicting hooks and daemons...
taskkill /F /IM ag_dns.exe >nul 2>&1
taskkill /F /IM AG_2.28.2.exe >nul 2>&1
schtasks /delete /tn "AG Unlocker DNS" /f >nul 2>&1
schtasks /delete /tn "AG Unlocker Watchdog" /f >nul 2>&1
schtasks /delete /tn "NoVPN Antigravity Watchdog" /f >nul 2>&1
reg delete "HKCU\Environment" /v "AG_LS_PROXY" /f >nul 2>&1
reg delete "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v "AG_LS_PROXY" /f >nul 2>&1
powershell -NoProfile -Command "Get-DnsClientNrptRule | Where-Object { $_.Namespace -like '*googleapis.com*' -or $_.IPsecCARestriction -like '*127.0.0.53*' } | Remove-DnsClientNrptRule -Force" >nul 2>&1
echo [+] Cleanup complete.
echo.
pause
exit /b 0

:RUN
%PY% "%~dp0nogravity.py" --clean
echo.
pause
exit /b %errorlevel%