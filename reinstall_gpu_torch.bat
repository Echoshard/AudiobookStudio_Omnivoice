@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

title "AudiobookStudio - GPU PyTorch Reinstaller"

REM Editable GPU install knobs:
REM   auto    = choose from nvidia-smi driver CUDA version
REM   cu130   = current stable target for CUDA 13.x / newer Blackwell GPUs
REM   cu128   = target for CUDA 12.8+ GPUs
REM   cu126   = target for CUDA 12.6+ GPUs
REM   cpu     = force CPU-only PyTorch
set "TORCH_CUDA_WHEEL=auto"
set "TORCH_PACKAGES=torch torchaudio"
if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
if not exist "%TEMP%" (
    set "TEMP=%~dp0.tmp"
    set "TMP=%~dp0.tmp"
    if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
)

set "VENV_PYTHON=.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found in .venv!
    echo Please make sure you run run_omnivoice.bat first to set up the environment.
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo   AudiobookStudio - GPU PyTorch Repair Tool
echo ============================================================
echo.
echo This tool will:
echo 1. Cleanly uninstall any CPU-only PyTorch packages.
echo 2. Search your system for NVIDIA CUDA capabilities (bypassing PATH constraints).
echo 3. Automatically download and install CUDA-accelerated PyTorch + Torchaudio.
echo    Newer CUDA 13.x cards use the stable cu130 wheel target by default.
echo.
echo Press any key to start the repair process...
pause >nul
echo.

REM Delete the installation marker file so the main app runner knows to accept this repair
del ".venv\.installed" 2>nul

echo [1/2] Uninstalling existing CPU PyTorch and installing GPU PyTorch...
"%VENV_PYTHON%" detect_cuda.py
if errorlevel 1 (
    echo.
    echo [ERROR] PyTorch GPU installation failed!
    pause
    exit /b 1
)

REM Mark as successfully installed for the main launcher
echo installed > ".venv\.installed"

echo.
echo ============================================================
echo   SUCCESS: GPU PyTorch Installation Complete!
echo ============================================================
echo.
echo You can now launch run_omnivoice.bat to run Audiobook Studio on your NVIDIA GPU!
echo.
pause
