@echo off
setlocal enabledelayedexpansion
title BS Segmentation Tool

REM ---- 0. Re-launch elevated (Administrator)
net session >nul 2>&1
if !errorlevel! neq 0 (
    echo [INFO] Administrator privileges required - requesting UAC elevation...
    powershell -NoProfile -Command "try { Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs } catch { exit 1 }"
    if !errorlevel! neq 0 (
        echo [ERROR] Administrator privileges were not granted.
        echo   Right-click run.bat and choose Run as administrator.
        pause
        exit /b 1
    )
    exit /b
)

echo ===========================================================
echo  BS Segmentation Tool Setup and Launcher  (Administrator)
echo ===========================================================
echo.

REM ---- 1. Find Python
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

REM ---- 2. Virtual environment
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

REM ---- 3. Core dependencies
echo [INFO] Upgrading pip and pinning setuptools for torch compatibility...
"%VENV_PY%" -m pip install --upgrade pip -q
"%VENV_PY%" -m pip install "setuptools<82" wheel -q
echo [INFO] Installing core dependencies...
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt" -q
if !errorlevel! neq 0 (
    echo [ERROR] Core dependency install failed. Check your internet connection.
    pause
    exit /b 1
)
echo [OK] Core dependencies installed.
echo.

REM ---- 3b. ffmpeg system-wide
where ffmpeg >nul 2>nul
if !errorlevel! neq 0 (
    echo [INSTALL] Installing ffmpeg system-wide...
    where winget >nul 2>nul
    if !errorlevel! equ 0 (
        winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements
    )
    where ffmpeg >nul 2>nul
    if !errorlevel! neq 0 (
        echo [INFO] winget unavailable or failed - copying bundled ffmpeg to C:\ffmpeg\bin ...
        if not exist "C:\ffmpeg\bin" mkdir "C:\ffmpeg\bin"
        "%VENV_PY%" -c "import imageio_ffmpeg, shutil; shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), r'C:\ffmpeg\bin\ffmpeg.exe')"
        powershell -NoProfile -Command "$m=[Environment]::GetEnvironmentVariable('Path','Machine'); if ($m -notlike '*C:\ffmpeg\bin*') { [Environment]::SetEnvironmentVariable('Path', $m.TrimEnd(';') + ';C:\ffmpeg\bin', 'Machine') }"
        set "PATH=%PATH%;C:\ffmpeg\bin"
    )
)
where ffmpeg >nul 2>nul
if !errorlevel! equ 0 (
    echo [OK] ffmpeg available system-wide.
) else (
    echo [WARN] System-wide ffmpeg install failed. App will use its bundled fallback.
)
echo.

REM ---- 4. PyTorch (optional)
where nvidia-smi >nul 2>nul
set "HAS_GPU=0"
if !errorlevel! equ 0 set "HAS_GPU=1"

"%VENV_PY%" -c "import torch" >nul 2>nul
if !errorlevel! neq 0 (
    if "!HAS_GPU!"=="1" (
        echo [INSTALL] NVIDIA GPU detected - installing PyTorch CUDA... this may take a few minutes.
        "%VENV_PY%" -m pip install torch -q
    ) else (
        echo [INSTALL] No GPU detected - installing PyTorch CPU build... this may take a few minutes.
        "%VENV_PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu -q
    )
    set "TORCH_ERR=!errorlevel!"
    if !TORCH_ERR! neq 0 (
        echo [WARN] PyTorch install failed. GPU/AI features will be limited.
    ) else (
        echo [OK] PyTorch installed.
    )
) else (
    "%VENV_PY%" -c "import torch; open('%TEMP%\\tc.txt','w').write(str(torch.cuda.is_available()))" >nul 2>nul
    set /p TORCH_CUDA_OK=<%TEMP%\tc.txt
    if "!HAS_GPU!"=="1" if /i "!TORCH_CUDA_OK!"=="False" (
        echo [INFO] GPU detected but PyTorch is CPU-only - reinstalling with CUDA...
        "%VENV_PY%" -m pip install --force-reinstall torch -q
        "%VENV_PY%" -c "import torch; open('%TEMP%\\tc.txt','w').write(str(torch.cuda.is_available()))" >nul 2>nul
        set /p TORCH_CUDA_OK=<%TEMP%\tc.txt
    )
    echo [OK] PyTorch already available (CUDA: !TORCH_CUDA_OK!^)
)
echo.

REM ---- 5. Whisper STT (optional)
"%VENV_PY%" -c "import whisper" >nul 2>nul
if !errorlevel! neq 0 (
    echo [INSTALL] openai-whisper for voice input...
    "%VENV_PY%" -m pip install openai-whisper -q
    set "WHISPER_ERR=!errorlevel!"
    if !WHISPER_ERR! neq 0 (
        echo [WARN] Whisper install failed. Voice input will be disabled.
    ) else (
        echo [OK] Whisper installed.
    )
) else (
    echo [OK] Whisper already available.
)
echo.

REM ---- 6. SAM 2 (optional - auto install attempted)
"%VENV_PY%" -c "from sam2.build_sam import build_sam2" >nul 2>nul
set "SAM2_PRESENT=!errorlevel!"
if !SAM2_PRESENT! equ 0 goto SAM2_OK

echo [INSTALL] SAM 2 not found - attempting install (requires Git)...
where git >nul 2>nul
if !errorlevel! neq 0 (
    echo [WARN] Git not found. SAM 2 requires Git to install.
    echo   Install Git from https://git-scm.com/ then re-run this script.
    goto SAM2_DONE
)

"%VENV_PY%" -m pip install "git+https://github.com/facebookresearch/sam2.git" -q
set "SAM2_ERR=!errorlevel!"
if !SAM2_ERR! neq 0 (
    echo [WARN] SAM 2 install failed. AI mask propagation will be disabled.
    echo   Retry manually: "%VENV_PY%" -m pip install git+https://github.com/facebookresearch/sam2.git
    goto SAM2_DONE
)
echo [OK] SAM 2 installed.
goto SAM2_DONE

:SAM2_OK
echo [OK] SAM 2 already available.

:SAM2_DONE
echo.

echo ===========================================================
echo  All checks done. Starting server...
echo ===========================================================
echo.
start http://localhost:5000
"%VENV_PY%" "%~dp0app.py"

pause