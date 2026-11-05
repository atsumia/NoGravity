@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title NoGravity - Autonomous Doctor & Environment Patcher

:: Check Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Запрос прав администратора...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: Locate Python adaptively on any PC
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

if not defined PY (
    color 0C
    echo.
    echo ======================================================================
    echo  [ОШИБКА] Python 3 не обнаружен на этом компьютере!
    echo ======================================================================
    echo  Для работы NoGravity требуется установленный Python 3 (3.8+).
    echo.
    echo  Быстрая установка через Windows Terminal / PowerShell:
    echo      winget install Python.Python.3.11
    echo.
    echo  Или скачайте с официального сайта:
    echo      https://www.python.org/downloads/
    echo ======================================================================
    echo.
    pause
    exit /b 1
)

:: Run NoGravity Interactive Engine
%PY% "%~dp0nogravity.py" %*

if %errorlevel% neq 0 (
    echo.
    echo [!] Программа завершилась с кодом: %errorlevel%
    pause
)