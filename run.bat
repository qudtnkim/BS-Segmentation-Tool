@echo off
setlocal enabledelayedexpansion
title BS Segmentation Tool

REM ============================================================
REM  BS Segmentation Tool - Setup and Launcher
REM  Fast-path: skip admin elevation when everything is installed
REM  ASCII only (Korean cp949 consoles choke on em dashes etc.)
REM ============================================================

REM ---- 1. Locate a Python interpreter. DO NOT auto-install.
set "PY="
where py >nul 2>nul
if !errorlevel! equ 0 (
    for %%V in (3.12 3.11 3.10) do (
        if not defined PY (
            py -%%V --version >nul 2>nul
            if !errorlevel! equ 0 set "PY=py -%%V"
        )
    )
)
if not defined PY (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        python --version >nul 2>nul
        if !errorlevel! equ 0 set "PY=python"
    )
)
if not defined PY (
    where py >nul 2>nul
    if !errorlevel! equ 0 set "PY=py -3"
)
if not defined PY (
    echo [ERROR] Python not found in PATH.
    echo   Install Python 3.10-3.12 from https://www.python.org/
    echo   Check "Add python.exe to PATH" during install, then re-run this script.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
echo [OK] Python %PYVER% found (%PY%).

REM ---- 2. Virtual environment (fixed, ASCII-only location)
set "VENV_DIR=%USERPROFILE%\.bs_tool\venv"
echo %VENV_DIR%| findstr /R "[^ -~]" >nul
if !errorlevel! equ 0 (
    echo [INFO] USERPROFILE has non-ASCII chars, using C:\bs_tool_venv instead.
    set "VENV_DIR=C:\bs_tool_venv"
)
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Creating virtual environment at %VENV_DIR% ...
    if not exist "%VENV_DIR%\.." mkdir "%VENV_DIR%\.." 2>nul
    %PY% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo [ERROR] Virtual environment creation failed.
        pause
        exit /b 1
    )
)
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
echo [OK] Venv ready at %VENV_DIR%.

REM ---- 3. FAST PATH: if all deps + ffmpeg are already present, skip admin elevation
REM     and jump straight to launch. This is the "python is installed, skip and go" path.
"%VENV_PY%" -c "import flask, cv2, torch, mobile_sam" >nul 2>nul
set "PKGS_OK=!errorlevel!"
where ffmpeg >nul 2>nul
set "FFMPEG_OK=!errorlevel!"
if !PKGS_OK! equ 0 if !FFMPEG_OK! equ 0 (
    echo [FASTPATH] All dependencies + ffmpeg present. Launching directly, no admin needed.
    goto LAUNCH
)

REM ---- 4. Something needs installing. Elevate ONLY if we need to write system PATH (ffmpeg).
REM     If pkgs are the only thing missing, plain-user pip install into the venv works fine.
net session >nul 2>&1
if !errorlevel! neq 0 (
    if !FFMPEG_OK! neq 0 (
        echo [INFO] ffmpeg missing - system-wide install needs Administrator rights.
        echo        Requesting UAC elevation...
        powershell -NoProfile -Command "try { Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs } catch { exit 1 }"
        exit /b
    )
)

echo ===========================================================
echo  Installing missing dependencies...
echo ===========================================================
echo.

REM ---- 5. Core dependencies (wheels-only first, source fallback)
echo [INFO] Upgrading pip and pinning setuptools for torch compatibility...
"%VENV_PY%" -m pip install --upgrade pip -q
"%VENV_PY%" -m pip install "setuptools<82" wheel -q
echo [INFO] Installing core dependencies (binary wheels only)...
"%VENV_PY%" -m pip install --only-binary=:all: -r "%~dp0requirements.txt" -q
set "CORE_ERR=!errorlevel!"
if !CORE_ERR! neq 0 (
    echo [WARN] Wheel-only install failed. Retrying with source builds allowed...
    "%VENV_PY%" -m pip install -r "%~dp0requirements.txt" -q
    set "CORE_ERR=!errorlevel!"
)
if !CORE_ERR! neq 0 (
    echo.
    echo [ERROR] Core dependency install failed.
    echo   Common causes: Python 3.13+ has no prebuilt wheel; or no internet.
    pause
    exit /b 1
)
echo [OK] Core dependencies installed.
echo.

REM ---- 6. ffmpeg (system-wide; needs admin, which we have if we reached here)
where ffmpeg >nul 2>nul
if !errorlevel! neq 0 (
    echo [INSTALL] Installing ffmpeg system-wide...
    where winget >nul 2>nul
    if !errorlevel! equ 0 (
        winget install --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements
    )
    where ffmpeg >nul 2>nul
    if !errorlevel! neq 0 (
        echo [INFO] winget unavailable, copying bundled ffmpeg to C:\ffmpeg\bin ...
        if not exist "C:\ffmpeg\bin" mkdir "C:\ffmpeg\bin"
        "%VENV_PY%" -c "import imageio_ffmpeg, shutil; shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), r'C:\ffmpeg\bin\ffmpeg.exe')"
        powershell -NoProfile -Command "$m=[Environment]::GetEnvironmentVariable('Path','Machine'); if ($m -notlike '*C:\ffmpeg\bin*') { [Environment]::SetEnvironmentVariable('Path', $m.TrimEnd(';') + ';C:\ffmpeg\bin', 'Machine') }"
        set "PATH=%PATH%;C:\ffmpeg\bin"
    )
)
where ffmpeg >nul 2>nul
if !errorlevel! equ 0 (
    echo [OK] ffmpeg available.
) else (
    echo [WARN] System-wide ffmpeg install failed. App uses its bundled fallback.
)
echo.

REM ---- 7. PyTorch (GPU auto-detect)
where nvidia-smi >nul 2>nul
set "HAS_GPU=0"
if !errorlevel! equ 0 set "HAS_GPU=1"

"%VENV_PY%" -c "import torch" >nul 2>nul
if !errorlevel! neq 0 (
    if "!HAS_GPU!"=="1" (
        echo [INSTALL] NVIDIA GPU detected - installing PyTorch CUDA (few minutes)...
        "%VENV_PY%" -m pip install torch -q
    ) else (
        echo [INSTALL] No GPU detected - installing PyTorch CPU (few minutes)...
        "%VENV_PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu -q
    )
    if !errorlevel! neq 0 echo [WARN] PyTorch install failed. AI features will be limited.
) else (
    echo [OK] PyTorch already available.
)
echo.

REM ---- 8. Whisper STT (optional)
"%VENV_PY%" -c "import whisper" >nul 2>nul
if !errorlevel! neq 0 (
    echo [INSTALL] openai-whisper for voice input...
    "%VENV_PY%" -m pip install openai-whisper -q
    if !errorlevel! neq 0 echo [WARN] Whisper install failed. Voice input disabled.
) else (
    echo [OK] Whisper already available.
)
echo.

REM ---- 9. MobileSAM (only AI backend). Full-import probe so missing timm is caught.
"%VENV_PY%" -c "from mobile_sam import sam_model_registry" >nul 2>nul
if !errorlevel! equ 0 goto MSAM_OK
echo [INSTALL] MobileSAM missing - installing timm then MobileSAM ...
"%VENV_PY%" -m pip install timm -q
if !errorlevel! neq 0 (
    echo [WARN] timm install failed. AI auto-propose will be off.
    goto MSAM_DONE
)
"%VENV_PY%" -m pip install git+https://github.com/ChaoningZhang/MobileSAM.git -q
if !errorlevel! neq 0 (
    echo [WARN] MobileSAM install failed. AI auto-propose will be off.
    goto MSAM_DONE
)
"%VENV_PY%" -c "from mobile_sam import sam_model_registry; sam_model_registry['vit_t']" >nul 2>nul
if !errorlevel! neq 0 (
    echo [WARN] MobileSAM installed but not usable. AI auto-propose will be off.
    goto MSAM_DONE
)
echo [OK] MobileSAM installed and verified.
goto MSAM_DONE
:MSAM_OK
echo [OK] MobileSAM already available. Weight bundled in the repo.
:MSAM_DONE
echo.

:LAUNCH
echo ===========================================================
echo  All checks done. Starting server...
echo ===========================================================
echo.
start http://localhost:5000
"%VENV_PY%" "%~dp0app.py"

pause
