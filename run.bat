@echo off
setlocal enabledelayedexpansion
title BS Segmentation Tool

REM ---- 0. Re-launch elevated (Administrator) if not already running as one.
REM     Needed to install ffmpeg system-wide (Program Files + machine PATH).
net session >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] Administrator privileges required - requesting UAC elevation...
    powershell -NoProfile -Command "try { Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs } catch { exit 1 }"
    if !errorlevel! neq 0 (
        echo [ERROR] Administrator privileges were not granted.
        echo   Approve the UAC prompt, or right-click run.bat and choose "Run as administrator".
        pause
        exit /b 1
    )
    exit /b
)

echo ===========================================================
echo  BS Segmentation Tool Setup and Launcher  (Administrator)
echo ===========================================================
echo.

REM ---- 1. Find a working Python (python.exe on PATH, or the py launcher)
set "PY="
where python >nul 2>nul
if !errorlevel! equ 0 (
    python --version >nul 2>nul
    if !errorlevel! equ 0 set "PY=python"
)
if not defined PY (
    where py >nul 2>nul
    if !errorlevel! equ 0 set "PY=py -3"
)
if not defined PY (
    echo [ERROR] Python not found in PATH.
    echo   Install Python 3.10+ from https://www.python.org/
    echo   Check 'Add python.exe to PATH' during install.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('%PY% --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% found (using: %PY%).
echo.

REM ---- 2. Create an isolated virtual environment (.venv)
REM     Installing into a venv instead of the system Python avoids version
REM     conflicts with whatever else is already on the target machine.
set "VENV_DIR=%~dp0.venv"
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Creating virtual environment in .venv ...
    %PY% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo [ERROR] Virtual environment creation failed.
        pause
        exit /b 1
    )
)
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
echo [OK] Virtual environment ready.
echo.

REM ---- 3. Core dependencies (pinned in requirements.txt)
echo [INFO] Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip -q
echo [INFO] Installing core dependencies (Flask, OpenCV, pandas, ffmpeg)...
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt" -q
if !errorlevel! neq 0 (
    echo [ERROR] Core dependency install failed. Check your internet connection.
    pause
    exit /b 1
)
echo [OK] Core dependencies installed.
echo.

REM ---- 3b. ffmpeg, system-wide (now that we have admin rights).
REM     If this fails for any reason, app.py falls back to its own bundled
REM     copy (imageio-ffmpeg) at runtime, so the app still works either way.
where ffmpeg >nul 2>nul
if !errorlevel! neq 0 (
    echo [INSTALL] Installing ffmpeg system-wide...
    where winget >nul 2>nul
    if !errorlevel! equ 0 (
        winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements
    )
    where ffmpeg >nul 2>nul
    if !errorlevel! neq 0 (
        echo [INFO] winget unavailable or failed - installing bundled ffmpeg binary to C:\ffmpeg\bin instead...
        if not exist "C:\ffmpeg\bin" mkdir "C:\ffmpeg\bin"
        for /f "delims=" %%f in ('"%VENV_PY%" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"') do (
            copy /y "%%f" "C:\ffmpeg\bin\ffmpeg.exe" >nul
        )
        REM Append to the machine PATH via .NET (setx truncates PATH past 1024 chars - do not use it here).
        powershell -NoProfile -Command ^
            "$m=[Environment]::GetEnvironmentVariable('Path','Machine'); if ($m -notlike '*C:\ffmpeg\bin*') { [Environment]::SetEnvironmentVariable('Path', $m.TrimEnd(';') + ';C:\ffmpeg\bin', 'Machine') }"
        set "PATH=%PATH%;C:\ffmpeg\bin"
    )
)
where ffmpeg >nul 2>nul
if !errorlevel! equ 0 (
    echo [OK] ffmpeg available system-wide.
) else (
    echo [WARN] System-wide ffmpeg install failed. The app will still use its bundled fallback.
)
echo.

REM ---- 4. PyTorch CPU (optional, large download; failure does not block the app)
"%VENV_PY%" -c "import torch" >nul 2>nul
if !errorlevel! neq 0 (
    echo [INSTALL] PyTorch CPU... this may take a few minutes.
    "%VENV_PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu -q
    if !errorlevel! neq 0 (
        echo [WARN] PyTorch install failed. GPU/AI features will be limited.
    ) else (
        echo [OK] PyTorch installed.
    )
) else (
    echo [OK] PyTorch already available.
)
echo.

REM ---- 5. Whisper STT (optional; ffmpeg is bundled via imageio-ffmpeg, no winget needed)
"%VENV_PY%" -c "import whisper" >nul 2>nul
if !errorlevel! neq 0 (
    echo [INSTALL] openai-whisper for voice input...
    "%VENV_PY%" -m pip install openai-whisper -q
    if !errorlevel! neq 0 (
        echo [WARN] Whisper install failed. Voice input (STT) will be disabled.
    ) else (
        echo [OK] Whisper installed.
    )
) else (
    echo [OK] Whisper already available.
)
echo.

REM ---- 6. SAM 2 (optional, heavy; app runs fine without it - manual brush tools remain)
"%VENV_PY%" -c "from sam2.build_sam import build_sam2" >nul 2>nul
if !errorlevel! neq 0 (
    echo [INFO] SAM 2 not installed. AI-assisted mask propagation disabled.
    echo   Optional manual install:
    echo   "%VENV_PY%" -m pip install "git+https://github.com/facebookresearch/sam2.git"
) else (
    echo [OK] SAM 2 available.
)
echo.

echo ===========================================================
echo  All checks done. Starting server...
echo ===========================================================
echo.
start http://localhost:5000
"%VENV_PY%" "%~dp0app.py"

pause
