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

python --version



Write-Host "Creating virtual environment..." -ForegroundColor Cyan
python -m venv venv


.\venv\Scripts\Activate.ps1


	python -m pip install --upgrade pip


    pip install PySide6
    pip install qt_material
    
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "To run your client:" -ForegroundColor Cyan
Write-Host "-----------------------------------"
Write-Host "./runit.bat"
Write-Host "-----------------------------------"
