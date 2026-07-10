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

REM ---- 1. Pick a Python (prefer 3.12, then 3.11, then 3.10, warn on 3.13+)
set "PY="
set "PY_VER_MAJOR=0"
set "PY_VER_MINOR=0"

REM Try py launcher with specific versions first
where py >nul 2>nul
if !errorlevel! equ 0 (
    for %%V in (3.12 3.11 3.10) do (
        if not defined PY (
            py -%%V --version >nul 2>nul
            if !errorlevel! equ 0 (
                set "PY=py -%%V"
                echo [OK] Using Python %%V via py launcher.
            )
        )
    )
)

REM Fallback: default python on PATH
if not defined PY (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        python --version >nul 2>nul
        if !errorlevel! equ 0 set "PY=python"
    )
)

REM Last resort: default py launcher (whatever version)
if not defined PY (
    where py >nul 2>nul
    if !errorlevel! equ 0 set "PY=py -3"
)

if not defined PY (
    echo [ERROR] Python not found in PATH.
    echo   Install Python 3.10-3.12 from https://www.python.org/
    echo   Check 'Add python.exe to PATH' during install.
    pause
    exit /b 1
)

REM Detect version for warning
for /f "tokens=2 delims= " %%v in ('%PY% --version 2^>^&1') do set "PYVER=%%v"
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set "PY_VER_MAJOR=%%a"
    set "PY_VER_MINOR=%%b"
)
echo [OK] Python %PYVER% found (using: %PY%).

REM Warn on Python 3.13+ (numpy/torch wheels may be missing)
if !PY_VER_MAJOR! equ 3 if !PY_VER_MINOR! geq 13 (
    echo.
    echo [WARN] Python !PYVER! detected. Some packages numpy, torch may not have
    echo   prebuilt wheels for 3.13+ and require slow source builds that can fail.
    echo   For best results, install Python 3.12 from https://www.python.org/
    echo.
)
echo.

REM ---- 2. Virtual environment in a fixed, ASCII-only user location
REM     This avoids issues with non-ASCII characters in the project path.
set "VENV_DIR=%USERPROFILE%\.bs_tool\venv"
echo [INFO] Virtual environment location: %VENV_DIR%

REM Verify the venv path itself is ASCII (USERPROFILE could contain non-ASCII)
echo %VENV_DIR%| findstr /R "[^ -~]" >nul
if !errorlevel! equ 0 (
    echo [WARN] Your user profile path contains non-ASCII characters:
    echo   %USERPROFILE%
    echo   Falling back to C:\bs_tool_venv instead.
    set "VENV_DIR=C:\bs_tool_venv"
    echo [INFO] New virtual environment location: !VENV_DIR!
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Creating virtual environment ...
    if not exist "%VENV_DIR%\.." mkdir "%VENV_DIR%\.." 2>nul
    %PY% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo [ERROR] Virtual environment creation failed.
        pause
        exit /b 1
    )
)
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
echo [OK] Virtual environment ready at %VENV_DIR%.
echo.

REM ---- 3. Core dependencies (wheel-only to avoid source builds)
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
    echo   Likely causes:
    echo     1. Python !PYVER! has no prebuilt wheel for some package - install Python 3.12 instead.
    echo     2. No internet connection.
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

REM ---- 6. SAM 2 (optional - auto install attempted; PyPI "sam2" package, no Git required)
"%VENV_PY%" -c "from sam2.build_sam import build_sam2" >nul 2>nul
set "SAM2_PRESENT=!errorlevel!"
if !SAM2_PRESENT! equ 0 goto SAM2_OK

echo [INSTALL] SAM 2 not found - installing from PyPI...
"%VENV_PY%" -m pip install sam2 -q
set "SAM2_ERR=!errorlevel!"
if !SAM2_ERR! neq 0 (
    echo [WARN] SAM 2 install failed. AI mask propagation will be disabled.
    echo   Retry manually: "%VENV_PY%" -m pip install sam2
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