<#
.SYNOPSIS
    Singularity Unified AI Gateway Launcher for Windows PowerShell
.DESCRIPTION
    Launches the Singularity server daemon or CLI on Windows with automatic
    Python detection, virtual environment setup, and dependency management.
#>

param (
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$SingularityDir = Join-Path $Root "singularity"
$VenvPython = Join-Path $SingularityDir ".venv\Scripts\python.exe"

# 1. Locate Python Executable
$PythonCmd = $null

if (Test-Path $VenvPython) {
    $PythonCmd = $VenvPython
} else {
    # Check py launcher, python, python3
    foreach ($cand in @("py", "python", "python3")) {
        $found = Get-Command $cand -ErrorAction SilentlyContinue
        if ($found) {
            $PythonCmd = $found.Source
            break
        }
    }
}

if (-not $PythonCmd) {
    Write-Host "======================================================================" -ForegroundColor Red
    Write-Host " [ERROR] Python 3.10+ was not found on your Windows system!" -ForegroundColor Red
    Write-Host "======================================================================" -ForegroundColor Red
    Write-Host " Please install Python from: https://www.python.org/downloads/"
    Write-Host " IMPORTANT: During installation, make sure to check:"
    Write-Host "   [x] Add python.exe to PATH" -ForegroundColor Yellow
    Write-Host "======================================================================" -ForegroundColor Red
    Read-Host "Press Enter to exit..."
    exit 1
}

# 2. Virtual Environment & Dependencies Setup
Set-Location $SingularityDir

if (-not (Test-Path $VenvPython)) {
    Write-Host "[*] Initializing virtual environment in singularity\.venv..." -ForegroundColor Cyan
    & $PythonCmd -m venv (Join-Path $SingularityDir ".venv")
    if (Test-Path $VenvPython) {
        $PythonCmd = $VenvPython
    }
}

# Verify required packages
$testDep = & $PythonCmd -c "import starlette, uvicorn, httpx" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[*] Installing dependencies from requirements.txt..." -ForegroundColor Cyan
    $reqFile = Join-Path $Root "requirements.txt"
    & $PythonCmd -m pip install -r $reqFile
}

# 3. Route Commands vs Gateway Server
$firstArg = if ($ScriptArgs.Count -gt 0) { $ScriptArgs[0] } else { "" }
$cliCommands = @("status", "limits", "accounts", "import", "export", "simulate", "host", "chat", "service", "-h", "--help", "help")

if ($cliCommands -contains $firstArg) {
    & $PythonCmd (Join-Path $SingularityDir "cli.py") @ScriptArgs
} else {
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "   SINGULARITY UNIFIED AI GATEWAY (Windows)" -ForegroundColor Green
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "   Dashboard:  http://localhost:9000" -ForegroundColor White
    Write-Host "   API Base:   http://localhost:9000/v1" -ForegroundColor White
    Write-Host "   Providers:  ChatGPT, Claude, Gemini, Grok, Kimi, GLM" -ForegroundColor Gray
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host ""
    
    & $PythonCmd (Join-Path $SingularityDir "server.py") @ScriptArgs
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[!] Singularity exited with code $LASTEXITCODE." -ForegroundColor Yellow
    Read-Host "Press Enter to close..."
}
