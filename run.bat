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

echo.
echo ===========================================================
echo  FIRST RUN SETUP - this happens once and takes a while.
echo  Total download is roughly 1-3 GB depending on your GPU.
echo  Progress bars below are live. Do not close this window.
echo ===========================================================
echo.

REM -q is deliberately NOT used below. pip prints its own download progress
REM bars and without them the console looks frozen for several minutes while
REM torch downloads, which is exactly what users report as "it hangs".

echo [1/5] Upgrading pip ... (a few seconds)
"%VPY%" -m pip install --upgrade pip
echo.

echo [2/5] Core libraries: Flask, OpenCV, pandas ... (~1 min, ~100 MB)
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto PIPFAIL
echo.

echo [3/3] PyTorch ... (THE SLOW ONE: 5-15 min, 200 MB - 2.5 GB)
echo       If the bar stalls at 0%%%% for a bit, it is resolving the index. Be patient.
"%VPY%" -m pip install torch
if errorlevel 1 goto PIPFAIL
echo.

REM MobileSAM needs NO install: its source is vendored in vendor\mobile_sam and
REM the weight ships as mobile_sam.pt. Whisper is not installed either - the app
REM fetches it on demand the first time the microphone button is pressed.

echo ===========================================================
echo  Setup complete. Future runs skip all of this and start
echo  in a couple of seconds.
echo ===========================================================
echo.

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
