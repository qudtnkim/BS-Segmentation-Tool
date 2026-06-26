@echo off
chcp 65001 >nul
title BS Segmentation Tool - Runner
echo ==========================================================
echo Starting BS Segmentation Tool with Local STT Engine...
echo ==========================================================

REM 1. Python Check
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python and try again.
    pause
    exit /b
)

REM 2. Dependencies Check
python -c "import flask" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Flask is missing. Installing...
    pip install Flask
)

python -c "import pandas" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Pandas is missing. Installing...
    pip install pandas openpyxl
)

python -c "import whisper" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Whisper is missing. Installing...
    pip install openai-whisper soundfile
)

REM 3. Open Browser
echo [INFO] Opening browser to http://localhost:5000 ...
start http://localhost:5000

REM 4. Run Server
echo [INFO] Running Flask Backend server...
python app.py

pause