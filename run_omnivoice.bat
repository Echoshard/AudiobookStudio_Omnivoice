@echo off
cd /d "%~dp0"
set "HF_HOME=%~dp0models"
set "PATH=%~dp0ffmpeg;%PATH%"

if not exist .venv (
    echo [System] Creating Python virtual environment...
    python -m venv .venv || (echo [ERROR] Python not found or failed to create venv. & pause & exit /b 1)
)

if not exist .venv\.installed (
    echo [System] Installing packages...
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe detect_cuda.py || (echo [ERROR] PyTorch installation failed. & pause & exit /b 1)
    .venv\Scripts\pip.exe install -r requirements.txt || (echo [ERROR] Requirements installation failed. & pause & exit /b 1)
    
    if not exist ffmpeg\ffmpeg.exe (
        echo [System] Downloading and extracting FFmpeg...
        mkdir ffmpeg 2>nul
        curl -L -o ffmpeg.zip https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
        powershell -Command "Expand-Archive -Path ffmpeg.zip -DestinationPath ffmpeg_temp -Force; Move-Item ffmpeg_temp\*\bin\*.exe ffmpeg\ -Force; Remove-Item -Path ffmpeg_temp, ffmpeg.zip -Recurse -Force"
    )
    echo installed > .venv\.installed
)

echo [System] Launching Audiobook Studio...
.venv\Scripts\python.exe OmniVoiceUI.py
if %errorlevel% neq 0 pause
