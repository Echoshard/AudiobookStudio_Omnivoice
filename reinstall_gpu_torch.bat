@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

title "OmniVoice Studio - GPU PyTorch Reinstaller"

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

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
if not exist "%TEMP%" (
    set "TEMP=%~dp0.tmp"
    set "TMP=%~dp0.tmp"
    if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
)

set "VENV_PYTHON=.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [System] Virtual environment not found in .venv. Creating environment...
    python -m venv .venv || (
        echo [ERROR] Python not found or failed to create venv.
        pause
        exit /b 1
    )
)

echo ============================================================
echo   OmniVoice Studio - GPU PyTorch Repair Tool
echo ============================================================
echo.
echo This tool will:
echo 1. Scan your system and GPU drivers for CUDA capabilities.
echo 2. Cleanly remove any mismatched or CPU PyTorch packages.
echo 3. Automatically download and verify the optimal CUDA PyTorch wheel.
echo.
echo Press any key to start the repair process...
pause >nul
echo.

REM Delete the installation marker file while repairing
del ".venv\.installed" 2>nul

echo [1/2] Detecting CUDA and installing compatible PyTorch...
"%VENV_PYTHON%" detect_cuda.py
if errorlevel 1 (
    echo.
    echo [ERROR] PyTorch installation failed!
    pause
    exit /b 1
)

REM Mark as successfully installed for the main launcher
echo installed > ".venv\.installed"

echo.
echo ============================================================
echo   SUCCESS: PyTorch Configuration Complete!
echo ============================================================
echo.
echo You can now launch OmniVoice Studio using run_omniStudio.bat
echo.
pause
