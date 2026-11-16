@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0NoGravity.exe" (
    "%~dp0NoGravity.exe" %*
    goto :EXE_DONE
)
set "NG_PY="
set "NG_PY_ARGS="
for /f "delims=" %%P in ('where py.exe 2^>nul') do call :TRY "%%P" "-3"
if not defined NG_PY for /f "delims=" %%P in ('where python.exe 2^>nul') do call :TRY "%%P" ""
if not defined NG_PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*" "%ProgramFiles%\Python*" "%ProgramFiles(x86)%\Python*") do call :TRY "%%~fD\python.exe" ""
if not defined NG_PY (
    echo [ERROR] Working Python 3.8+ was not found.
    echo Install Python from https://www.python.org/downloads/ and retry.
    exit /b 1
)
"%NG_PY%" %NG_PY_ARGS% "%~dp0nogravity.py" %*
exit /b %errorlevel%

:EXE_DONE
exit /b %errorlevel%

:TRY
if defined NG_PY exit /b
if not exist "%~1" exit /b
"%~1" %~2 -c "import sys;sys.exit(sys.version_info[:2] < (3,8))" >nul 2>&1
if errorlevel 1 exit /b
set "NG_PY=%~1"
set "NG_PY_ARGS=%~2"
exit /b
