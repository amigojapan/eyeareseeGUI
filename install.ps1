# EyeAreSee IRC Client Installer (PowerShell)

# Ensure execution policy for this process
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

Write-Host "=== EyeAreSee Installer ===" -ForegroundColor Cyan

# --- Check Python ---
$python = Get-Command python -ErrorAction SilentlyContinue

if (-not $python) {
    Write-Host "Python not found. Downloading..." -ForegroundColor Yellow

    $url = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
    $installer = "$env:TEMP\python_installer.exe"

    Invoke-WebRequest -Uri $url -OutFile $installer

    Write-Host "Installing Python..." -ForegroundColor Yellow
    Start-Process $installer -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait

    Remove-Item $installer -Force
}

Write-Host "✔ Python ready" -ForegroundColor Green

# --- Create venv ---
if (-Not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv venv
}

# --- Activate venv ---
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& ".\venv\Scripts\Activate.ps1"

# --- Upgrade pip ---
Write-Host "Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# --- Install dependencies ---
Write-Host "Installing dependencies..." -ForegroundColor Cyan

try {
    pip install PySide6 -ErrorAction Stop
    Write-Host "✔ Installed PySide6" -ForegroundColor Green
}
catch {
    Write-Host "PySide6 failed, trying PyQt6..." -ForegroundColor Yellow
    try {
        pip install PyQt6 -ErrorAction Stop
        Write-Host "✔ Installed PyQt6" -ForegroundColor Green
    }
    catch {
        Write-Host "PyQt6 failed, installing PyQt5..." -ForegroundColor Yellow
        pip install PyQt5
        Write-Host "✔ Installed PyQt5" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host ""

Write-Host "To run your client:" -ForegroundColor Cyan
Write-Host "-----------------------------------"
Write-Host ".\venv\Scripts\Activate.ps1"
Write-Host "python starteyeareseeGUI.py"
Write-Host "-----------------------------------"

Pause
