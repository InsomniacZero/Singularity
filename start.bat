@echo off
setlocal enabledelayedexpansion
title Singularity Unified AI Gateway

:: Resolve root and singularity directories (always quoted)
set "ROOT_DIR=%~dp0"
set "SING_DIR=%ROOT_DIR%singularity"

:: 1. Detect Python Executable
set "PYTHON_EXE="
set "PYTHON_ARGS="

:: Check if local virtualenv python already exists
if exist "%SING_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%SING_DIR%\.venv\Scripts\python.exe"
    goto :PYTHON_FOUND
)

:: Check for 'py -3' Windows launcher
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
    goto :PYTHON_FOUND
)

:: Check for system 'python'
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :PYTHON_FOUND
)

:: Check standard Windows user installation directories
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :PYTHON_FOUND
    )
)

:: Check Program Files installation directories
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :PYTHON_FOUND
    )
)

:PYTHON_NOT_FOUND
echo ======================================================================
echo  [ERROR] Python 3.10+ was not found on your Windows system!
echo ======================================================================
echo.
echo  Singularity requires Python to run.
echo  1. Download Python from: https://www.python.org/downloads/
echo  2. IMPORTANT: During setup, check the box:
echo     [x] "Add python.exe to PATH"
echo  3. Restart Command Prompt or double-click start.bat again.
echo.
echo ======================================================================
pause
exit /b 1

:PYTHON_FOUND
cd /d "%SING_DIR%"
set "PYTHONPATH=%ROOT_DIR%;%SING_DIR%;%PYTHONPATH%"

:: 2. Check / Setup Virtual Environment
if not exist "%SING_DIR%\.venv\Scripts\python.exe" (
    echo [*] Initializing virtual environment in singularity\.venv...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv "%SING_DIR%\.venv"
    if exist "%SING_DIR%\.venv\Scripts\python.exe" (
        set "PYTHON_EXE=%SING_DIR%\.venv\Scripts\python.exe"
        set "PYTHON_ARGS="
    )
) else (
    set "PYTHON_EXE=%SING_DIR%\.venv\Scripts\python.exe"
    set "PYTHON_ARGS="
)

:: Verify dependencies
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import starlette, uvicorn, httpx, curl_cffi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing required Singularity dependencies from requirements.txt...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%ROOT_DIR%requirements.txt"
    if %errorlevel% neq 0 (
        echo.
        echo ======================================================================
        echo  [!] Dependency installation failed.
        echo  Please verify your internet connection or run:
        echo  pip install -r requirements.txt
        echo ======================================================================
        echo.
        pause
        exit /b 1
    )
)

:: 3. Route CLI subcommands vs Gateway Server
set "ARG1=%~1"

if "%ARG1%"=="status" goto :RUN_CLI
if "%ARG1%"=="limits" goto :RUN_CLI
if "%ARG1%"=="accounts" goto :RUN_CLI
if "%ARG1%"=="import" goto :RUN_CLI
if "%ARG1%"=="export" goto :RUN_CLI
if "%ARG1%"=="simulate" goto :RUN_CLI
if "%ARG1%"=="host" goto :RUN_CLI
if "%ARG1%"=="chat" goto :RUN_CLI
if "%ARG1%"=="thinking" goto :RUN_CLI
if "%ARG1%"=="service" goto :RUN_CLI
if "%ARG1%"=="-h" goto :RUN_CLI
if "%ARG1%"=="--help" goto :RUN_CLI
if "%ARG1%"=="help" goto :RUN_CLI

:: Launch Gateway Server
cls
echo ======================================================================
echo   SINGULARITY UNIFIED AI GATEWAY & TAVERN (Windows)
echo ======================================================================
echo   Dashboard:       http://localhost:9000
echo   Tavern Studio:   http://localhost:5173
echo   API Base:        http://localhost:9000/v1
echo   Phone / Remote:  http://^<YOUR_PC_IP^>:5173 (Check Wi-Fi IP)
echo   NOTE: Do NOT type 0.0.0.0 on phones - always use your PC's LAN IP!
echo ======================================================================
echo.

:: Launch Tavern Studio alongside Singularity if present
set "TAV_DIR="
if exist "%ROOT_DIR%TAVERN\package.json" (
    set "TAV_DIR=%ROOT_DIR%TAVERN"
) else if exist "%ROOT_DIR%TAV-TEST\package.json" (
    set "TAV_DIR=%ROOT_DIR%TAV-TEST"
)

if defined TAV_DIR (
    echo [*] Starting Tavern Studio alongside Singularity (ports 5173 / 3001)...
    start "Tavern Studio" /min cmd /c "cd /d "!TAV_DIR!" && set API_HOST=0.0.0.0&& set RP_ALLOWED_ORIGINS=*&& if not exist node_modules npm install && npm run dev"
)

"%PYTHON_EXE%" %PYTHON_ARGS% server.py %*
goto :AFTER_RUN

:RUN_CLI
"%PYTHON_EXE%" %PYTHON_ARGS% cli.py %*

:AFTER_RUN
set "EXIT_CODE=%errorlevel%"
if %EXIT_CODE% neq 0 (
    echo.
    echo [!] Singularity process ended with exit code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
