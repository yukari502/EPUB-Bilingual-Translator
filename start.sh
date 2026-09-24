#!/bin/bash
echo "=============================================="
echo "EPUB Translator - One-Click Launcher (Linux)"
echo "=============================================="

PYTHON_EXE="python3"

# Check if Python is installed
if ! command -v $PYTHON_EXE &> /dev/null
then
    echo "[ERROR] Python 3 is not installed or not in PATH."
    echo "Please install Python 3 (e.g., sudo apt install python3 python3-venv)"
    exit 1
fi

echo "[INFO] System Python detected."

if [ ! -d ".venv" ]; then
    echo "[1/3] Creating virtual environment..."
    $PYTHON_EXE -m venv .venv
else
    echo "[1/3] Virtual environment already exists."
fi

echo "[2/3] Activating virtual environment and checking dependencies..."
source .venv/bin/activate

pip install --upgrade pip
pip install -e .
pip install fastapi uvicorn httpx python-multipart websockets bs4 pydantic pydantic-core

echo "=============================================="
echo "[INFO] Starting EPUB Translator Web UI..."
echo "=============================================="
python -m epub_translator.web_server
