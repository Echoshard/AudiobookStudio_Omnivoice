@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title OmniVoice Studio

REM Editable GPU install knobs:
REM   auto    = choose dynamically from nvidia-smi / driver CUDA version
REM   cu130   = target for CUDA 13.x / newer Blackwell GPUs
REM   cu128   = target for CUDA 12.8+ GPUs
REM   cu126   = target for CUDA 12.6+ GPUs
REM   cu124   = target for CUDA 12.4+ GPUs
REM   cu121   = target for CUDA 12.1+ GPUs
REM   cu118   = target for CUDA 11.8+ GPUs
REM   cpu     = force CPU-only PyTorch
if "%TORCH_CUDA_WHEEL%"=="" set "TORCH_CUDA_WHEEL=auto"
if "%TORCH_PACKAGES%"=="" set "TORCH_PACKAGES=torch torchaudio"

set "HF_HOME=%~dp0models"
set "PATH=%~dp0ffmpeg;%PATH%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
if not exist "%TEMP%" (
    set "TEMP=%~dp0.tmp"
    set "TMP=%~dp0.tmp"
    if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
)

set "VENV_PYTHON=.venv\Scripts\python.exe"

REM Perform one-time setup if .venv\.installed is missing
if not exist .venv\.installed (
    echo ============================================================
    echo   OmniVoice Studio - Initial Setup and Dependency Check
    echo ============================================================
    echo.

    if not exist "%VENV_PYTHON%" (
        echo [System] Checking system Python...
        python --version >nul 2>&1
        if %errorlevel% neq 0 (
            echo [ERROR] Python was not found on your system PATH!
            echo Please install Python 3.10+ and check 'Add Python to PATH' from https://www.python.org/
            pause
            exit /b 1
        )
        echo [System] Creating Python virtual environment in .venv...
        python -m venv .venv
        if %errorlevel% neq 0 (
            echo [ERROR] Failed to create virtual environment.
            pause
            exit /b 1
        )
    )

    echo [System] Upgrading pip...
    "%VENV_PYTHON%" -m pip install --upgrade pip

    echo [System] Detecting hardware and installing optimal PyTorch...
    "%VENV_PYTHON%" detect_cuda.py
    if %errorlevel% neq 0 (
        echo [ERROR] PyTorch installation failed.
        pause
        exit /b 1
    )

    echo [System] Installing required dependencies from requirements.txt...
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies from requirements.txt.
        pause
        exit /b 1
    )

    if not exist ffmpeg\ffmpeg.exe (
        echo [System] Downloading and extracting FFmpeg binaries...
        mkdir ffmpeg 2>nul
        curl -L -o ffmpeg.zip https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
        powershell -Command "Expand-Archive -Path ffmpeg.zip -DestinationPath ffmpeg_temp -Force; Move-Item ffmpeg_temp\*\bin\*.exe ffmpeg\ -Force; Remove-Item -Path ffmpeg_temp, ffmpeg.zip -Recurse -Force"
    )

    if exist test_voice.py (
        echo [System] Downloading model and running quick test synthesis...
        "%VENV_PYTHON%" test_voice.py
        if %errorlevel% neq 0 (
            echo [WARNING] Test voice synthesis encountered an issue, but setup will continue.
        )
    )

    echo installed > .venv\.installed
    echo.
    echo ============================================================
    echo   SUCCESS: OmniVoice Studio setup is complete!
    echo ============================================================
    echo.
)

echo [System] Launching OmniVoice Studio...
"%VENV_PYTHON%" OmniVoiceStudioUI.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] OmniVoice Studio encountered an issue.
    pause
)
