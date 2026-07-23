@echo off
cd /d "%~dp0"
title "OmniVoice Studio"

set "HF_HOME=%~dp0models"
set "PATH=%~dp0ffmpeg;%PATH%"
if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
if not exist "%TEMP%" (
    set "TEMP=%~dp0.tmp"
    set "TMP=%~dp0.tmp"
    if not exist "%TEMP%" mkdir "%TEMP%" 2>nul
)

if not exist .venv\.installed (
    echo [Warning] Environment not fully setup or setup file .venv\.installed is missing.
    echo [System] Running setup.bat first...
    call setup.bat
    if %errorlevel% neq 0 (
        echo [ERROR] Setup failed. Cannot launch OmniVoice Studio.
        pause
        exit /b 1
    )
)

echo [System] Launching OmniVoice Studio...
.venv\Scripts\python.exe OmniVoiceStudioUI.py
if %errorlevel% neq 0 pause
