@echo off
cd /d "%~dp0"
title BS Segmentation Tool

echo ===========================================================
echo  BS Segmentation Tool
echo ===========================================================
echo.

REM Requires Python 3.10-3.12 already installed and on PATH.
REM No auto-install, no admin, no UAC. If python is missing, install it once
REM from https://www.python.org/ with "Add python.exe to PATH" checked.

python --version >nul 2>&1
if errorlevel 1 goto NOPYTHON

for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [OK] Python %%v

REM venv lives inside the project folder so a Korean username can't break it
set VENV=%~dp0.venv
set VPY=%VENV%\Scripts\python.exe

if not exist "%VPY%" (
    echo [INFO] Creating virtual environment .venv ...
    python -m venv "%VENV%"
    if errorlevel 1 goto VENVFAIL
)
echo [OK] venv ready

REM Skip the whole install pass when the app can already import what it needs
"%VPY%" -c "import flask, cv2, pandas" >nul 2>&1
if not errorlevel 1 goto RUN

echo [INFO] Installing dependencies (first run only, needs internet)...
"%VPY%" -m pip install --upgrade pip -q
"%VPY%" -m pip install -r requirements.txt -q
if errorlevel 1 goto PIPFAIL

echo [INFO] Installing PyTorch (large download, first run only)...
"%VPY%" -m pip install torch -q
"%VPY%" -m pip install git+https://github.com/ChaoningZhang/MobileSAM.git -q
"%VPY%" -m pip install openai-whisper -q
echo [OK] dependencies installed

:RUN
echo.
echo ===========================================================
echo  Starting server at http://localhost:5000
echo  Keep this window open. Ctrl+C to stop.
echo ===========================================================
echo.
start "" http://localhost:5000
"%VPY%" app.py
echo.
echo [INFO] Server stopped.
goto END

:NOPYTHON
echo [ERROR] Python not found on PATH.
echo.
echo   Install Python 3.12 from https://www.python.org/downloads/
echo   IMPORTANT: tick "Add python.exe to PATH" in the installer.
echo   Then run this file again.
goto END

:VENVFAIL
echo [ERROR] Could not create the .venv folder.
echo   Check that you can write to: %~dp0
goto END

:PIPFAIL
echo [ERROR] Dependency install failed.
echo   Usually this means no internet, or Python 3.13+ (no prebuilt wheels).
echo   Python 3.12 is the safest version for this tool.
goto END

:END
echo.
pause
