@echo off
setlocal enabledelayedexpansion
title Tavern Web Studio
cd /d "%~dp0"

:: Tavern's API has no login: loopback only unless the caller set API_HOST [start.bat --lan does].
if not defined API_HOST set "API_HOST=127.0.0.1"

:: Check if Node or Bun is installed
where bun >nul 2>&1
if %errorlevel% equ 0 (
    set "RUNNER=bun"
) else (
    where node >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Node.js or Bun is required to run Tavern Studio.
        echo Please install Node.js [v22+] from https://nodejs.org
        pause
        exit /b 1
    )
    set "RUNNER=npm"
)

:: First-time dependency install
if not exist "node_modules" (
    echo ======================================================================
    echo   [TAVERN] Installing dependencies [first-time setup]...
    echo   This may take 1-2 minutes. Please keep this window open!
    echo ======================================================================
    if "!RUNNER!"=="bun" (
        call bun install
    ) else (
        call npm install
    )
    if errorlevel 1 (
        echo [!] Dependency installation failed.
        pause
        exit /b 1
    )
    echo [*] Dependencies installed successfully!
)

echo ======================================================================
echo   [TAVERN] Starting dev server on http://localhost:5173 ...
echo ======================================================================
if "!RUNNER!"=="bun" (
    call bun run dev
) else (
    call npm run dev
)
if errorlevel 1 (
    echo [!] Tavern server stopped with an error. Check logs above.
    pause
)
