@echo off
title BS Segmentation Tool
echo ===========================================================
echo  BS Segmentation Tool Setup and Launcher
echo ===========================================================
echo.

REM ---- 1. Python check
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH.
    echo   Install Python 3.10+ from https://www.python.org/
    echo   Check 'Add Python to PATH' during install.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% found.
echo.

REM ---- 2. Upgrade pip + setuptools first (prevents resolver conflicts)
echo [INFO] Upgrading pip and setuptools...
python -m pip install --upgrade pip setuptools wheel -q
echo [OK] pip / setuptools / wheel
echo.

REM ---- 3. Flask
python -c "import flask" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INSTALL] Flask...
    python -m pip install Flask -q
    if %errorlevel% neq 0 (
        echo [ERROR] Flask install failed.
        pause
        exit /b 1
    )
)
echo [OK] Flask

REM ---- 4. pandas
python -c "import pandas, openpyxl" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INSTALL] pandas + openpyxl...
    python -m pip install pandas openpyxl -q
    if %errorlevel% neq 0 (
        echo [ERROR] pandas install failed.
        pause
        exit /b 1
    )
)
echo [OK] pandas

REM ---- 5. OpenCV
python -c "import cv2" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INSTALL] OpenCV...
    python -m pip install opencv-python -q
    if %errorlevel% neq 0 (
        echo [ERROR] OpenCV install failed.
        pause
        exit /b 1
    )
)
echo [OK] OpenCV

REM ---- 6. PyTorch CPU
python -c "import torch" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INSTALL] PyTorch CPU... this may take a few minutes.
    python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu -q
    if %errorlevel% neq 0 (
        echo [ERROR] PyTorch install failed.
        pause
        exit /b 1
    )
)
echo [OK] PyTorch

REM ---- 7. Whisper
python -c "import whisper" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INSTALL] openai-whisper + soundfile...
    python -m pip install openai-whisper soundfile -q
    if %errorlevel% neq 0 (
        echo [WARN] Whisper install failed. STT will be disabled.
    ) else (
        echo [OK] Whisper
    )
) else (
    echo [OK] Whisper
)

REM ---- 8. ffmpeg
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo [INSTALL] ffmpeg via winget...
    winget install --id Gyan.FFmpeg -e --silent >nul 2>nul
    where ffmpeg >nul 2>nul
    if %errorlevel% neq 0 (
        echo [WARN] ffmpeg not found. STT voice input will not work.
        echo   Download from https://ffmpeg.org/download.html and add to PATH.
    ) else (
        echo [OK] ffmpeg installed.
    )
) else (
    echo [OK] ffmpeg
)

REM ---- 9. SAM 2 optional
python -c "from sam2.build_sam import build_sam2" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] SAM 2 not installed. AI mask propagation disabled.
) else (
    echo [OK] SAM 2
)

echo.
echo ===========================================================
echo  All checks done. Starting server...
echo ===========================================================
echo.
start http://localhost:5000
python app.py

pause
