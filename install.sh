#!/usr/bin/env bash

set -e

echo "=== IRC Client Installer ==="

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3.8+"
    exit 1
fi

echo "✔ Python found: $(python3 --version)"

echo "📦 Creating virtual environment..."
python3 -m venv venv

echo "⚙️ Activating virtual environment..."
source venv/bin/activate

echo "⬆️ Upgrading pip..."
pip install --upgrade pip

echo "📥 Installing dependencies..."

if pip install PySide6; then
    echo "✔ Installed PySide6"
else
    echo "⚠️ PySide6 failed, trying PyQt6..."
    if pip install PyQt6; then
        echo "✔ Installed PyQt6"
    else
        echo "⚠️ PyQt6 failed, trying PyQt5..."
        pip install PyQt5
        echo "✔ Installed PyQt5"
    fi
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "To run the client:"
echo "-----------------------------------"
echo "./runit.bash"
echo "-----------------------------------"
