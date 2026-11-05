@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title NoGravity - Очистка конфликтующих служб и хуков

:: Check Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Запрос прав администратора...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: Locate Python adaptively
set "PY="
where py.exe >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%I in ('where py.exe 2^>nul') do if not defined PY set "PY=%%I -3"
)
if not defined PY (
    where python.exe >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "delims=" %%I in ('where python.exe 2^>nul') do if not defined PY set "PY=%%I"
    )
)
if not defined PY (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%ProgramFiles(x86)%\Python3*") do (
        if not defined PY if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
    )
)

if defined PY (
    %PY% "%~dp0nogravity.py" --clean
) else (
    echo [*] Python не найден, выполняю прямую аварийную очистку...
    taskkill /F /IM ag_dns.exe >nul 2>&1
    taskkill /F /IM AG_2.28.2.exe >nul 2>&1
    schtasks /delete /tn "AG Unlocker DNS" /f >nul 2>&1
    schtasks /delete /tn "AG Unlocker Watchdog" /f >nul 2>&1
    schtasks /delete /tn "NoVPN Antigravity Watchdog" /f >nul 2>&1
    reg delete "HKCU\Environment" /v "AG_LS_PROXY" /f >nul 2>&1
    reg delete "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v "AG_LS_PROXY" /f >nul 2>&1
    powershell -NoProfile -Command "Get-DnsClientNrptRule | Where-Object { $_.Comment -like '*AG_UNLOCKER*' -or $_.Namespace -contains 'cloudcode-pa.googleapis.com' } | Remove-DnsClientNrptRule -Force" >nul 2>&1
    echo [+] Очистка завершена напрямую.
)

echo.
pause