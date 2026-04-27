@echo off
echo === IRC Client Installer (Windows) ===

REM Check if Python exists
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python not found. Downloading Python installer...
    powershell -Command "Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe -OutFile python_installer.exe"

    echo Installing Python... this may take a while
    start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0

    echo Cleaning up installer...
    del python_installer.exe
)

echo ✔ Python ready

REM Create venv
echo Creating virtual environment...
python -m venv venv

call venv\Scripts\activate

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing dependencies...

pip install PySide6
IF %ERRORLEVEL% NEQ 0 (
    echo PySide6 failed, trying PyQt6...
    pip install PyQt6
    IF %ERRORLEVEL% NEQ 0 (
        echo PyQt6 failed, trying PyQt5...
        pip install PyQt5
    )
)

echo.
echo Installation complete!
echo.
echo To run the client:
echo venv\Scripts\activate
echo python starteyeareseeGUI_urls.py
echo.

pause
