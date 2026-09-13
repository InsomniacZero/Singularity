# ==============================================================================
# Universal-Gift - 1-Click Universal Windows Installer & Shortcut Setup
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "  🎁 Universal-Gift - Free Gemini Web2API Windows Installer 🎁" -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan

# 1. Check Python
Write-Host "[1/4] Checking Python..." -ForegroundColor Yellow
$hasPython = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $hasPython) {
    Write-Host "[!] Python is not installed or not in your PATH." -ForegroundColor Red
    Write-Host "Attempting automatic installation via winget..." -ForegroundColor Yellow
    try {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    } catch {
        Write-Host "[ERROR] Could not auto-install Python." -ForegroundColor Red
        Write-Host "Please install Python from https://www.python.org/downloads/ (check 'Add python.exe to PATH') and rerun this command." -ForegroundColor Red
        Read-Host "Press Enter to exit..."
        exit 1
    }
}

# 2. Download and extract repository
Write-Host "[2/4] Downloading latest files from GitHub..." -ForegroundColor Yellow
$dest = "$HOME\Universal-Gift"
if (Test-Path $dest) {
    Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
}

$zip = "$env:TEMP\gemini_gift_win.zip"
$extractTemp = "$env:TEMP\gemini_gift_extract"
if (Test-Path $extractTemp) { Remove-Item -Recurse -Force $extractTemp -ErrorAction SilentlyContinue }

Invoke-WebRequest -Uri "https://github.com/InsomniacZero/Universal-Gift/archive/refs/heads/main.zip" -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $extractTemp -Force
Move-Item "$extractTemp\Universal-Gift-main" $dest
Remove-Item -Recurse -Force $extractTemp, $zip -ErrorAction SilentlyContinue

# 3. Install Python dependencies
Write-Host "[3/4] Installing Python httpx library..." -ForegroundColor Yellow
python -m pip install httpx --quiet

# 4. Create 'gift' keyword shortcuts (PATH, PowerShell Profile, Desktop)
Write-Host "[4/4] Creating 'gift' shortcut command..." -ForegroundColor Yellow

# A. Create gift.bat inside the folder
$giftBat = "$dest\gift.bat"
"@echo off`r`ncall `"%~dp0start.bat`"" | Out-File -FilePath $giftBat -Encoding ascii

# B. Add folder to User PATH so CMD and PowerShell recognize 'gift'
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$dest*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dest", "User")
}
$env:Path += ";$dest"

# C. Add 'gift' function to PowerShell profile for instant terminal usage
try {
    if (!(Test-Path $PROFILE)) {
        New-Item -ItemType File -Path $PROFILE -Force | Out-Null
    }
    $profContent = Get-Content $PROFILE -ErrorAction SilentlyContinue | Out-String
    if ($profContent -notmatch "function gift") {
        Add-Content -Path $PROFILE -Value "`nfunction gift { & '$dest\start.bat' }"
    }
} catch {
    # Ignore profile write restrictions
}

# D. Create Desktop Shortcut
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("$HOME\Desktop\Universal-Gift.lnk")
    $Shortcut.TargetPath = "$dest\start.bat"
    $Shortcut.WorkingDirectory = "$dest"
    $Shortcut.Description = "Start Universal-Gift Gemini Web2API Proxy"
    $Shortcut.Save()
    Write-Host "[+] Created Desktop shortcut: Universal-Gift" -ForegroundColor Green
} catch {
    # Desktop shortcut is optional
}

Write-Host ""
Write-Host "===================================================================" -ForegroundColor Green
Write-Host "  INSTALLATION COMPLETE! YOU'RE READY TO USE GEMINI ANYWHERE!" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Green
Write-Host "From now on, whenever you want to start the proxy, just open" -ForegroundColor White
Write-Host "PowerShell or CMD and type:" -ForegroundColor White
Write-Host ""
Write-Host "    gift" -ForegroundColor Yellow
Write-Host ""
Write-Host "and press Enter!" -ForegroundColor White
Write-Host "===================================================================" -ForegroundColor Green
Write-Host ""

$startNow = Read-Host "Would you like to start the server right now? (Y/N)"
if ($startNow -match "^[Yy]$") {
    & "$dest\start.bat"
}
