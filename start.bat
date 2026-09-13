@echo off
title Universal-Gift - Free Gemini Web2API Proxy
color 0B
cd /d "%~dp0"

echo =========================================================================
echo       🎁 Universal-Gift - Free Gemini Web2API Proxy 🎁
echo =========================================================================
echo   [+] Checking Python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in your PATH!
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo   [+] Starting Universal-Gift on http://localhost:8045/v1 ...
echo =========================================================================
echo   API Base URL:       http://localhost:8045/v1
echo   Chat Completions:   http://localhost:8045/v1/chat/completions
echo   Models List:        http://localhost:8045/v1/models
echo   Default Model:      gemini-3.8-flash
echo   Flagship Pro:       gemini-3.1-pro or gemini-3.1-pro-extended
echo   API Key:            Any text (or leave blank)
echo =========================================================================
echo   Ready to connect in Cursor, Open WebUI, LibreChat, Python, or cURL!
echo   Press Ctrl+C to stop the server.
echo =========================================================================
echo.

python gemini_web2api.py --port 8045 %*
pause
