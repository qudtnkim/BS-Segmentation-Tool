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

python -c "import cv2" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] OpenCV is missing. Installing...
    pip install opencv-python
)

python -c "import whisper" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Whisper is missing. Installing...
    pip install openai-whisper soundfile
)

REM SAM 2(segment-anything-2)는 자동 설치 대상이 아니며, 없으면 수동 주석 모드로 동작합니다.

REM 3. Open Browser
echo [INFO] Opening browser to http://localhost:5000 ...
start http://localhost:5000

REM 4. Run Server
echo [INFO] Running Flask Backend server...
python app.py

pause
